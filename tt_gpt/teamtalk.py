"""All TeamTalk SDK calls run on the event-loop thread."""
from collections import deque
import importlib
import json
import logging
from pathlib import Path
import random
import sys
import time

from .core import Message

LOG = logging.getLogger(__name__)


def sdk(config):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'vendor'))
    tt = importlib.import_module('TeamTalk5')
    if not tt.setLicense(tt.ttstr(config.license_name), tt.ttstr(config.license_key)):
        raise ValueError('TeamTalk SDK rejected the license')
    # Instantiation checks Python/C structure sizes before making a connection.
    for name in ('User', 'TextMessage', 'TTMessage', 'Channel', 'UserAccount'):
        getattr(tt, name)()
    return tt


class TeamTalkBot:
    def __init__(self, config, core, stop):
        self.config, self.core, self.stop = config, core, stop
        self.tt = sdk(config)
        self.client = self.tt.TeamTalk()
        self.login_command = 0
        self.join_command = 0
        self.joined_channel = 0
        self.password_index = 0
        self.passwords = [config.password]
        if config.fallback_password and config.fallback_password != config.password:
            self.passwords.append(config.fallback_password)
        self.authenticated = False
        self.connecting = False
        self.next_connect = 0
        self.deadline = 0
        self.backoff = 3
        self.fragments = {}
        self.outbound = deque()
        self.next_send = 0
        self.send_commands = {}
        self.next_snapshot = 0

    def login(self):
        c, t = self.config, self.tt
        self.login_command = self.client.doLogin(t.ttstr(c.nickname), t.ttstr(c.username),
            t.ttstr(self.passwords[self.password_index]), t.ttstr('TeamTalk GPT Bot'))
        if self.login_command <= 0:
            self.reconnect('login_submit_failed')
            return
        self.core.connection = 'logging in'
        self.deadline = time.monotonic() + 30

    def reconnect(self, reason):
        LOG.warning('teamtalk_disconnected reason=%s', reason)
        self.core.last_error = reason
        self.core.connection = 'reconnecting'
        self.core.disconnected()
        self.client.disconnect()
        self.authenticated = self.connecting = False
        self.login_command = self.join_command = self.joined_channel = 0
        self.fragments.clear()
        self.outbound.clear()
        self.send_commands.clear()
        self.deadline = 0
        self.next_connect = time.monotonic() + self.backoff + random.random()
        self.backoff = min(60, self.backoff * 2)

    def join(self):
        c = self.config
        channel_id = (self.client.getRootChannelID() if c.channel == '/' else
                      self.client.getChannelIDFromPath(self.tt.ttstr(c.channel)))
        if not channel_id:
            LOG.error('configured_channel_not_found')
            raise ValueError('Configured TeamTalk channel does not exist')
        self.join_command = self.client.doJoinChannelByID(channel_id, self.tt.ttstr(c.channel_password))
        if self.join_command <= 0:
            raise ValueError('Could not submit the TeamTalk channel join command')

    def handle(self, event):
        e, t = self.tt.ClientEvent, self.tt
        kind = event.nClientEvent
        if kind == e.CLIENTEVENT_CON_SUCCESS:
            LOG.info('teamtalk_connected')
            # Hold the connection state until authentication completes.
            self.connecting = True
            self.login()
        elif kind in (e.CLIENTEVENT_CON_FAILED, e.CLIENTEVENT_CON_LOST, e.CLIENTEVENT_CON_CRYPT_ERROR):
            self.reconnect('connection_lost')
        elif kind == e.CLIENTEVENT_CMD_MYSELF_LOGGEDIN:
            self.authenticated = True
            self.connecting = False
            self.passwords = [self.passwords[self.password_index]]
            self.password_index = 0
            self.core.connection = 'logged in, joining channel'
            self.client.doChangeStatus(0, t.ttstr(self.config.status))
            LOG.info('teamtalk_logged_in user_id=%d', self.client.getMyUserID())
            account = self.client.getMyUserAccount()
            LOG.info('teamtalk_account type=%d rights=%d', account.uUserType, account.uUserRights)
            # Channel list is fully populated by CMD_SUCCESS for the login command.
        elif kind == e.CLIENTEVENT_CMD_SUCCESS:
            if event.nSource == self.login_command:
                self.login_command = 0
                self.join()
            elif event.nSource == self.join_command:
                self.join_command = 0
                self.deadline = 0
                self.backoff = 3
                self.joined_channel = self.client.getMyChannelID()
                self.core.connection = f'online, channel {self.joined_channel}'
                LOG.info('teamtalk_ready channel_id=%d', self.joined_channel)
            self.send_commands.pop(event.nSource, None)
        elif kind == e.CLIENTEVENT_CMD_ERROR:
            code = int(event.clienterrormsg.nErrorNo)
            LOG.error('teamtalk_command_error command=%d code=%d', event.nSource, code)
            self.core.last_error = f'teamtalk_error_{code}'
            if event.nSource == self.login_command:
                if code == t.ClientError.CMDERR_INVALID_ACCOUNT and self.password_index + 1 < len(self.passwords):
                    self.password_index += 1
                    self.login()
                elif code == t.ClientError.CMDERR_INVALID_ACCOUNT:
                    raise ValueError('TeamTalk rejected all provided account passwords')
                else:
                    self.reconnect(f'login_error_{code}')
            elif event.nSource == self.join_command:
                raise ValueError(f'TeamTalk channel join failed: {code}')
            elif event.nSource in self.send_commands:
                self.send_commands.pop(event.nSource, None)
                self.core.stats['errors'] += 1
        elif kind in (e.CLIENTEVENT_CMD_MYSELF_LOGGEDOUT, e.CLIENTEVENT_CMD_MYSELF_KICKED):
            self.reconnect('logged_out_or_kicked')
        elif kind == e.CLIENTEVENT_CMD_USER_LOGGEDOUT:
            self.core.forget_user(event.user.nUserID)
            self.fragments = {k: v for k, v in self.fragments.items() if k[0] != event.user.nUserID}
            self.outbound = deque((reply, chunk) for reply, chunk in self.outbound
                                  if reply.message.user_id != event.user.nUserID)
        elif kind == e.CLIENTEVENT_CMD_USER_JOINED and event.user.nUserID == self.client.getMyUserID():
            self.joined_channel = event.user.nChannelID
            self.core.connection = f'online, channel {self.joined_channel}'
        elif kind == e.CLIENTEVENT_CMD_USER_TEXTMSG and self.authenticated:
            self.receive(event.textmessage)

    def receive(self, text):
        sender = int(text.nFromUserID)
        LOG.info('teamtalk_text_received from_user_id=%d type=%d to_user_id=%d channel_id=%d',
                 sender, text.nMsgType, text.nToUserID, text.nChannelID)
        if sender <= 0 or sender == self.client.getMyUserID() or text.nMsgType not in (1, 2):
            return
        private = text.nMsgType == 1
        # TeamTalk omits the recipient ID on directly delivered private messages.
        # We never subscribe to intercepted private traffic.
        if private and text.nToUserID not in (0, self.client.getMyUserID()):
            return
        if not private and (text.nChannelID <= 0 or text.nChannelID != self.client.getMyChannelID()):
            return
        user = self.client.getUser(sender)
        if user.nUserID != sender:
            LOG.warning('teamtalk_sender_not_visible user_id=%d', sender)
            return
        key = (sender, text.nMsgType, text.nToUserID, text.nChannelID)
        raw = text.szMessage
        part = raw.decode('utf-8', errors='replace') if isinstance(raw, bytes) else raw
        previous, _, oversized = self.fragments.pop(key, ('', 0, False))
        combined = previous + part
        oversized = oversized or len(combined) > 8000
        if text.bMore:
            # Bound incomplete messages and expire them, including oversized ones.
            if len(self.fragments) < 128:
                self.fragments[key] = ('' if oversized else combined, time.monotonic(), oversized)
            return
        if oversized:
            combined = 'x' * 8001
        self.core.receive(Message(sender, tstr(user.szUsername), int(text.nChannelID), private,
            combined, bool(user.uUserType & self.tt.UserType.USERTYPE_ADMIN), self.core.generation))

    def valid_recipient(self, reply):
        msg = reply.message
        if not self.authenticated or msg.generation != self.core.generation:
            return False
        user = self.client.getUser(msg.user_id)
        if user.nUserID != msg.user_id or tstr(user.szUsername) != msg.username:
            return False
        return reply.private or (self.core.channel_replies_enabled and
                                 self.client.getMyChannelID() == msg.channel_id and
                                 user.nChannelID == msg.channel_id)

    def queue_replies(self):
        if not self.core.channel_replies_enabled:
            self.outbound = deque((reply, chunk) for reply, chunk in self.outbound if reply.private)
        for reply in self.core.poll():
            if not self.valid_recipient(reply):
                continue
            chunks = self.tt.buildTextMessage(reply.text,
                    1 if reply.private else 2,
                    nToUserID=reply.message.user_id if reply.private else 0,
                    nChannelID=0 if reply.private else reply.message.channel_id)
            if len(self.outbound) + len(chunks) > 128:
                LOG.warning('outbound_queue_full')
                continue
            for chunk in chunks:
                self.outbound.append((reply, chunk))

    def flush(self, now):
        if now < self.next_send or not self.outbound:
            return
        reply, chunk = self.outbound.popleft()
        if self.valid_recipient(reply):
            command = self.client.doTextMessage(chunk)
            if command > 0:
                self.send_commands[command] = now
            else:
                self.core.stats['errors'] += 1
                self.core.last_error = 'text_submit_failed'
                LOG.error('teamtalk_text_submit_failed')
            self.next_send = now + 0.6

    def snapshot(self):
        path = self.config.data_dir / 'status.json'
        data = dict(self.core.stats, connection=self.core.connection, model=self.config.model,
                    uptime_seconds=int(self.core.clock() - self.core.started),
                    queued=len(self.core.waiting), active=len(self.core.active),
                    last_error=self.core.last_error, updated_at=int(time.time()))
        data['channel_replies_enabled'] = self.core.channel_replies_enabled
        data['openai_costs'] = self.core.costs.snapshot() if self.core.costs is not None else {'available': False}
        if self.authenticated:
            user = self.client.getUser(self.client.getMyUserID())
            account = self.client.getMyUserAccount()
            data.update(nickname=tstr(user.szNickname), status=tstr(user.szStatusMsg),
                        account_type=account.uUserType, account_rights=account.uUserRights)
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')
        temporary.replace(path)

    def run(self):
        LOG.info('bot_start model=%s sdk=%s', self.config.model, tstr(self.tt.getVersion()))
        try:
            while not self.stop.is_set():
                now = time.monotonic()
                if not self.connecting and not self.authenticated and now >= self.next_connect:
                    self.core.connection = 'connecting'
                    self.connecting = bool(self.client.connect(self.tt.ttstr(self.config.host),
                        self.config.tcp_port, self.config.udp_port, bEncrypted=self.config.encrypted))
                    self.deadline = now + 30
                    if not self.connecting:
                        self.reconnect('connect_submit_failed')
                event = self.client.getMessage(100)
                if event.nClientEvent:
                    self.handle(event)
                if self.deadline and time.monotonic() > self.deadline:
                    self.reconnect('connection_or_login_timeout')
                self.queue_replies()
                self.flush(now)
                self.fragments = {k: v for k, v in self.fragments.items() if now - v[1] < 30}
                self.send_commands = {k: v for k, v in self.send_commands.items() if now - v < 60}
                if now >= self.next_snapshot:
                    self.core.prune()
                    self.snapshot()
                    self.next_snapshot = now + 10
        finally:
            self.client.disconnect()
            self.core.connection = 'stopped'
            self.snapshot()
            # The official wrapper owns the native instance and closes it in __del__.
            self.core.close()
            LOG.info('bot_stopped')


def tstr(value):
    return value.decode('utf-8', errors='replace') if isinstance(value, bytes) else value

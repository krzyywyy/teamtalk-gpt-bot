import io
import json
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from tt_gpt.api import APIError, Answer, OpenAIClient
from tt_gpt.core import BotCore, Message, Reply
from tt_gpt.teamtalk import TeamTalkBot


class FakeAPI:
    def __init__(self):
        self.calls = []
        self.gate = None
        self.error = None

    def answer(self, messages):
        self.calls.append(list(messages))
        if self.gate:
            self.gate.wait(2)
        if self.error:
            raise self.error
        return Answer('odpowiedź: ' + messages[-1]['content'], 10, 5, 0.01)


def msg(text='hej', user_id=1, username='alice', private=True, channel_id=7, admin=False, generation=0):
    return Message(user_id, username, channel_id, private, text, admin, generation)


def finish(core, expected=1):
    replies = []
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        replies.extend(core.poll())
        if not core.active and not core.waiting:
            return replies
        time.sleep(.002)
    raise AssertionError('worker did not finish')


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.api = FakeAPI()
        self.core = BotCore(self.api, 'gpt-6-luna')

    def tearDown(self):
        if self.api.gate:
            self.api.gate.set()
        self.core.close()

    def test_private_and_channel_routing(self):
        self.core.receive(msg('prywatna'))
        self.core.receive(msg('publiczna', private=False))
        replies = finish(self.core)
        self.assertEqual({(r.text, r.private) for r in replies},
            {('odpowiedź: prywatna', True), ('odpowiedź: publiczna', False)})

    def test_status_requires_server_admin_and_is_always_private(self):
        self.core.receive(msg('/status', private=False))
        self.core.receive(msg('/status', user_id=2, username='admin', private=False, admin=True))
        replies = finish(self.core)
        self.assertIn('tylko dla administratorów', replies[0].text)
        self.assertIn('gpt-6-luna', replies[1].text)
        self.assertTrue(all(r.private for r in replies))
        self.assertEqual(self.api.calls, [])

    def test_context_isolated_between_users_and_public_private(self):
        for message in (msg('sekret'), msg('publiczne', private=False),
                        msg('bob', user_id=2, username='bob'), msg('dalej')):
            self.core.receive(message)
            finish(self.core)
        self.assertEqual(len(self.api.calls[1]), 1)
        self.assertEqual(len(self.api.calls[2]), 1)
        self.assertEqual(len(self.api.calls[3]), 3)
        self.assertEqual(self.api.calls[3][0]['content'], 'sekret')

    def test_requests_in_same_conversation_are_serialized(self):
        self.api.gate = threading.Event()
        self.core.receive(msg('pierwsza'))
        self.core.receive(msg('druga'))
        self.assertEqual(len(self.core.active), 1)
        self.api.gate.set()
        finish(self.core)
        self.assertEqual(len(self.api.calls[1]), 3)

    def test_disconnect_discards_inflight_result(self):
        self.api.gate = threading.Event()
        self.core.receive(msg('sekret'))
        self.core.disconnected()
        self.api.gate.set()
        self.assertEqual(finish(self.core), [])
        self.assertEqual(self.core.history, {})

    def test_logout_discards_inflight_result(self):
        self.api.gate = threading.Event()
        self.core.receive(msg('sekret'))
        self.core.forget_user(1)
        self.api.gate.set()
        self.assertEqual(finish(self.core), [])

    def test_reset_discards_inflight_and_queued_messages(self):
        self.api.gate = threading.Event()
        self.core.receive(msg('sekret'))
        self.core.receive(msg('kolejny'))
        self.core.receive(msg('/reset'))
        self.api.gate.set()
        replies = finish(self.core)
        self.assertEqual(len(replies), 1)
        self.assertIn('usunięty', replies[0].text)
        self.assertEqual(self.core.history, {})

    def test_api_errors_are_controlled(self):
        self.api.error = APIError('insufficient_quota')
        self.core.receive(msg())
        replies = finish(self.core)
        self.assertIn('Spróbuj później', replies[0].text)
        self.assertEqual(self.core.last_error, 'insufficient_quota')
        self.assertEqual(self.core.stats['errors'], 1)

    def test_history_expires(self):
        now = [100]
        self.core.clock = lambda: now[0]
        self.core.receive(msg())
        finish(self.core)
        now[0] += 1801
        self.core.prune()
        self.assertEqual(self.core.history, {})

    def test_input_limit_never_calls_api(self):
        self.core.receive(msg('a' * 8001))
        self.assertIn('8000', finish(self.core)[0].text)
        self.assertEqual(self.api.calls, [])

    def test_rate_limit_and_command_flood_are_bounded(self):
        self.api.gate = threading.Event()
        for _ in range(200):
            self.core.receive(msg())
        self.assertLessEqual(len(self.core.waiting) + len(self.core.active), 10)
        for _ in range(200):
            self.core.receive(msg('/status'))
        self.assertLessEqual(len(self.core.reply_queue), 11)


class APITests(unittest.TestCase):
    def test_responses_payload_and_text_extraction(self):
        response = {'output': [{'type': 'reasoning'}, {'type': 'message', 'content':
            [{'type': 'output_text', 'text': 'cześć'}]}],
            'usage': {'input_tokens': 9, 'output_tokens': 3}}
        with patch('tt_gpt.api.urlopen') as mocked:
            mocked.return_value.__enter__.return_value = io.BytesIO(json.dumps(response).encode())
            answer = OpenAIClient('secret', 'gpt-6-luna').answer([{'role': 'user', 'content': 'hej'}])
            request = mocked.call_args.args[0]
            payload = json.loads(request.data)
        self.assertFalse(payload['store'])
        self.assertEqual(payload['model'], 'gpt-6-luna')
        self.assertEqual(answer.text, 'cześć')
        self.assertEqual(answer.output_tokens, 3)

    def test_quota_error_does_not_retry_or_expose_http_body(self):
        error = HTTPError('https://api.openai.com/v1/responses', 429, 'error', {},
                         io.BytesIO(b'{"error":{"code":"insufficient_quota","message":"secret"}}'))
        with patch('tt_gpt.api.urlopen', side_effect=error) as mocked:
            with self.assertRaises(APIError) as raised:
                OpenAIClient('secret', 'gpt-6-luna').answer([])
        self.assertEqual(str(raised.exception), 'insufficient_quota')
        self.assertEqual(mocked.call_count, 1)


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.bot = object.__new__(TeamTalkBot)
        self.bot.authenticated = True
        self.bot.core = SimpleNamespace(generation=0, receive=lambda m: self.received.append(m))
        self.received = []
        self.bot.fragments = {}
        self.bot.client = SimpleNamespace(getMyUserID=lambda: 50, getMyChannelID=lambda: 7,
            getUser=lambda uid: SimpleNamespace(nUserID=uid, szUsername=b'alice',
                                                uUserType=1, nChannelID=7))
        self.bot.tt = SimpleNamespace(UserType=SimpleNamespace(USERTYPE_ADMIN=2))

    def packet(self, text=b'hej', **changes):
        fields = dict(nFromUserID=1, nMsgType=1, nToUserID=50, nChannelID=0,
                      szMessage=text, bMore=False)
        fields.update(changes)
        return SimpleNamespace(**fields)

    def test_fragments_are_assembled_before_api(self):
        self.bot.receive(self.packet('żółć'.encode(), bMore=True))
        self.assertFalse(self.received)
        self.bot.receive(self.packet('🙂'.encode()))
        self.assertEqual(self.received[0].text, 'żółć🙂')

    def test_sdk_private_message_with_omitted_recipient_is_accepted(self):
        self.bot.receive(self.packet(b'private', nToUserID=0))
        self.assertEqual(len(self.received), 1)
        self.assertTrue(self.received[0].private)
        self.assertEqual(self.received[0].text, 'private')

    def test_oversized_fragments_are_rejected_as_one_message(self):
        for _ in range(20):
            self.bot.receive(self.packet(b'a' * 500, bMore=True))
        self.bot.receive(self.packet(b'koniec'))
        self.assertEqual(len(self.received), 1)
        self.assertGreater(len(self.received[0].text), 8000)

    def test_own_broadcast_custom_and_other_channel_messages_are_ignored(self):
        for changes in ({'nFromUserID': 50}, {'nMsgType': 3}, {'nMsgType': 4},
                        {'nMsgType': 2, 'nChannelID': 9}, {'nToUserID': 99}):
            self.bot.receive(self.packet(**changes))
        self.assertFalse(self.received)

    def test_reply_discarded_on_reconnect_or_reused_user_id(self):
        reply = Reply(msg(), 'sekret', True)
        self.assertTrue(self.bot.valid_recipient(reply))
        self.bot.core.generation = 1
        self.assertFalse(self.bot.valid_recipient(reply))
        self.bot.core.generation = 0
        self.bot.client.getUser = lambda _: SimpleNamespace(nUserID=1, szUsername=b'bob')
        self.assertFalse(self.bot.valid_recipient(reply))

    def test_admin_permission_comes_from_sdk_not_message_content(self):
        self.bot.receive(self.packet(b'/status'))
        self.assertFalse(self.received[0].admin)
        self.bot.client.getUser = lambda uid: SimpleNamespace(nUserID=uid, szUsername=b'admin', uUserType=2)
        self.bot.receive(self.packet(b'/status'))
        self.assertTrue(self.received[1].admin)

    def test_connection_is_held_during_authentication(self):
        events = SimpleNamespace(CLIENTEVENT_CON_SUCCESS=10)
        self.bot.tt.ClientEvent = events
        self.bot.connecting = False
        self.bot.login = lambda: None
        self.bot.handle(SimpleNamespace(nClientEvent=10))
        self.assertTrue(self.bot.connecting)

    def test_invalid_account_uses_fallback_password(self):
        events = SimpleNamespace(CLIENTEVENT_CON_SUCCESS=10, CLIENTEVENT_CON_FAILED=20,
            CLIENTEVENT_CON_LOST=30, CLIENTEVENT_CON_CRYPT_ERROR=15,
            CLIENTEVENT_CMD_MYSELF_LOGGEDIN=230, CLIENTEVENT_CMD_SUCCESS=220,
            CLIENTEVENT_CMD_ERROR=210)
        self.bot.tt.ClientEvent = events
        self.bot.tt.ClientError = SimpleNamespace(CMDERR_INVALID_ACCOUNT=2002)
        self.bot.login_command = 12
        self.bot.passwords = ['first', 'fallback']
        self.bot.password_index = 0
        attempts = []
        self.bot.login = lambda: attempts.append(self.bot.password_index)
        self.bot.handle(SimpleNamespace(nClientEvent=210, nSource=12,
                                        clienterrormsg=SimpleNamespace(nErrorNo=2002)))
        self.assertEqual(attempts, [1])


if __name__ == '__main__':
    unittest.main()

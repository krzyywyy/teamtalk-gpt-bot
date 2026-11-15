from collections import deque
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from test_bot import FakeAPI, finish, msg
from tt_gpt.core import BotCore, Reply
from tt_gpt.config import Config
from tt_gpt.settings import BotSettings
from tt_gpt.teamtalk import TeamTalkBot


class ChannelControlTests(unittest.TestCase):
    def setUp(self):
        self.api = FakeAPI()
        self.core = BotCore(self.api, 'gpt-6-luna')

    def tearDown(self):
        if self.api.gate:
            self.api.gate.set()
        self.core.close()

    def test_non_admin_cannot_disable_channel(self):
        self.core.receive(msg('/channel off'))
        replies = finish(self.core)
        self.assertTrue(self.core.channel_replies_enabled)
        self.assertIn('tylko dla administratorów', replies[0].text)
        self.assertTrue(replies[0].private)

    def test_admin_must_use_private_message(self):
        self.core.receive(msg('/channel off', admin=True, private=False))
        self.assertTrue(self.core.channel_replies_enabled)
        self.assertIn('prywatnej', finish(self.core)[0].text)

    def test_disable_channel_keeps_private_api_replies_working(self):
        self.core.receive(msg('/channel off', admin=True))
        self.core.receive(msg('public ignored', private=False))
        self.core.receive(msg('private accepted'))
        replies = finish(self.core)
        self.assertFalse(self.core.channel_replies_enabled)
        self.assertEqual(len(self.api.calls), 1)
        self.assertEqual(self.api.calls[0][-1]['content'], 'private accepted')
        self.assertTrue(all(r.private for r in replies))

    def test_reenable_accepts_channel_messages(self):
        self.core.receive(msg('/channel off', admin=True))
        self.core.receive(msg('/channel on', admin=True))
        self.core.receive(msg('public accepted', private=False))
        replies = finish(self.core)
        self.assertTrue(any(not r.private for r in replies))

    def test_disabling_discards_queued_and_inflight_channel_responses(self):
        self.api.gate = threading.Event()
        self.core.receive(msg('first', private=False))
        deadline = time.monotonic() + 1
        while not self.api.calls and time.monotonic() < deadline:
            time.sleep(.002)
        self.assertEqual(len(self.api.calls), 1)
        self.core.receive(msg('queued', private=False))
        self.core.receive(msg('/channel off', admin=True))
        self.core.receive(msg('/channel on', admin=True))
        self.api.gate.set()
        replies = finish(self.core)
        self.assertTrue(all(r.private for r in replies))
        self.assertEqual(self.core.history, {})
        self.assertEqual(len(self.api.calls), 1)

    def test_status_shows_current_channel_mode(self):
        self.core.receive(msg('/channel off', admin=True))
        self.assertIn('Channel replies: disabled', self.core.status())
        self.core.receive(msg('/channel status', admin=True))
        self.assertIn('wyłączone', finish(self.core)[-1].text)

    def test_invalid_command_does_not_change_mode(self):
        self.core.receive(msg('/channel off extra', admin=True))
        self.assertTrue(self.core.channel_replies_enabled)
        self.assertIn('Użycie', finish(self.core)[0].text)

    def test_failed_save_does_not_acknowledge_success(self):
        with patch.object(self.core.settings, 'set_channel_replies', side_effect=OSError):
            self.core.receive(msg('/channel off', admin=True))
        self.assertTrue(self.core.channel_replies_enabled)
        self.assertIn('Nie udało', finish(self.core)[0].text)

    def test_transport_purges_public_messages_already_waiting_to_send(self):
        bot = object.__new__(TeamTalkBot)
        bot.core = SimpleNamespace(channel_replies_enabled=False, poll=lambda: [])
        bot.outbound = deque([(Reply(msg(private=False), 'public', False), object()),
                              (Reply(msg(), 'private', True), object())])
        bot.queue_replies()
        self.assertEqual(len(bot.outbound), 1)
        self.assertTrue(bot.outbound[0][0].private)


class SettingsTests(unittest.TestCase):
    def test_configuration_repr_does_not_include_credentials(self):
        config = Config('private-api', 'private-license-name', 'private-license-key',
                        'private-user', 'private-password', admin_key='private-admin')
        self.assertNotIn('private-', repr(config))

    def test_setting_survives_new_instance(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'settings.json'
            settings = BotSettings(path)
            self.assertTrue(settings.channel_replies_enabled)
            settings.set_channel_replies(False)
            reloaded = BotSettings(path)
            self.assertFalse(reloaded.channel_replies_enabled)
            reloaded.set_channel_replies(True)
            self.assertTrue(BotSettings(path).channel_replies_enabled)

    def test_failed_atomic_write_preserves_old_file_and_live_mode(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'settings.json'
            settings = BotSettings(path)
            settings.set_channel_replies(False)
            with patch('tt_gpt.settings.os.replace', side_effect=OSError):
                with self.assertRaises(OSError):
                    settings.set_channel_replies(True)
            self.assertFalse(settings.channel_replies_enabled)
            self.assertFalse(BotSettings(path).channel_replies_enabled)
            self.assertEqual(len(list(Path(temporary).iterdir())), 1)

    def test_invalid_setting_is_not_silently_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'settings.json'
            path.write_text('{"version":1,"channel_replies_enabled":"false"}')
            with self.assertRaises(ValueError):
                BotSettings(path)


if __name__ == '__main__':
    unittest.main()

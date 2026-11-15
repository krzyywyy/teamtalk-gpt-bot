"""Persist operational settings without storing conversations or credentials."""
import json
import os
from pathlib import Path
import tempfile


class BotSettings:
    def __init__(self, path=None):
        self.path = Path(path) if path is not None else None
        self.channel_replies_enabled = True
        if self.path is not None and self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding='utf-8'))
                if data.get('version') != 1 or type(data.get('channel_replies_enabled')) is not bool:
                    raise ValueError
                self.channel_replies_enabled = data['channel_replies_enabled']
            except (ValueError, TypeError, AttributeError):
                raise ValueError('Invalid bot settings file') from None

    def set_channel_replies(self, enabled):
        if type(enabled) is not bool:
            raise ValueError('Channel reply setting must be boolean')
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            descriptor, temporary = tempfile.mkstemp(prefix='.settings-', dir=self.path.parent)
            try:
                with os.fdopen(descriptor, 'w', encoding='utf-8') as output:
                    json.dump({'version': 1, 'channel_replies_enabled': enabled}, output)
                    output.write('\n')
                os.replace(temporary, self.path)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
        # A failed write must leave the currently active setting unchanged.
        self.channel_replies_enabled = enabled

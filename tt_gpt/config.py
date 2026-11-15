from dataclasses import dataclass, field
from pathlib import Path
import os


def load_env(path):
    """Read literal KEY=value pairs; never execute shell syntax."""
    for line in Path(path).read_text(encoding='utf-8-sig').splitlines():
        line = line.strip()
        if line and not line.startswith('#'):
            key, value = line.split('=', 1)
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1]
            os.environ.setdefault(key.strip(), value)


@dataclass(frozen=True)
class Config:
    api_key: str = field(repr=False)
    license_name: str = field(repr=False)
    license_key: str = field(repr=False)
    username: str = field(repr=False)
    password: str = field(repr=False)
    fallback_password: str = field(default='', repr=False)
    model: str = 'gpt-6-luna'
    host: str = 'teamtalk.example.com'
    tcp_port: int = 10333
    udp_port: int = 10333
    nickname: str = 'Chat GPT'
    status: str = 'If you need help, send me a message.'
    channel: str = '/'
    channel_password: str = ''
    encrypted: bool = False
    data_dir: Path = Path('data')
    admin_key: str = field(default='', repr=False)
    cost_project_id: str = field(default='', repr=False)

    @classmethod
    def from_env(cls):
        def required(name):
            value = os.environ.get(name, '')
            if not value:
                raise ValueError(f'Missing required configuration: {name}')
            return value
        return cls(
            api_key=required('OPENAI_API_KEY'),
            license_name=required('TT_LICENSE_NAME'),
            license_key=required('TT_LICENSE_KEY'),
            username=required('TT_USERNAME'),
            password=required('TT_PASSWORD'),
            fallback_password=os.environ.get('TT_PASSWORD_FALLBACK', ''),
            model=os.environ.get('OPENAI_MODEL', 'gpt-6-luna'),
            host=os.environ.get('TT_HOST', 'teamtalk.example.com'),
            tcp_port=int(os.environ.get('TT_TCP_PORT', '10333')),
            udp_port=int(os.environ.get('TT_UDP_PORT', '10333')),
            nickname=os.environ.get('TT_NICKNAME', 'Chat GPT'),
            status=os.environ.get('TT_STATUS', 'If you need help, send me a message.'),
            channel=os.environ.get('TT_CHANNEL', '/'),
            channel_password=os.environ.get('TT_CHANNEL_PASSWORD', ''),
            encrypted=os.environ.get('TT_ENCRYPTED', 'false').lower() == 'true',
            data_dir=Path(os.environ.get('BOT_DATA_DIR', 'data')),
            admin_key=os.environ.get('OPENAI_ADMIN_KEY', ''),
            cost_project_id=os.environ.get('OPENAI_COST_PROJECT_ID', ''),
        )

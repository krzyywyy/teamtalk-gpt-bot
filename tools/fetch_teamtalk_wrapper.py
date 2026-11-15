"""Fetch the official v5.23 Python wrapper; BearWare's SDK license applies."""
import hashlib
from pathlib import Path
from urllib.request import Request, urlopen

URL = 'https://raw.githubusercontent.com/BearWare/TeamTalk5/v5.23/Library/TeamTalkPy/TeamTalk5.py'
SHA256 = 'f0286737337c8d6d91b71e63857e1e688062e61ae8f889300fe28ca89dfba013'
DESTINATION = Path(__file__).resolve().parents[1] / 'vendor/TeamTalk5.py'


def main():
    if DESTINATION.exists():
        if hashlib.sha256(DESTINATION.read_bytes()).hexdigest() == SHA256:
            print('Official TeamTalk v5.23 wrapper is already installed.')
            return
        raise SystemExit('A different wrapper already exists. Back it up or remove it before downloading.')
    request = Request(URL, headers={'User-Agent': 'teamtalk-gpt-bot/1.0'})
    with urlopen(request, timeout=30) as response:
        payload = response.read()
    if hashlib.sha256(payload).hexdigest() != SHA256:
        raise SystemExit('Wrapper checksum mismatch; no file was installed.')
    DESTINATION.parent.mkdir(parents=True, exist_ok=True)
    temporary = DESTINATION.with_suffix('.tmp')
    temporary.write_bytes(payload)
    temporary.replace(DESTINATION)
    print('Installed the official TeamTalk v5.23 wrapper with verified SHA-256.')
    print('Install a matching native library and configure your own BearWare SDK license.')


if __name__ == '__main__':
    main()

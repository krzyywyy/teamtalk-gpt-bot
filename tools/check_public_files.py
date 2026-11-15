"""Check Git-tracked files for common accidentally committed credentials."""
import argparse
from pathlib import Path, PurePosixPath
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = (
    re.compile(rb'sk-(?:proj-)?[A-Za-z0-9_-]{24,}'),
    re.compile(rb'(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})'),
    re.compile(rb'-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----'),
    re.compile(rb'C:\\Users\\[^\\\r\n]+\\', re.IGNORECASE),
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--staged', action='store_true', help='Read the Git index instead of working files')
    args = parser.parse_args()
    result = subprocess.run(['git', 'ls-files', '-z'], cwd=ROOT, check=True, capture_output=True)
    paths = [name.decode('utf-8') for name in result.stdout.split(b'\0') if name]
    if not paths:
        raise SystemExit('No tracked files. Stage the intended public files before scanning.')
    problems = []
    for name in paths:
        path = PurePosixPath(name)
        forbidden = (path.name.startswith('.env') and path.name != '.env.example') or any(
            part in {'.secrets', '.ssh', 'data', 'logs'} for part in path.parts)
        forbidden = forbidden or (path.parts[0] == 'vendor' and name != 'vendor/README.md')
        if forbidden:
            problems.append((name, 'private or third-party runtime file'))
            continue
        if args.staged:
            content = subprocess.run(['git', 'show', ':' + name], cwd=ROOT,
                check=True, capture_output=True).stdout
        else:
            content = (ROOT / name).read_bytes()
        if any(pattern.search(content) for pattern in PATTERNS):
            problems.append((name, 'possible credential or personal path'))
    if problems:
        for name, category in problems:
            print(f'FAIL: {name}: {category}')
        raise SystemExit(1)
    print(f'PASS: {len(paths)} tracked files checked; no matching credentials or private paths.')


if __name__ == '__main__':
    main()

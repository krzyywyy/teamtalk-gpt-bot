import argparse
import logging
from logging.handlers import RotatingFileHandler
import signal
import sys
import threading

from .api import APIError, OpenAIClient
from .config import Config, load_env
from .core import BotCore
from .teamtalk import TeamTalkBot, sdk, tstr


def main():
    parser = argparse.ArgumentParser(description='TeamTalk GPT text bot')
    parser.add_argument('--env', help='Path to a protected environment file')
    parser.add_argument('--check', action='store_true', help='Check SDK and OpenAI without connecting to TeamTalk')
    args = parser.parse_args()
    if args.env:
        load_env(args.env)
    config = Config.from_env()
    config.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    log_dir = config.data_dir / 'logs'
    log_dir.mkdir(exist_ok=True, mode=0o700)
    handlers = [logging.StreamHandler(), RotatingFileHandler(log_dir / 'bot.log',
                maxBytes=2_000_000, backupCount=5, encoding='utf-8')]
    logging.basicConfig(level=logging.INFO, handlers=handlers,
                        format='%(asctime)s %(levelname)s %(name)s %(message)s')
    api = OpenAIClient(config.api_key, config.model)
    if args.check:
        tt = sdk(config)
        answer = api.answer([{'role': 'user', 'content': 'Reply with the single word OK.'}])
        print(f'SDK {tstr(tt.getVersion())}: OK; API {config.model}: {answer.text}')
        return
    stop = threading.Event()
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda *_: stop.set())
    core = BotCore(api, config.model)
    try:
        TeamTalkBot(config, core, stop).run()
    finally:
        if not core.closed:
            core.close()


if __name__ == '__main__':
    try:
        main()
    except (ValueError, APIError) as error:
        # These exceptions contain only controlled configuration names/error categories.
        logging.error('startup_failed %s', error)
        sys.exit(78)
    except Exception as error:
        # Avoid logging HTTP bodies, environment values, or secret-bearing exceptions.
        logging.error('bot_fatal exception_type=%s', type(error).__name__)
        sys.exit(1)

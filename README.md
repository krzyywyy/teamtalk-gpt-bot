# TeamTalk GPT Bot

[![Tests](https://github.com/krzyywyy/teamtalk-gpt-bot/actions/workflows/tests.yml/badge.svg)](https://github.com/krzyywyy/teamtalk-gpt-bot/actions/workflows/tests.yml)
![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-blue)
[![MIT license](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**English** · [Polski](README.pl.md)

A text assistant for TeamTalk servers, powered by the OpenAI Responses API.
Send the bot a private message or write in its current channel to receive a reply.
The default model is **GPT-6 Luna** (`gpt-6-luna`), configurable through the environment.

Designed for a Linux server: automatic reconnects, a systemd service, bounded request
queues, rotating logs, and a private administrator status command.

## Features

- Automatic replies to private messages and messages in the bot's current channel.
- Separate conversation context for each user and for private versus channel messages.
- Replies in the language of the incoming message, with plain text suitable for screen readers.
- `/status` restricted to TeamTalk server administrators, always answered privately.
- `/reset` to clear the current conversation and `/help` for a short guide.
- UTF-8 message fragmentation and reassembly, including Polish text and emoji.
- Two concurrent API requests, sequential requests within each conversation, and rate limits.
- Reconnects with a 3–60 second backoff, graceful shutdown, and systemd autostart.
- Logs and a machine-readable status file without message contents or credentials.
- Python standard library only; no pip dependencies for the bot or its unit tests.

The bot handles text. It does not listen to audio, speak, browse the web, or run shell commands.
It answers **all messages in its current channel**, without requiring a mention.
It does not monitor every channel on the server. Local help/error notices are currently in Polish;
model replies follow the user's language, and the administrator status report is in English.

## Requirements

- Python **3.12 or later**.
- Linux with a compatible TeamTalk native library; the verified runtime is Ubuntu 24 x86_64.
- A TeamTalk account allowed to view users, join the chosen channel, and send private/channel messages.
- An OpenAI API key with access to the configured model and available API credit.
- Your own valid **BearWare TeamTalk SDK registration name and license key**.

The verified native combination is TeamTalk v5.23 and its v5.23 Python wrapper.
An ordinary bot account is sufficient when it has the required rights; the bot does not need
server administrator privileges. `/status` checks the requesting user's server administrator flag.

## Quick start

### 1. Get the source and wrapper

```sh
git clone https://github.com/krzyywyy/teamtalk-gpt-bot.git
cd teamtalk-gpt-bot
python3 tools/fetch_teamtalk_wrapper.py
```

The helper downloads the official, version-pinned Python wrapper and verifies its SHA-256.
It does not download or supply a license key. See [the TeamTalk runtime notes](vendor/README.md).

### 2. Install the native TeamTalk library

Obtain a matching Linux library from [BearWare](https://bearware.dk/?page_id=419)
or its [official TeamTalk distribution](https://bearware.dk/?page_id=353), under the
applicable SDK license. Place `libTeamTalk5.so` in `vendor/`:

```sh
cp /path/to/libTeamTalk5.so vendor/
ldd vendor/libTeamTalk5.so
```

Install any missing system dependencies reported by `ldd`. Match the library to your OS
and CPU architecture. A library built for a newer Linux distribution may require a newer glibc.

### 3. Configure your own accounts

```sh
cp .env.example .env
chmod 600 .env
```

Edit `.env`: set the OpenAI key, TeamTalk hostname and ports, account credentials,
and BearWare registration details. `teamtalk.example.com` and the credentials in the example
are placeholders. Use your server's actual TCP and UDP ports and its encryption setting.

### 4. Check and run

```sh
python3 -m unittest discover -s tests -v
LD_LIBRARY_PATH="$PWD/vendor" python3 -m tt_gpt --env .env --check
LD_LIBRARY_PATH="$PWD/vendor" python3 -m tt_gpt --env .env
```

`--check` verifies the SDK license and C/Python structure compatibility, then sends a small
request to OpenAI. It does **not** connect to TeamTalk and may incur a small API charge.
The normal command logs in, sets the nickname/status, and joins the configured channel.
Press Ctrl+C to stop a foreground run.

## Configuration

Settings come from environment variables or the file passed with `--env`.
Existing process environment variables take precedence over values loaded with `--env`.
The file uses literal `KEY=value` lines, not executable shell syntax.

| Variable | Purpose | Default / example |
| --- | --- | --- |
| `OPENAI_API_KEY` | Your OpenAI API key | Required |
| `OPENAI_MODEL` | Responses API model | `gpt-6-luna` |
| `TT_HOST` | TeamTalk server hostname | `teamtalk.example.com` |
| `TT_TCP_PORT` | TeamTalk TCP port | `10333` |
| `TT_UDP_PORT` | TeamTalk UDP port | `10333` |
| `TT_ENCRYPTED` | Whether the server uses encrypted TeamTalk connections | `false` |
| `TT_USERNAME` | Bot account username | Required |
| `TT_PASSWORD` | Bot account password | Required |
| `TT_PASSWORD_FALLBACK` | Optional second password, tried only if the first is rejected | Empty |
| `TT_LICENSE_NAME` | BearWare SDK registration name | Required |
| `TT_LICENSE_KEY` | BearWare SDK license key | Required |
| `TT_NICKNAME` | Visible nickname | `Chat GPT` |
| `TT_STATUS` | Visible status message | `If you need help, send me a message.` |
| `TT_CHANNEL` | Channel path to join after login/reconnect | `/` |
| `TT_CHANNEL_PASSWORD` | Password for the selected channel | Empty |
| `BOT_DATA_DIR` | Runtime logs and status file | `data` for manual runs |

An administrator can move the bot to another channel. It will answer there until a reconnect
or restart, when it returns to `TT_CHANNEL`.

## Chat commands

| Command | Who can use it? | Behavior |
| --- | --- | --- |
| `/help` | Anyone | Sends a short private guide. |
| `/reset` | Anyone | Clears the context of the conversation where it was issued and discards pending/in-flight results for it. Confirmation is private. |
| `/status` | Server administrators | Sends connection state, model, uptime, queue size, reply/error counts, API token counters, last API duration, and the latest error. Always private. |

Administrator access is checked using the SDK's `USERTYPE_ADMIN` flag, not a nickname
or text supplied by a user. A channel operator alone does not qualify.
Token counters cover the current bot process; they are not an account billing report.

## Install as a systemd service

Complete the SDK setup first. Run the installer from your source checkout:

```sh
sudo sh deploy/install.sh
sudoedit /etc/teamtalk-gpt-bot/bot.env
sudo systemctl enable --now tt-gpt
```

The installer creates a dedicated `tt-gpt` system account and installs the application in
`/opt/teamtalk-gpt-bot`. It creates a placeholder configuration with mode `0600` if none exists,
preserves an existing configuration, and leaves starting the service to the final command above.
It does not copy your checkout's `.env` automatically.

The service reads `/etc/teamtalk-gpt-bot/bot.env`. Fill in your real settings there.
Leave `BOT_DATA_DIR` unset in that file to use the unit's writable state directory,
`/var/lib/teamtalk-gpt-bot`. The unit restricts filesystem writes, runs without root privileges,
and disables unnecessary audio hardware discovery for this text bot.

```sh
sudo systemctl status tt-gpt
sudo systemctl restart tt-gpt
sudo systemctl stop tt-gpt
sudo journalctl -u tt-gpt -n 100 --no-pager
sudo tail -n 100 /var/lib/teamtalk-gpt-bot/logs/bot.log
sudo cat /var/lib/teamtalk-gpt-bot/status.json
```

After changing configuration, restart the service. For updates, pull the reviewed source,
run `sudo sh deploy/install.sh` again, and restart `tt-gpt`.
Invalid account/channel/license configuration can stop the bot with exit code **78**.
systemd does not endlessly restart that exit code; fix the configuration and restart manually.
Other process failures are restarted, and temporary TeamTalk connection loss is handled by the bot.

## Privacy, logs, and limits

- Requests are sent to the OpenAI API with `store=false`; OpenAI's own data policies still apply.
- Conversation history stays in RAM: up to six recent question/answer pairs, bounded to roughly
  24,000 characters, and expires after 30 minutes without a completed exchange.
- Private conversations and channel conversations use separate contexts, with each user isolated.
  Logging out clears that user's context; restarting the bot clears all history.
- Logs include operational events and numeric user/channel identifiers, but no message text,
  API keys, passwords, or SDK registration keys. Files rotate at 2 MB with five backups.
- `status.json` is updated about every 10 seconds and contains operational metadata.
- API limits: 8,000 characters per question, 10 questions/minute per user, 30 questions/minute
  overall, two simultaneous API requests, and at most 24 queued/active requests.
- Commands have a separate limit of 10/minute per user. API retries are bounded; quota errors
  are returned without retrying. Replies are capped at 1,800 output tokens and 7,000 characters.

These rate limits do not create a monetary spending cap. Set an appropriate budget in your OpenAI
project. Do not commit real configuration: `.env`, `.secrets/`, runtime data, and SDK files are ignored.

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| `libTeamTalk5.so` cannot be loaded | Library is in `vendor/`, `LD_LIBRARY_PATH` is set, and `ldd` has no missing dependencies. |
| SDK rejected the license | Correct BearWare registration name/key and a compatible SDK edition/version. |
| TeamTalk error `2002` | Account username/password and account availability on the selected server. |
| Bot is online but cannot answer some users | Account rights to view users and send private/channel messages. |
| No channel replies | Bot is in that channel and has permission to send channel messages. |
| `model_not_found` | Model ID and access granted to your API project. |
| `insufficient_quota` | API credit/billing for the project. |
| Service stops with code `78` | Fix configuration, inspect logs, and restart the service. |

## Development

```sh
python3 -m unittest discover -s tests -v
python3 -m compileall -q tt_gpt tools tests
python3 tools/check_public_files.py
```

The unit tests use fake API responses and SDK objects, so they require no credentials,
native SDK, or running server. GitHub Actions runs them on Linux and Windows with Python
3.12 and 3.13, and checks tracked files for common credential patterns and private paths.
The public-file check is a useful guard, not a substitute for reviewing changes before publishing.

```text
tt_gpt/     Bot configuration, Responses API client, request queue, TeamTalk transport
tests/      Unit tests for routing, permissions, privacy, errors, limits, and message fragments
deploy/     Generic Linux installer, systemd unit, and headless audio configuration
tools/      Official wrapper downloader and tracked-file checks
vendor/     Local TeamTalk runtime; only its setup notes are tracked
```

## License and acknowledgments

The bot's original source code is licensed under [MIT](LICENSE).
**The TeamTalk SDK is a separate BearWare product and is not covered by this MIT license.**
Its wrapper and native libraries are installed separately and are not redistributed here.

- [TeamTalk SDK and license information](https://bearware.dk/?page_id=419)
- [Official TeamTalk Python wrapper](https://github.com/BearWare/TeamTalk5/tree/v5.23/Library/TeamTalkPy)
- [OpenAI Responses API](https://developers.openai.com/api/docs/guides/text)
- [GPT-6 Luna model](https://developers.openai.com/api/docs/models/gpt-6-luna)

This is an independent project, not an official OpenAI or BearWare application.

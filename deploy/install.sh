#!/bin/sh
# Install reviewed local files. Credentials and starting the service are separate steps.
set -eu

if [ "$(id -u)" -ne 0 ]; then
    echo 'Run this installer as root: sudo sh deploy/install.sh' >&2
    exit 1
fi
source_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
target_dir=/opt/teamtalk-gpt-bot

for required in vendor/TeamTalk5.py vendor/libTeamTalk5.so; do
    if [ ! -f "$source_dir/$required" ]; then
        echo "Missing $required. Follow the SDK setup in README.md first." >&2
        exit 1
    fi
done
if ! id tt-gpt >/dev/null 2>&1; then
    useradd --system --user-group --home-dir /var/lib/teamtalk-gpt-bot --shell /usr/sbin/nologin tt-gpt
fi
install -d -m 0755 "$target_dir" "$target_dir/tt_gpt" "$target_dir/vendor" "$target_dir/deploy"
install -d -m 0700 /etc/teamtalk-gpt-bot
install -m 0644 "$source_dir"/tt_gpt/*.py "$target_dir/tt_gpt/"
install -m 0644 "$source_dir/vendor/TeamTalk5.py" "$target_dir/vendor/"
for library in "$source_dir"/vendor/libTeamTalk5.so*; do
    install -m 0644 "$library" "$target_dir/vendor/"
done
install -m 0644 "$source_dir/deploy/asound.conf" "$target_dir/deploy/"
if [ ! -f /etc/teamtalk-gpt-bot/bot.env ]; then
    install -m 0600 "$source_dir/.env.example" /etc/teamtalk-gpt-bot/bot.env
fi
install -m 0644 "$source_dir/deploy/tt-gpt.service" /etc/systemd/system/tt-gpt.service
systemctl daemon-reload
echo 'Installed. Edit /etc/teamtalk-gpt-bot/bot.env with your own settings.'
echo 'Then start and enable: sudo systemctl enable --now tt-gpt'

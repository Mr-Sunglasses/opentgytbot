# Automating cookie refresh

The bot reads `cookies.txt` **on every download** (`download_queue.py:190`), so
updating that file on the server is enough — no bot restart needed.

## One-time: run the sync script from your PC

```bash
pip install yt-dlp paramiko

python tools/sync_cookies.py \
  --browser chrome \
  --server your-host.example.com \
  --user ubuntu \
  --key ~/.ssh/id_ed25519 \
  --remote /app/cookies.txt
```

- `--browser` must match the browser where your YouTube session is still logged in.
- `--remote` must match `COOKIES_FILE` in the bot's `.env` on the server.

If the bot runs as a systemd unit and you want a restart too:

```bash
... --restart-service youtube-bot
```

## Schedule it (so you never touch it again)

**Linux (cron)** — run twice a day:

```
0 */12 * * * cd /path/to/repo && python tools/sync_cookies.py --server your-host --user ubuntu --remote /app/cookies.txt >> /var/log/sync_cookies.log 2>&1
```

**macOS (launchd)** or **Windows (Task Scheduler)** — same command, triggered daily.

## How it works

1. `yt-dlp --cookies-from-browser` pulls the live session cookies straight from
   your logged-in browser (Chrome/Firefox/Edge/Brave/Opera/Vivaldi).
2. The file is uploaded to the server over SFTP using your SSH key.
3. Next download picks up the fresh cookies automatically.

## Requirements

- The browser session must **stay logged in** to YouTube (keep the browser open
  or keep the profile). YouTube's login cookies expire after ~48h, so a twice-daily
  refresh is plenty.
- Your PC needs `yt-dlp` and `paramiko`. The script runs locally and never
  exposes your browser data to the server.

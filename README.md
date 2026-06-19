# YouTube Shorts Telegram Bot

<p align="center">
  <a href="https://t.me/opentgytbot">
    <img src="https://img.shields.io/badge/Use%20Bot-Open%20Telegram-blue" alt="Use Bot">
  </a>
</p>

----

<p align="center">
  <img src="./assets/freedom.png" width="400" height="600">
</p>

A Telegram bot that downloads YouTube Shorts with a queue system supporting 5 concurrent downloads.

## Features

- 📥 Download YouTube Shorts via Telegram
- 📊 Queue management with status tracking
- 🚀 5 concurrent download workers
- ✅ Automatic cleanup after sending
- 🛡️ Error handling and retry logic
- 📝 Comprehensive logging

## Setup

### Method 1: Using uv (Recommended)

1. Install dependencies with uv:
```bash
uv sync
```

2. Create a `.env` file from the example:
```bash
cp .env.example .env
```

3. Get a bot token from [@BotFather](https://t.me/botfather) and update `.env`

4. Run bot:
```bash
uv run python main.py
```

### Method 2: Using Docker

1. Create a `.env` file from the example:
```bash
cp .env.example .env
```

2. Get a bot token from [@BotFather](https://t.me/botfather) and update `.env`

3. Build the Docker image:
```bash
docker build -t youtube-shorts-bot .
```

4. Run the container:
```bash
docker run -d \
  --name youtube-shorts-bot \
  --env-file .env \
  -v $(pwd)/downloads:/app/downloads \
  youtube-shorts-bot
```

5. View logs:
```bash
docker logs -f youtube-shorts-bot
```

6. Stop the container:
```bash
docker stop youtube-shorts-bot
docker rm youtube-shorts-bot
```

## Usage

- Send a YouTube Shorts URL to download it
- `/status` - Check queue status
- `/cancel` - Cancel your downloads

## Configuration

- `TELEGRAM_BOT_TOKEN` - Your bot token
- `MAX_CONCURRENT_DOWNLOADS` - Number of concurrent downloads (default: 5)
- `MAX_VIDEO_SIZE_MB` - Maximum video size in MB (default: 50)
- `LOG_LEVEL` - Logging level (default: INFO)

## Important Notes

### Telegram Limits
Due to Telegram's restrictions, files must be under 50MB to be sent.

### YouTube Bot Detection ⚠️
YouTube aggressively blocks requests from cloud servers and data centers. If you encounter "Sign in to confirm you're not a bot" or "YouTube requires verification" errors:

#### 1. Use Cookies (Recommended)
Providing cookies from a logged-in YouTube account is the most reliable way to bypass detection.

1. Install the [Get cookies.txt LOCALLY](https://chrome.google.com/webstore/detail/get-cookiestxt-locally/ccmclabmjjnoobemgongeiclepgejclj) extension in your browser.
2. Go to YouTube and log in.
3. Use the extension to export cookies for YouTube as `cookies.txt`.
4. Place the `cookies.txt` file in the bot's root directory.
5. The bot will automatically detect and use it.

#### 2. Environment Considerations
| Environment | Works? | Notes |
|-------------|--------|-------|
| **Home server / Residential IP** | ✅ Yes | Recommended for self-hosting |
| **Cloud VPS (AWS, Hetzner, etc.)** | ❌ Often blocked | Data center IPs are flagged |
| **Raspberry Pi at home** | ✅ Yes | Great low-power option |

**Recommendation:** Run this bot on a home server or any device with a residential internet connection for best results.

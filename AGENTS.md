# AI Agent Instructions

## Project Overview

This is a Python-based Telegram bot that downloads YouTube Shorts with a queue management system. The bot uses `uv` as the package manager and features rate limiting, progress tracking, and proper video format handling for Telegram compatibility.

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│    main.py      │────▶│     bot.py      │────▶│ download_queue  │
│   (Entry Point) │     │  (Telegram Bot) │     │    (Workers)    │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                               │                        │
                               ▼                        ▼
                        ┌─────────────────┐     ┌─────────────────┐
                        │   config.py     │     │    yt-dlp       │
                        │ (Pydantic)      │     │  (Downloads)    │
                        └─────────────────┘     └─────────────────┘
```

### Key Components

| File | Purpose |
|------|---------|
| `main.py` | Entry point, starts the bot |
| `bot.py` | Telegram handlers, rate limiting, URL validation |
| `download_queue.py` | Async queue with ThreadPoolExecutor for downloads |
| `config.py` | Pydantic-settings based configuration with validation |
| `logger.py` | Centralized logging configuration |

## Environment Setup

**IMPORTANT: Always use `uv` for package management and running the project.**

### Installing Dependencies

```bash
uv sync              # Install all dependencies
uv sync --all-extras # Install dependencies with dev tools (ruff, mypy)
```

### Running the Project

```bash
uv run python main.py
# OR
./start.sh
```

### Running Linter

```bash
uv run ruff check .
uv run ruff check . --fix  # Auto-fix issues
```

### Type Checking

```bash
uv run mypy .
```

## Configuration

Configuration is managed via `pydantic-settings` in `config.py`. All settings can be overridden via environment variables or `.env` file.

| Variable | Default | Description |
|----------|---------|-------------|
| `TELEGRAM_BOT_TOKEN` | *required* | Bot token from @BotFather |
| `DOWNLOAD_DIR` | `downloads` | Temporary download directory |
| `MAX_CONCURRENT_DOWNLOADS` | `5` | Number of worker threads (1-20) |
| `MAX_VIDEO_SIZE_MB` | `50` | Max file size in MB (Telegram limit) |
| `RATE_LIMIT_PER_USER` | `10` | Max requests per user per minute |
| `LOG_LEVEL` | `INFO` | Logging level (DEBUG/INFO/WARNING/ERROR) |

### Example `.env` file

```bash
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
DOWNLOAD_DIR=downloads
MAX_CONCURRENT_DOWNLOADS=5
MAX_VIDEO_SIZE_MB=50
RATE_LIMIT_PER_USER=10
LOG_LEVEL=INFO
```

## Code Conventions

1. **Use `uv run` for all Python commands** - Ensures correct virtual environment
2. **Follow PEP 8** - Code must pass `ruff check` with no errors
3. **Type hints** - All functions must have proper type annotations (enforced by mypy)
4. **Async/await** - The bot is fully asynchronous, use `async/await` patterns
5. **Error handling** - Always log errors and provide user feedback
6. **Markdown escaping** - Use `ParseMode.MARKDOWN_V2` and escape special chars

## Project Structure

```
.
├── main.py              # Entry point - starts TelegramBot
├── bot.py               # TelegramBot class, handlers, RateLimiter
├── download_queue.py    # DownloadQueue, DownloadTask, workers
├── config.py            # Settings class with pydantic-settings
├── logger.py            # Logging setup (avoids circular imports)
├── pyproject.toml       # Project config, dependencies, tool settings
├── uv.lock              # Locked dependencies (committed to git)
├── .env                 # Environment variables (not in git)
├── Dockerfile           # Container config (uses uv, includes ffmpeg)
├── start.sh             # Shell script to run bot
├── youtube-bot.service  # Systemd service file
└── downloads/           # Temporary download directory (auto-created)
```

## Key Classes

### `TelegramBot` (bot.py)

Main bot class that handles:
- Command handlers: `/start`, `/help`, `/status`, `/cancel`
- URL message handler with YouTube regex validation
- Rate limiting via `RateLimiter` class
- Task monitoring with progress bar updates

### `DownloadQueue` (download_queue.py)

Async queue manager:
- Uses `asyncio.Queue` for task management
- `ThreadPoolExecutor` runs blocking yt-dlp in separate threads
- Configurable number of concurrent workers
- Progress tracking via yt-dlp hooks

### `DownloadTask` (download_queue.py)

Dataclass representing a download:
- `url`, `user_id`, `message_id` - Task identification
- `status` - Enum: PENDING, DOWNLOADING, COMPLETED, FAILED
- `progress` - Download percentage (0-100)
- `video_title`, `video_duration` - Metadata from yt-dlp
- `result_path` - Path to downloaded file

### `RateLimiter` (bot.py)

In-memory rate limiter:
- Tracks requests per user with sliding window
- Configurable max requests and window duration
- Methods: `is_allowed(user_id)`, `get_remaining(user_id)`

## Video Format Handling

**Critical:** Telegram requires H.264/MP4 for playable videos.

The download options in `download_queue.py` ensure compatibility:

```python
"format": (
    "bestvideo[vcodec^=avc1][ext=mp4]+bestaudio[ext=m4a]/"  # Best H.264
    "bestvideo[vcodec^=avc1]+bestaudio/"                    # H.264 any audio
    "bestvideo[ext=mp4]+bestaudio[ext=m4a]/"                # MP4 container
    "best[ext=mp4]/best"                                     # Fallback
),
"merge_output_format": "mp4",
"postprocessors": [{"key": "FFmpegVideoConvertor", "preferedformat": "mp4"}],
```

**Requirements:**
- `ffmpeg` must be installed (included in Dockerfile)
- Output is always MP4 with H.264 codec

## Message Formatting

All bot messages use `ParseMode.MARKDOWN_V2`. Special characters must be escaped:

```python
# Characters that need escaping: _ * [ ] ( ) ~ ` > # + - = | { } . !
text = text.replace("-", "\\-").replace(".", "\\.")

await message.reply_text(
    "Hello\\! This is *bold* text\\.",
    parse_mode=ParseMode.MARKDOWN_V2
)
```

## URL Validation

YouTube URLs are validated with regex patterns:

```python
YOUTUBE_PATTERNS = [
    r"(?:https?://)?(?:www\.)?youtube\.com/(?:watch\?v=|shorts/)[\w-]+",
    r"(?:https?://)?(?:m\.)?youtube\.com/(?:watch\?v=|shorts/)[\w-]+",
    r"(?:https?://)?youtu\.be/[\w-]+",
]
```

Supported formats:
- `youtube.com/shorts/VIDEO_ID`
- `youtube.com/watch?v=VIDEO_ID`
- `youtu.be/VIDEO_ID`
- Mobile URLs (`m.youtube.com`)

## Before Making Changes

1. **Check dependencies**: Verify required packages exist in `pyproject.toml`
2. **Run linter**: `uv run ruff check .` - ensure no issues
3. **Run type check**: `uv run mypy .` - ensure no type errors
4. **Test locally**: Use `uv run python main.py` to verify changes
5. **Check imports**: Avoid naming conflicts with standard library modules

## Adding Dependencies

```bash
# Add a new package
uv add package-name

# Add dev dependency
uv add --dev package-name

# Add specific version
uv add package-name==1.2.3
```

## Common Issues and Solutions

### Import Errors
- If you see "cannot import name 'X' from 'queue'", check for module name conflicts
- The project uses `download_queue.py` instead of `queue.py` to avoid stdlib conflicts

### Circular Imports
- `logger.py` reads `LOG_LEVEL` directly from `os.getenv()` to avoid importing `config.py`
- Import order: `logger.py` → `config.py` → other modules

### Video Not Playable
- Ensure `ffmpeg` is installed
- Check that `merge_output_format: "mp4"` is set
- The FFmpegVideoConvertor postprocessor handles conversion

### Environment Variables
- Configuration uses `pydantic-settings` which auto-loads `.env`
- Validation happens at import time - invalid config will raise errors early
- Never commit `.env` to version control

### Telegram Bot
- Get token from [@BotFather](https://t.me/botfather)
- Test with Shorts first before larger videos
- Monitor logs for 403 errors (normal - yt-dlp retries automatically)
- Files over 50MB cannot be sent (Telegram API limit)

### YouTube Bot Detection ("Sign in to confirm you're not a bot")
- This error means YouTube is blocking requests
- The bot uses iOS client emulation to bypass this in most cases
- If it persists, try a different video or wait and retry later

### Rate Limiting
- Users are limited to `RATE_LIMIT_PER_USER` requests per minute
- Rate limit state is in-memory (resets on bot restart)
- Check `/status` command to see remaining quota

## Testing Changes

After making changes:

```bash
# 1. Check code quality
uv run ruff check .

# 2. Run type checking
uv run mypy .

# 3. Verify syntax
uv run python -m py_compile main.py bot.py download_queue.py config.py logger.py

# 4. Run the bot
uv run python main.py
```

## Debugging

Enable debug logging by setting `LOG_LEVEL=DEBUG` in `.env`:

```bash
LOG_LEVEL=DEBUG
```

Logs are written to stdout with format:
```
2024-01-15 10:30:45 | INFO     | Starting bot...
2024-01-15 10:30:46 | INFO     | Worker 0 processing: https://youtube.com/shorts/...
```

## Performance Considerations

- Default: 5 concurrent download workers (configurable via `MAX_CONCURRENT_DOWNLOADS`)
- Maximum file size: 50MB (Telegram API limit, configurable via `MAX_VIDEO_SIZE_MB`)
- Downloads run in `ThreadPoolExecutor` to avoid blocking the event loop
- Downloads are automatically cleaned up after sending to user
- Queue prevents overwhelming system resources
- Rate limiting prevents individual users from abusing the bot
- Optimized for YouTube Shorts (typically small files under 50MB)

## Deployment

### Docker

The Dockerfile uses `uv` for fast, reproducible builds:

```bash
docker build -t youtube-shorts-bot .
docker run -d --env-file .env youtube-shorts-bot
```

**Note:** The Docker image uses `uv sync --frozen` which requires `uv.lock` to be committed.

### Systemd

Use the provided `youtube-bot.service` file:

```bash
sudo cp youtube-bot.service /etc/systemd/system/
sudo systemctl enable youtube-bot
sudo systemctl start youtube-bot
```

## Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome message with features and usage |
| `/help` | Help with troubleshooting tips |
| `/status` | Queue status and user's rate limit |
| `/cancel` | Cancel user's active downloads |

## Error Handling Flow

1. **URL Validation** → Invalid URL message with supported formats
2. **Rate Limiting** → Rate limit exceeded message
3. **Download Failure** → Error message with reason from yt-dlp
4. **File Too Large** → Size limit exceeded message
5. **Send Failure** → Error message (file is cleaned up regardless)

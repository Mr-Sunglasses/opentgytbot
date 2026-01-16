# AI Agent Instructions

## Project Overview

This is a Python-based Telegram bot that downloads YouTube Shorts with a queue management system. The bot uses `uv` as the package manager.

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

## Code Conventions

1. **Use `uv run` for all Python commands** - This ensures the correct virtual environment is used
2. **Follow PEP 8** - Code should pass `ruff check` with no errors
3. **Type hints** - All functions should have proper type annotations
4. **Async/await** - The bot is fully asynchronous, use `async/await` patterns
5. **Error handling** - Always log errors and provide user feedback

## Project Structure

```
.
├── main.py              # Entry point
├── bot.py               # Telegram bot logic and handlers
├── download_queue.py   # Queue management and download workers
├── config.py            # Configuration with dotenv support
├── logger.py            # Logging setup
├── pyproject.toml       # Project config and dependencies
├── .env                 # Environment variables (not in git)
├── .env.example         # Example environment variables
├── Dockerfile           # Container configuration
├── requirements.txt     # Pip-compatible dependencies
└── downloads/           # Temporary download directory
```

## Before Making Changes

1. **Check dependencies**: Verify required packages exist in `pyproject.toml`
2. **Run linter**: `uv run ruff check .` - ensure no issues
3. **Test locally**: Use `uv run python main.py` to verify changes
4. **Check imports**: Avoid naming conflicts with standard library modules

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

### Environment Variables
- Always load from `.env` file using `python-dotenv` in `config.py`
- Never commit `.env` to version control
- Use `.env.example` as a template

### Telegram Bot
- Get token from [@BotFather](https://t.me/botfather)
- Test with Shorts first before larger videos
- Monitor logs for 403 errors (normal - yt-dlp retries automatically)

## Testing Changes

After making changes:

```bash
# 1. Check code quality
uv run ruff check .

# 2. Verify syntax
uv run python -m py_compile main.py bot.py download_queue.py config.py

# 3. Run the bot
uv run python main.py
```

## Debugging

Enable debug logging by setting `LOG_LEVEL=DEBUG` in `.env`:

```bash
LOG_LEVEL=DEBUG
```

Logs are written to stdout with timestamps and include worker IDs for tracking downloads.

## Performance Considerations

- Default: 5 concurrent download workers (configurable via `MAX_CONCURRENT_DOWNLOADS`)
- Maximum file size: 50MB (configurable via `MAX_VIDEO_SIZE_MB`)
- Downloads are automatically cleaned up after sending to user
- Queue prevents overwhelming system resources
- Optimized for YouTube Shorts (typically small files under 50MB)

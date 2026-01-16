import os
from typing import Final

from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN: Final = os.getenv("TELEGRAM_BOT_TOKEN", "")
DOWNLOAD_DIR: Final = os.getenv("DOWNLOAD_DIR", "downloads")
MAX_CONCURRENT_DOWNLOADS: Final = int(os.getenv("MAX_CONCURRENT_DOWNLOADS", "5"))
MAX_VIDEO_SIZE_MB: Final = int(os.getenv("MAX_VIDEO_SIZE_MB", "50"))
LOG_LEVEL: Final = os.getenv("LOG_LEVEL", "INFO")

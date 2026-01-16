import asyncio
import os
import re
from collections import defaultdict
from time import time

from telegram import Message, Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from config import (
    DOWNLOAD_DIR,
    MAX_CONCURRENT_DOWNLOADS,
    MAX_VIDEO_SIZE_MB,
    RATE_LIMIT_PER_USER,
    TELEGRAM_BOT_TOKEN,
)
from download_queue import DownloadQueue, DownloadStatus, DownloadTask
from logger import logger

os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# YouTube URL patterns
YOUTUBE_PATTERNS = [
    r"(?:https?://)?(?:www\.)?youtube\.com/(?:watch\?v=|shorts/)[\w-]+",
    r"(?:https?://)?(?:m\.)?youtube\.com/(?:watch\?v=|shorts/)[\w-]+",
    r"(?:https?://)?youtu\.be/[\w-]+",
]
YOUTUBE_REGEX = re.compile("|".join(YOUTUBE_PATTERNS), re.IGNORECASE)


class RateLimiter:
    """Simple in-memory rate limiter per user."""

    def __init__(self, max_requests: int, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: dict[int, list[float]] = defaultdict(list)

    def is_allowed(self, user_id: int) -> bool:
        """Check if user is within rate limit."""
        now = time()
        window_start = now - self.window_seconds

        # Clean old requests
        self.requests[user_id] = [t for t in self.requests[user_id] if t > window_start]

        if len(self.requests[user_id]) >= self.max_requests:
            return False

        self.requests[user_id].append(now)
        return True

    def get_remaining(self, user_id: int) -> int:
        """Get remaining requests for user."""
        now = time()
        window_start = now - self.window_seconds
        self.requests[user_id] = [t for t in self.requests[user_id] if t > window_start]
        return max(0, self.max_requests - len(self.requests[user_id]))


class TelegramBot:
    def __init__(self) -> None:
        self.queue = DownloadQueue(max_concurrent=MAX_CONCURRENT_DOWNLOADS)
        self.application: Application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        self.rate_limiter = RateLimiter(max_requests=RATE_LIMIT_PER_USER, window_seconds=60)

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message:
            await update.message.reply_text(
                "🎬 *YouTube Shorts Downloader Bot*\n\n"
                "Simply send me any YouTube Shorts URL and I'll download it for you\\!\n\n"
                "✨ *Features:*\n"
                "• 📥 Download YouTube Shorts\n"
                f"• 🚀 {MAX_CONCURRENT_DOWNLOADS} concurrent downloads \\(queue system\\)\n"
                "• 🎥 Automatic MP4 format conversion\n"
                "• 📊 Real\\-time progress updates\n"
                "• 🧹 Auto\\-cleanup after sending\n\n"
                "📋 *Commands:*\n"
                "/start \\- Show this welcome message\n"
                "/status \\- Check current queue status\n"
                "/cancel \\- Cancel your pending downloads\n"
                "/help \\- Get help and usage information\n\n"
                "💡 *Usage:*\n"
                "1\\. Copy a YouTube Shorts URL\n"
                "2\\. Paste and send it to me\n"
                "3\\. Wait for the download to complete\n"
                "4\\. Receive your Short\\!\n\n"
                f"⚠️ *Limits:*\n"
                f"• Maximum file size: {MAX_VIDEO_SIZE_MB}MB\n"
                f"• Rate limit: {RATE_LIMIT_PER_USER} requests/minute\n"
                "• Video format: MP4\n\n"
                "🔒 *Privacy:* Your downloads are processed automatically and deleted after sending\\.",
                parse_mode=ParseMode.MARKDOWN_V2,
            )

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message:
            await update.message.reply_text(
                "📖 *Help & Troubleshooting*\n\n"
                "*Supported URLs:*\n"
                "• `youtube.com/shorts/...`\n"
                "• `youtube.com/watch?v=...`\n"
                "• `youtu.be/...`\n\n"
                "*Common Issues:*\n"
                "• ❌ *File too large* \\- The video exceeds 50MB Telegram limit\n"
                "• ❌ *Download failed* \\- Video might be private or age\\-restricted\n"
                "• ⏳ *Slow download* \\- High queue, please wait\n\n"
                "*Tips:*\n"
                "• Shorts are usually small and download quickly\n"
                "• Use /status to check queue position\n"
                "• Use /cancel to stop pending downloads\n\n"
                "*Rate Limiting:*\n"
                f"You can make up to {RATE_LIMIT_PER_USER} requests per minute\\.",
                parse_mode=ParseMode.MARKDOWN_V2,
            )

    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return

        user_id = update.effective_user.id if update.effective_user else 0
        queue_size = self.queue.get_queue_size()
        active = self.queue.get_active_downloads_count()
        remaining = self.rate_limiter.get_remaining(user_id)

        # Check if user has active downloads
        user_downloads = [
            task
            for task in self.queue.active_downloads.values()
            if task.user_id == user_id
        ]

        status_text = (
            f"📊 *Queue Status*\n\n"
            f"• Pending downloads: {queue_size}\n"
            f"• Currently downloading: {active}\n"
            f"• Max concurrent: {MAX_CONCURRENT_DOWNLOADS}\n\n"
            f"👤 *Your Status*\n"
            f"• Rate limit remaining: {remaining}/{RATE_LIMIT_PER_USER}"
        )

        if user_downloads:
            status_text += f"\n• Your active downloads: {len(user_downloads)}"
            for task in user_downloads:
                progress = f"{task.progress:.0f}%" if task.progress > 0 else "starting..."
                status_text += f"\n  └ {progress}"

        await update.message.reply_text(
            status_text.replace("-", "\\-").replace(".", "\\."),
            parse_mode=ParseMode.MARKDOWN_V2,
        )

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return

        user_id = update.effective_user.id if update.effective_user else 0
        cancelled = 0

        for task_id, task in list(self.queue.active_downloads.items()):
            if task.user_id == user_id:
                task.status = DownloadStatus.FAILED
                task.error = "Cancelled by user"
                cancelled += 1

        if cancelled > 0:
            await update.message.reply_text(f"✅ Cancelled {cancelled} active download(s)")
        else:
            await update.message.reply_text("❌ No active downloads to cancel")

    async def handle_url(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not update.message.text:
            return

        url = update.message.text.strip()
        user_id = update.effective_user.id if update.effective_user else 0
        message_id = update.message.message_id

        # Validate URL
        if not self._is_youtube_url(url):
            await update.message.reply_text(
                "❌ Please send a valid YouTube URL\\.\n\n"
                "*Supported formats:*\n"
                "• `youtube.com/shorts/...`\n"
                "• `youtube.com/watch?v=...`\n"
                "• `youtu.be/...`",
                parse_mode=ParseMode.MARKDOWN_V2,
            )
            return

        # Check rate limit
        if not self.rate_limiter.is_allowed(user_id):
            await update.message.reply_text(
                f"⚠️ Rate limit exceeded\\! You can make {RATE_LIMIT_PER_USER} requests per minute\\.\n"
                f"Please wait before trying again\\.",
                parse_mode=ParseMode.MARKDOWN_V2,
            )
            return

        queue_pos = self.queue.get_queue_size() + 1
        status_msg = await update.message.reply_text(
            f"⏳ Added to queue \\(position: {queue_pos}\\)\\.\\.\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )

        task = DownloadTask(url=url, user_id=user_id, message_id=message_id)
        await self.queue.add(task)

        asyncio.create_task(self._monitor_task(task, status_msg))

    def _is_youtube_url(self, url: str) -> bool:
        """Validate YouTube URL using regex patterns."""
        return bool(YOUTUBE_REGEX.search(url))

    async def _monitor_task(self, task: DownloadTask, status_msg: Message) -> None:
        last_progress = -1

        while True:
            if task.status == DownloadStatus.DOWNLOADING:
                # Update progress bar every 10%
                current_progress = int(task.progress // 10) * 10
                if current_progress != last_progress and task.progress > 0:
                    last_progress = current_progress
                    filled = int(task.progress // 10)
                    bar = "".join(["🟦" if i < filled else "⬜" for i in range(10)])
                    try:
                        await status_msg.edit_text(
                            f"📥 Downloading\\.\\.\\.\n\n"
                            f"{bar} {task.progress:.0f}%",
                            parse_mode=ParseMode.MARKDOWN_V2,
                        )
                    except Exception:
                        pass  # Ignore rate limit errors on status updates

            elif task.status == DownloadStatus.COMPLETED and task.result_path:
                try:
                    await status_msg.edit_text("✅ Download complete\\! Sending file\\.\\.\\.",
                                               parse_mode=ParseMode.MARKDOWN_V2)
                    await self._send_video(status_msg, task)
                    await status_msg.edit_text("🎉 Video sent successfully\\!",
                                               parse_mode=ParseMode.MARKDOWN_V2)
                except Exception as e:
                    logger.error(f"Error sending video: {e}")
                    error_msg = str(e).replace("-", "\\-").replace(".", "\\.")
                    await status_msg.edit_text(f"❌ Error: {error_msg}",
                                               parse_mode=ParseMode.MARKDOWN_V2)
                finally:
                    self._cleanup_file(task.result_path)
                break

            elif task.status == DownloadStatus.FAILED:
                error_msg = (task.error or "Unknown error").replace("-", "\\-").replace(".", "\\.")
                await status_msg.edit_text(f"❌ Download failed: {error_msg}",
                                           parse_mode=ParseMode.MARKDOWN_V2)
                break

            await asyncio.sleep(1.5)

    async def _send_video(self, message: Message, task: DownloadTask) -> None:
        file_path = task.result_path
        if not file_path or not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        file_size = os.path.getsize(file_path)
        file_size_mb = file_size / (1024 * 1024)

        if file_size > MAX_VIDEO_SIZE_MB * 1024 * 1024:
            raise ValueError(
                f"File too large ({file_size_mb:.1f}MB > {MAX_VIDEO_SIZE_MB}MB limit)"
            )

        logger.info(f"Sending video: {file_path} ({file_size_mb:.2f}MB)")

        # Build caption with video info
        caption_parts = []
        if task.video_title:
            caption_parts.append(f"🎬 {task.video_title}")
        if task.video_duration:
            mins, secs = divmod(task.video_duration, 60)
            caption_parts.append(f"⏱ {mins}:{secs:02d}")
        caption_parts.append(f"📦 {file_size_mb:.1f}MB")

        caption = "\n".join(caption_parts) if caption_parts else "Here's your video!"

        with open(file_path, "rb") as video:
            await message.reply_video(
                video=video,
                caption=caption,
                read_timeout=300,
                write_timeout=300,
                connect_timeout=300,
            )

    def _cleanup_file(self, file_path: str | None) -> None:
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
                logger.info(f"Cleaned up file: {file_path}")
            except Exception as e:
                logger.error(f"Error cleaning up file: {e}")

    async def run(self) -> None:
        await self.queue.start()

        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("status", self.status))
        self.application.add_handler(CommandHandler("cancel", self.cancel))
        self.application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_url)
        )

        logger.info("Starting bot...")
        await self.application.initialize()
        await self.application.start()
        if self.application.updater:
            await self.application.updater.start_polling(drop_pending_updates=True)

        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            pass
        finally:
            if self.application.updater:
                await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()
            await self.queue.stop()

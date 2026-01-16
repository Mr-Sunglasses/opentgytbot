import asyncio
import os

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from config import TELEGRAM_BOT_TOKEN, DOWNLOAD_DIR, MAX_CONCURRENT_DOWNLOADS, MAX_VIDEO_SIZE_MB
from logger import logger
from download_queue import DownloadQueue, DownloadTask, DownloadStatus

os.makedirs(DOWNLOAD_DIR, exist_ok=True)


class TelegramBot:
    def __init__(self):
        self.queue = DownloadQueue(max_concurrent=MAX_CONCURRENT_DOWNLOADS)
        self.application: Application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message:
            await update.message.reply_text(
                "🎬 **YouTube Shorts Downloader Bot**\n\n"
                "Simply send me any YouTube Shorts URL and I'll download it for you!\n\n"
                "✨ **Features:**\n"
                "• 📥 Download YouTube Shorts\n"
                "• 🚀 5 concurrent downloads (queue system)\n"
                "• 🎥 Automatic MP4 format conversion\n"
                "• 📊 Real-time status updates\n"
                "• 🧹 Auto-cleanup after sending\n\n"
                "📋 **Commands:**\n"
                "/start - Show this welcome message\n"
                "/status - Check current queue status\n"
                "/cancel - Cancel your pending downloads\n"
                "/help - Get help and usage information\n\n"
                "💡 **Usage:**\n"
                "1. Copy a YouTube Shorts URL\n"
                "2. Paste and send it to me\n"
                "3. Wait for the download to complete\n"
                "4. Receive your Short!\n\n"
                "⚠️ **Limits:**\n"
                "• Maximum file size: 50MB\n"
                "• Video format: MP4\n\n"
                "📌 **Note:** Due to Telegram's restrictions, files over 50MB cannot be sent. Please ensure your Shorts are under 50MB.\n\n"
                "🔒 **Privacy:** Your downloads are processed automatically and deleted after sending."
            )

    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return

        queue_size = self.queue.get_queue_size()
        active = self.queue.get_active_downloads_count()
        await update.message.reply_text(
            f"📊 Queue Status:\n"
            f"• Pending downloads: {queue_size}\n"
            f"• Currently downloading: {active}\n"
            f"• Max concurrent: {MAX_CONCURRENT_DOWNLOADS}"
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
            await update.message.reply_text(f"✅ Cancelled {cancelled} active downloads")
        else:
            await update.message.reply_text("❌ No active downloads to cancel")

    async def handle_url(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not update.message.text:
            return

        url = update.message.text.strip()
        user_id = update.effective_user.id if update.effective_user else 0
        message_id = update.message.message_id

        if not self._is_youtube_url(url):
            await update.message.reply_text("❌ Please send a valid YouTube URL")
            return

        status_msg = await update.message.reply_text("⏳ Added to queue...")

        task = DownloadTask(url=url, user_id=user_id, message_id=message_id)
        await self.queue.add(task)

        asyncio.create_task(self._monitor_task(task, status_msg))

    def _is_youtube_url(self, url: str) -> bool:
        return any(domain in url.lower() for domain in ["youtube.com", "youtu.be", "m.youtube.com"])

    async def _monitor_task(self, task: DownloadTask, status_msg) -> None:
        while True:
            if task.status == DownloadStatus.COMPLETED and task.result_path:
                try:
                    await status_msg.edit_text("✅ Download complete! Sending file...")
                    await self._send_video(status_msg, task.result_path)
                    await status_msg.edit_text("🎉 Video sent successfully!")
                except Exception as e:
                    logger.error(f"Error sending video: {e}")
                    await status_msg.edit_text(f"❌ Error sending video: {e}")
                finally:
                    self._cleanup_file(task.result_path)
                break

            elif task.status == DownloadStatus.FAILED:
                await status_msg.edit_text(f"❌ Download failed: {task.error}")
                break

            await asyncio.sleep(2)

    async def _send_video(self, message, file_path: str) -> None:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        file_size = os.path.getsize(file_path)
        file_size_mb = file_size / (1024 * 1024)

        if file_size > MAX_VIDEO_SIZE_MB * 1024 * 1024:
            raise ValueError(
                f"File too large for download ({file_size_mb:.1f}MB > {MAX_VIDEO_SIZE_MB}MB limit). "
                f"Please choose a YouTube Short that's under 50MB."
            )

        logger.info(f"Sending video: {file_path} ({file_size_mb:.2f}MB)")

        with open(file_path, "rb") as video:
            await message.reply_video(
                video=video,
                caption="Here's your video!",
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
        self.application.add_handler(CommandHandler("help", self.start))
        self.application.add_handler(CommandHandler("status", self.status))
        self.application.add_handler(CommandHandler("cancel", self.cancel))
        self.application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_url)
        )

        logger.info("Starting bot...")
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling(drop_pending_updates=True)

        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            pass
        finally:
            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()
            await self.queue.stop()

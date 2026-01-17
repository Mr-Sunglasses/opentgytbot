import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

import yt_dlp  # type: ignore[import-untyped]

from config import DOWNLOAD_DIR
from logger import logger


class DownloadStatus(Enum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class DownloadTask:
    url: str
    user_id: int
    message_id: int
    status: DownloadStatus = DownloadStatus.PENDING
    result_path: Optional[str] = None
    error: Optional[str] = None
    progress: float = 0.0
    video_title: Optional[str] = None
    video_duration: Optional[int] = None
    estimated_size_mb: Optional[float] = None
    # Callback for progress updates
    progress_callback: Optional[Callable[[float, str], None]] = field(default=None, repr=False)


class DownloadQueue:
    def __init__(self, max_concurrent: int = 5):
        self.queue: asyncio.Queue[DownloadTask] = asyncio.Queue()
        self.max_concurrent = max_concurrent
        self.active_downloads: dict[str, DownloadTask] = {}
        self._workers: list[asyncio.Task] = []
        self._executor = ThreadPoolExecutor(max_workers=max_concurrent, thread_name_prefix="yt-dlp")

    async def add(self, task: DownloadTask) -> None:
        await self.queue.put(task)
        logger.info(f"Added task to queue: {task.url} for user {task.user_id}")

    async def start(self) -> None:
        self._workers = [asyncio.create_task(self._worker(i)) for i in range(self.max_concurrent)]
        logger.info(f"Started {self.max_concurrent} download workers")

    async def stop(self) -> None:
        for worker in self._workers:
            worker.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._executor.shutdown(wait=False)
        logger.info("Stopped all download workers")

    async def _worker(self, worker_id: int) -> None:
        while True:
            try:
                task = await self.queue.get()
                task_id = f"{task.user_id}_{task.message_id}"
                self.active_downloads[task_id] = task
                task.status = DownloadStatus.DOWNLOADING

                logger.info(f"Worker {worker_id} processing: {task.url}")

                try:
                    # Run blocking download in executor
                    loop = asyncio.get_event_loop()
                    result = await loop.run_in_executor(
                        self._executor, self._download_video_sync, task
                    )
                    task.result_path = result["path"]
                    task.video_title = result.get("title")
                    task.video_duration = result.get("duration")
                    task.status = DownloadStatus.COMPLETED
                    logger.info(f"Worker {worker_id} completed: {task.url}")
                except Exception as e:
                    task.error = str(e)
                    task.status = DownloadStatus.FAILED
                    logger.error(f"Worker {worker_id} failed: {task.url} - {e}")
                finally:
                    del self.active_downloads[task_id]
                    self.queue.task_done()

            except asyncio.CancelledError:
                logger.info(f"Worker {worker_id} cancelled")
                break

    def _download_video_sync(self, task: DownloadTask) -> dict[str, Any]:
        """Synchronous download function to run in executor."""
        os.makedirs(DOWNLOAD_DIR, exist_ok=True)

        def progress_hook(d: dict[str, Any]) -> None:
            if d["status"] == "downloading":
                downloaded = d.get("downloaded_bytes", 0)
                total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
                if total > 0:
                    task.progress = (downloaded / total) * 100
                    task.estimated_size_mb = total / (1024 * 1024)

        ydl_opts: dict[str, Any] = {
            # Download best quality with H.264 for Telegram compatibility
            "format": (
                "bestvideo[vcodec^=avc1][height<=1080]+bestaudio[ext=m4a]/"
                "bestvideo[vcodec^=avc1]+bestaudio[ext=m4a]/"
                "bestvideo[vcodec^=avc1]+bestaudio/"
                "bestvideo[ext=mp4]+bestaudio[ext=m4a]/"
                "best[ext=mp4]/best"
            ),
            "outtmpl": f"{DOWNLOAD_DIR}/%(title).100s.%(ext)s",
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "progress_hooks": [progress_hook],
            # Ensure output is always MP4
            "merge_output_format": "mp4",
            # Post-process to ensure compatibility
            "postprocessors": [
                {
                    "key": "FFmpegVideoConvertor",
                    "preferedformat": "mp4",
                },
            ],
            "writethumbnail": False,
            # Use multiple client fallbacks to bypass bot detection
            # iOS and Android clients work best for Shorts
            "extractor_args": {
                "youtube": {
                    "player_client": ["ios", "android", "web_creator", "mweb", "tv_embedded"],
                    "player_skip": ["webpage", "configs"],
                },
            },
            "http_headers": {
                "User-Agent": (
                    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) "
                    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Referer": "https://www.youtube.com/",
            },
            "socket_timeout": 30,
            "retries": 10,
            "fragment_retries": 10,
            "file_access_retries": 5,
            "extractor_retries": 5,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:  # type: ignore[arg-type]
            logger.info(f"Starting download for: {task.url}")
            info = ydl.extract_info(task.url, download=True)
            filename = ydl.prepare_filename(info)

            # Handle postprocessor changing extension to mp4
            if not os.path.exists(filename):
                # Try with .mp4 extension
                base, _ = os.path.splitext(filename)
                mp4_filename = f"{base}.mp4"
                if os.path.exists(mp4_filename):
                    filename = mp4_filename
                else:
                    raise ValueError(f"Downloaded file not found: {filename}")

            if os.path.getsize(filename) == 0:
                raise ValueError("Downloaded file is empty")

            file_size_mb = os.path.getsize(filename) / (1024 * 1024)
            logger.info(f"Download complete: {filename} ({file_size_mb:.2f}MB)")

            return {
                "path": filename,
                "title": info.get("title", "Unknown"),
                "duration": info.get("duration"),
                "uploader": info.get("uploader"),
            }

    def get_queue_size(self) -> int:
        return self.queue.qsize()

    def get_active_downloads_count(self) -> int:
        return len(self.active_downloads)

import asyncio
import os
from dataclasses import dataclass
from typing import Optional
from enum import Enum

import yt_dlp
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


class DownloadQueue:
    def __init__(self, max_concurrent: int = 5):
        self.queue: asyncio.Queue[DownloadTask] = asyncio.Queue()
        self.max_concurrent = max_concurrent
        self.active_downloads: dict[str, DownloadTask] = {}
        self._workers: list[asyncio.Task] = []

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
                    result_path = await self._download_video(task.url)
                    task.result_path = result_path
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

    async def _download_video(self, url: str) -> str:
        download_dir = "downloads"
        os.makedirs(download_dir, exist_ok=True)

        ydl_opts = {
            "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "outtmpl": f"{download_dir}/%(title)s.%(ext)s",
            "quiet": False,
            "no_warnings": False,
            "noplaylist": True,
            "http_headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
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

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            logger.info(f"Starting download for: {url}")
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)

            if not os.path.exists(filename) or os.path.getsize(filename) == 0:
                raise ValueError("Downloaded file is empty or does not exist")

            logger.info(
                f"Download complete: {filename} ({os.path.getsize(filename) / (1024 * 1024):.2f}MB)"
            )
            return filename

    def get_queue_size(self) -> int:
        return self.queue.qsize()

    def get_active_downloads_count(self) -> int:
        return len(self.active_downloads)

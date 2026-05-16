import asyncio
import json
import os
import subprocess
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
    video_width: Optional[int] = None
    video_height: Optional[int] = None
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
                    task.video_width = result.get("width")
                    task.video_height = result.get("height")
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
            # Download best quality video regardless of codec, then re-encode to H.264.
            # Two separate dimension caps handle both orientations at 1080p quality:
            #   height<=1080 → landscape videos  (e.g. 1920×1080)
            #   width<=1080  → portrait Shorts   (e.g. 1080×1920)
            # Using height<=1920 caused format_sort:res to pick 1440p (2560×1440)
            # because 1440 < 1920, blowing out the expected 1080p output dimensions.
            "format": (
                "bestvideo[height<=1080]+bestaudio[ext=m4a]/"  # Landscape 1080p + M4A
                "bestvideo[width<=1080]+bestaudio[ext=m4a]/"  # Portrait 1080p + M4A
                "bestvideo[height<=1080]+bestaudio/"  # Landscape 1080p + any audio
                "bestvideo[width<=1080]+bestaudio/"  # Portrait 1080p + any audio
                "bestvideo+bestaudio/"  # Best any orientation (fallback)
                "best[ext=mp4]/best"  # Absolute fallback
            ),
            # Rank candidates by quality before the format selector picks one:
            # resolution → fps → video bitrate → audio bitrate (all descending).
            "format_sort": ["res", "fps", "vbr", "abr"],
            "outtmpl": f"{DOWNLOAD_DIR}/%(title).100s.%(ext)s",
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "progress_hooks": [progress_hook],
            # Ensure output is always MP4
            "merge_output_format": "mp4",
            # Post-process to ensure MP4 container
            "postprocessors": [
                {
                    "key": "FFmpegVideoConvertor",
                    "preferedformat": "mp4",
                },
            ],
            # Force H.264/AAC encoding on every ffmpeg invocation (merger + convertor).
            # This transcodes VP9/AV1 sources to H.264 so Telegram plays videos inline.
            # Preserve the source display aspect ratio exactly while normalizing to
            # square pixels. This keeps Shorts portrait and landscape videos in the
            # same shape YouTube provides instead of fitting them into a fixed box.
            # CRF 23 + fast preset keeps quality high while keeping encoding time short
            # (Shorts are ≤60 s, so the extra ~5-15 s is acceptable).
            "postprocessor_args": {
                "ffmpeg": [
                    "-vf",
                    "scale=trunc((iw*sar)/2)*2:trunc(ih/2)*2,setsar=1",
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    "-crf",
                    "23",
                    "-preset",
                    "fast",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "128k",
                    "-movflags",
                    "+faststart",
                ],
            },
            "writethumbnail": False,
            # Clients that work without GVS PO Tokens (as of yt-dlp 2026.x):
            #   web_creator / tv_embedded  – DASH streams, reliable, no token needed
            #   web_safari / android_vr    – full range 144p→2160p, no token needed
            # Removed: ios, android, mweb — YouTube now requires GVS PO Tokens for
            # these clients; without them every stream is silently skipped, leaving
            # only a single 360p fallback and causing the "low quality" symptom.
            # Removed: player_skip=["webpage","configs"] — it prevented yt-dlp from
            # discovering the full adaptive format list, compounding the quality issue.
            "extractor_args": {
                "youtube": {
                    "player_client": ["web_creator", "tv_embedded", "web_safari", "android_vr"],
                },
            },
            "http_headers": {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
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
            width, height = self._probe_video_dimensions(filename)
            logger.info(f"Download complete: {filename} ({file_size_mb:.2f}MB)")

            return {
                "path": filename,
                "title": info.get("title", "Unknown"),
                "duration": info.get("duration"),
                "uploader": info.get("uploader"),
                "width": width,
                "height": height,
            }

    def _probe_video_dimensions(self, file_path: str) -> tuple[Optional[int], Optional[int]]:
        """Read final encoded dimensions for Telegram video metadata."""
        try:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-select_streams",
                    "v:0",
                    "-show_entries",
                    "stream=width,height",
                    "-of",
                    "json",
                    file_path,
                ],
                capture_output=True,
                check=True,
                text=True,
                timeout=15,
            )
            streams = json.loads(result.stdout).get("streams", [])
            if not streams:
                return None, None

            width = streams[0].get("width")
            height = streams[0].get("height")
            if isinstance(width, int) and isinstance(height, int):
                return width, height
        except Exception as e:
            logger.warning(f"Could not probe video dimensions for {file_path}: {e}")

        return None, None

    def get_queue_size(self) -> int:
        return self.queue.qsize()

    def get_active_downloads_count(self) -> int:
        return len(self.active_downloads)

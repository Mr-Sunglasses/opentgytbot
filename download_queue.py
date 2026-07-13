import asyncio
import json
import os
import shutil
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

import yt_dlp  # type: ignore[import-untyped]

from config import COOKIES_FILE, DOWNLOAD_DIR
from logger import logger

STALE_DOWNLOAD_AGE_SECONDS = 24 * 60 * 60
TASK_DIR_PREFIX = "task-"


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
    work_dir: Optional[str] = None
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
        self._cleanup_stale_downloads()
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
                    self.cleanup_task_files(task)
                finally:
                    del self.active_downloads[task_id]
                    self.queue.task_done()

            except asyncio.CancelledError:
                logger.info(f"Worker {worker_id} cancelled")
                break

    def _download_video_sync(self, task: DownloadTask) -> dict[str, Any]:
        """Synchronous download function to run in executor."""
        os.makedirs(DOWNLOAD_DIR, exist_ok=True)
        task.work_dir = tempfile.mkdtemp(
            prefix=f"{TASK_DIR_PREFIX}{task.user_id}-{task.message_id}-",
            dir=DOWNLOAD_DIR,
        )

        def progress_hook(d: dict[str, Any]) -> None:
            if d["status"] == "downloading":
                downloaded = d.get("downloaded_bytes", 0)
                total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
                if total > 0:
                    task.progress = (downloaded / total) * 100
                    task.estimated_size_mb = total / (1024 * 1024)

        ydl_opts: dict[str, Any] = {
            # Download best quality video regardless of codec; re-encoded to H.264
            # afterwards only if the source isn't already Telegram-compatible.
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
            "outtmpl": os.path.join(task.work_dir, "%(title).100s [%(id)s].%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "progress_hooks": [progress_hook],
            # Merge into MP4 with a plain stream copy (no forced re-encode here).
            # We only transcode afterwards if the merged file actually needs it
            # (see _transcode_to_h264) — most web_creator/web_safari formats are
            # already H.264/AAC, so this skips a multi-minute encode in that case.
            "merge_output_format": "mp4",
            "writethumbnail": False,
            # Clients that work without GVS PO Tokens (as of yt-dlp 2026.x):
            #   web_creator – DASH streams, reliable, no token needed
            #   web_safari  – full range 144p→2160p, no token needed
            # Removed: ios, android, mweb — YouTube now requires GVS PO Tokens for
            # these clients; without them every stream is silently skipped, leaving
            # only a single 360p fallback and causing the "low quality" symptom.
            # Removed: tv_embedded (no longer supported by yt-dlp) and android_vr
            # (skipped whenever cookies are set, which we always do now).
            # Removed: player_skip=["webpage","configs"] — it prevented yt-dlp from
            # discovering the full adaptive format list, compounding the quality issue.
            # remote_components lets yt-dlp fetch its JS challenge-solver script
            # (used together with the deno runtime baked into the image) to solve
            # YouTube's nsig challenge; without it only image-only formats resolve.
            "remote_components": ["ejs:github"],
            "extractor_args": {
                "youtube": {
                    "player_client": ["web_creator", "web_safari"],
                },
            },
            "http_headers": {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
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

        if os.path.exists(COOKIES_FILE):
            ydl_opts["cookiefile"] = COOKIES_FILE
            logger.info(f"Using cookies from: {COOKIES_FILE}")

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:  # type: ignore[arg-type]
            logger.info(f"Starting download for: {task.url}")
            info = ydl.extract_info(task.url, download=True)
            filename = self._resolve_downloaded_file(ydl.prepare_filename(info), task.work_dir)

            if os.path.getsize(filename) == 0:
                raise ValueError("Downloaded file is empty")

            if self._is_telegram_compatible(self._probe_streams(filename)):
                logger.info(f"Source already H.264/AAC, skipping re-encode: {filename}")
            else:
                logger.info(f"Re-encoding to H.264/AAC: {filename}")
                filename = self._transcode_to_h264(filename)

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

    def _resolve_downloaded_file(self, prepared_filename: str, work_dir: str) -> str:
        """Find the final media file after yt-dlp post-processing."""
        candidates = [prepared_filename]
        base, _ = os.path.splitext(prepared_filename)
        candidates.extend([f"{base}.mp4", f"{base}.mkv", f"{base}.webm"])

        for filename in candidates:
            if os.path.isfile(filename):
                return filename

        video_suffixes = {".mp4", ".mkv", ".mov", ".webm"}
        media_files = [
            path
            for path in Path(work_dir).iterdir()
            if path.is_file()
            and not path.name.endswith(".part")
            and path.suffix.lower() in video_suffixes
            and path.stat().st_size > 0
        ]
        if media_files:
            return str(max(media_files, key=lambda path: path.stat().st_mtime))

        raise ValueError(f"Downloaded file not found in task directory: {work_dir}")

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

    def _probe_streams(self, file_path: str) -> list[dict[str, Any]]:
        """Read codec/SAR info for every stream, used to decide if a re-encode is needed."""
        try:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "stream=codec_type,codec_name,sample_aspect_ratio",
                    "-of",
                    "json",
                    file_path,
                ],
                capture_output=True,
                check=True,
                text=True,
                timeout=15,
            )
            return json.loads(result.stdout).get("streams", [])
        except Exception as e:
            logger.warning(f"Could not probe streams for {file_path}: {e}")
            return []

    def _is_telegram_compatible(self, streams: list[dict[str, Any]]) -> bool:
        """True if the file is already H.264/AAC with square pixels, so re-encoding
        would be a no-op for compatibility and just burns CPU."""
        vcodec = next((s.get("codec_name") for s in streams if s.get("codec_type") == "video"), None)
        acodec = next((s.get("codec_name") for s in streams if s.get("codec_type") == "audio"), None)
        sar = next((s.get("sample_aspect_ratio") for s in streams if s.get("codec_type") == "video"), None)
        return vcodec == "h264" and acodec == "aac" and sar in (None, "1:1", "0:1")

    def _transcode_to_h264(self, src_path: str) -> str:
        """Re-encode to H.264/AAC for Telegram compatibility. Only called when the
        source codec isn't already compatible (e.g. VP9/AV1 video or non-square SAR).
        Uses 'veryfast' since this is the slow path and correctness, not max
        compression, is the goal here.
        """
        base, _ = os.path.splitext(src_path)
        out_path = f"{base}.h264.mp4"
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                src_path,
                "-vf",
                "scale=trunc((iw*sar)/2)*2:trunc(ih/2)*2,setsar=1",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-crf",
                "23",
                "-preset",
                "veryfast",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-movflags",
                "+faststart",
                out_path,
            ],
            check=True,
            capture_output=True,
            timeout=600,
        )
        os.remove(src_path)
        return out_path

    def cleanup_task_files(self, task: DownloadTask) -> None:
        """Remove a task's temporary directory or final file."""
        if task.work_dir:
            self._remove_task_dir(task.work_dir)
            return

        if task.result_path and os.path.exists(task.result_path):
            try:
                os.remove(task.result_path)
                logger.info(f"Cleaned up file: {task.result_path}")
            except Exception as e:
                logger.error(f"Error cleaning up file {task.result_path}: {e}")

    def _cleanup_stale_downloads(self) -> None:
        """Remove old task directories left behind by previous process exits."""
        download_root = Path(DOWNLOAD_DIR)
        if not download_root.exists():
            return

        cutoff = time.time() - STALE_DOWNLOAD_AGE_SECONDS
        for path in download_root.iterdir():
            if not path.is_dir() or not path.name.startswith(TASK_DIR_PREFIX):
                continue

            try:
                if path.stat().st_mtime < cutoff:
                    self._remove_task_dir(str(path))
            except Exception as e:
                logger.warning(f"Could not inspect stale download directory {path}: {e}")

    def _remove_task_dir(self, directory: str) -> None:
        path = Path(directory)
        download_root = Path(DOWNLOAD_DIR).resolve()

        try:
            resolved_path = path.resolve()
            if (
                resolved_path == download_root
                or download_root not in resolved_path.parents
                or not path.name.startswith(TASK_DIR_PREFIX)
            ):
                logger.warning(f"Refusing to clean unexpected download path: {directory}")
                return

            if path.exists():
                shutil.rmtree(path)
                logger.info(f"Cleaned up task directory: {directory}")
        except Exception as e:
            logger.error(f"Error cleaning up task directory {directory}: {e}")

    def get_queue_size(self) -> int:
        return self.queue.qsize()

    def get_active_downloads_count(self) -> int:
        return len(self.active_downloads)

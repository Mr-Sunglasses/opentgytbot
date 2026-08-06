#!/usr/bin/env python3
"""Automatically refresh cookies.txt on a remote server.

Run on YOUR PC where the YouTube browser session lives. Every time this runs it:

 1. Exports fresh, non-expired cookies from your logged-in browser via yt-dlp.
 2. Uploads them over SFTP to the server path configured for the bot.
 3. Optionally restarts the bot service if you don't want to rely on the
    bot reading cookies.txt fresh per download.

Requires:
    pip install yt-dlp paramiko

Usage:
    python sync_cookies.py --browser chrome \\
        --host you.example.com --user ubuntu --key ~/.ssh/id_ed25519 \\
        --remote-path /app/cookies.txt [--restart-service botctl]
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile

import paramiko  # type: ignore


def export_cookies(browser: str, out_path: str, video_url: str) -> None:
    """Export fresh cookies from the browser into a Netscape cookies file."""
    cmd = [
        "yt-dlp",
        f"--cookies-from-browser", browser,
        "--cookies", out_path,
        "--skip-download",
        video_url,
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)

    with open(out_path, encoding="utf-8") as f:
        content = f.read()
    if "youtube.com" not in content or "HTTP" not in content:
        raise SystemExit("Exported cookie file doesn't look like a valid cookies file.")


def upload_sftp(host: str, user: str, key_path: str, local: str, remote: str,
                port: int) -> None:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, port=port, username=user, key_filename=os.path.expanduser(key_path))
    try:
        sftp = ssh.open_sftp()
        sftp.put(local, remote)
        sftp.close()
    finally:
        ssh.close()
    print(f"Uploaded fresh cookies to {remote}")


def restart_service(server: str, port: int, key_path: str, service: str) -> None:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(server, port=port, key_filename=os.path.expanduser(key_path))
    _, out, err = ssh.exec_command(f"sudo systemctl restart {service}")
    out.channel.recv_exit_status()
    err_text = err.read().decode()
    if err_text:
        print(f"restart stderr: {err_text}")
    else:
        print(f"Restarted service {service}")
    ssh.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync fresh browser cookies to your bot server.")
    parser.add_argument("--browser", default="chrome",
                        choices=["chrome", "chromium", "firefox", "edge", "brave", "opera", "vivaldi"],
                        help="Browser holding your logged-in YouTube session.")
    parser.add_argument("--video-url", default="https://www.youtube.com/",
                        help="Video to fetch cookies for (default: homepage).")
    parser.add_argument("--server", required=True, help="SSH host of the server.")
    parser.add_argument("--port", type=int, default=22)
    parser.add_argument("--user", required=True, help="SSH username.")
    parser.add_argument("--key", default="~/.ssh/id_ed25519", help="Path to SSH private key.")
    parser.add_argument("--remote", required=True, help="Remote path to cookies.txt (matches COOKIES_FILE).")
    parser.add_argument("--restart-service", default=None,
                        help="Optional systemd service name to restart after upload (e.g. 'botctl' or 'youtube-bot').")
    args = parser.parse_args()

    with tempfile.NamedTemporaryFile(prefix="cookies_", suffix=".txt", delete=False) as tmp:
        local = tmp.name

    try:
        export_cookies(args.browser, local, args.video_url)
        print(f"Exported fresh cookies to {local}")

        upload_sftp(args.server, args.port, args.key, local, args.remote)

        if args.restart_service:
            restart_service(args.server, args.port, args.key, args.restart_service)
    finally:
        try:
            os.remove(local)
        except OSError:
            pass


if __name__ == "__main__":
    main()
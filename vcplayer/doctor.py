"""Offline dependency checks; does not connect to Telegram or inspect secrets."""

import importlib.metadata
import platform
import shutil
import subprocess


def main():
    print(f"Python {platform.python_version()} | {platform.system()} {platform.machine()}")
    failed = False
    for binary in ("ffmpeg", "ffprobe", "node"):
        path = shutil.which(binary)
        if not path:
            print(f"MISSING: {binary}")
            failed = True
            continue
        flag = "--version" if binary == "node" else "-version"
        result = subprocess.run([path, flag], capture_output=True, text=True, timeout=10)
        print(result.stdout.splitlines()[0] if result.stdout else f"{binary}: failed")
        failed |= result.returncode != 0
        if binary == "node" and int(result.stdout.strip().lstrip("v").split(".")[0]) < 22:
            print("Node.js 22 or newer is required for YouTube JavaScript challenges.")
            failed = True
    try:
        import ntgcalls  # noqa: F401
        import pytgcalls  # noqa: F401

        for package in ("py-tgcalls", "ntgcalls", "telethon", "yt-dlp", "yt-dlp-ejs"):
            print(f"{package} {importlib.metadata.version(package)}")
    except (ImportError, OSError, importlib.metadata.PackageNotFoundError) as exc:
        print(f"Dependency check failed ({type(exc).__name__}). Reinstall requirements.")
        failed = True
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()

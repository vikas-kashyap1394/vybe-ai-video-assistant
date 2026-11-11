
from pathlib import Path
import subprocess
import yt_dlp

PROJECT_ROOT = Path(__file__).resolve().parent.parent
AUDIO_DIR = PROJECT_ROOT / "data" / "audio"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

SUPPORTED_FILES = {".mp3", ".wav", ".m4a", ".mp4", ".mov", ".mkv", ".webm", ".aac", ".flac", ".ogg"}


def process_media(source):
    source = str(source).strip()

    if source.startswith(("https://www.youtube.com/", "https://youtube.com/",
                          "https://youtu.be/")):
        return download_youtube_audio(source)

    path = Path(source).expanduser()

    if not path.is_file():
        raise FileNotFoundError(f"Media file not found: {path}")

    if path.suffix.lower() not in SUPPORTED_FILES:
        raise ValueError(f"Unsupported media format: {path.suffix}")

    if path.suffix.lower() in {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}:
        return str(path.resolve())

    return extract_audio(path)


def download_youtube_audio(url):
    options = {
        "format": "bestaudio/best",
        "outtmpl": str(AUDIO_DIR / "%(id)s.%(ext)s"),
        "noplaylist": True,
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "128",
        }],
    }

    with yt_dlp.YoutubeDL(options) as downloader:
        info = downloader.extract_info(url, download=True)
        audio_path = AUDIO_DIR / f"{info['id']}.mp3"

    if not audio_path.exists():
        raise FileNotFoundError("YouTube audio download did not produce an MP3 file.")

    return str(audio_path.resolve())


def extract_audio(video_path):
    output_path = AUDIO_DIR / f"{video_path.stem}.mp3"

    command = [
        "ffmpeg", "-y", "-i", str(video_path),
        "-vn", "-ac", "1", "-ar", "16000",
        "-b:a", "128k", str(output_path),
    ]

    subprocess.run(command, check=True, capture_output=True, text=True)
    return str(output_path.resolve())

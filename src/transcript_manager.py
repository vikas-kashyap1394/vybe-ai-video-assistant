
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TRANSCRIPT_DIR = PROJECT_ROOT / "data" / "transcripts"
TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)


def save_transcript(transcript, filename="transcript.txt"):
    path = TRANSCRIPT_DIR / Path(filename).name
    path = path.with_suffix(".txt")

    path.write_text(transcript.strip() + "\n", encoding="utf-8")
    return str(path.resolve())


def load_transcript(filename):
    path = TRANSCRIPT_DIR / Path(filename).name

    if not path.exists():
        raise FileNotFoundError(f"Transcript not found: {path}")

    return path.read_text(encoding="utf-8").strip()


def create_transcript_filename():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"transcript_{timestamp}.txt"




import whisper
import torch
from pathlib import Path

_model = None


def get_model():
    global _model

    if _model is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"

        print(f"Loading Whisper Small model on {device}...")

        _model = whisper.load_model("small", device=device)

    return _model


def transcribe_audio(audio_path):
    audio_path = Path(audio_path)

    if not audio_path.exists():
        raise FileNotFoundError(
            f"Audio file not found: {audio_path}"
        )

    model = get_model()

    result = model.transcribe(
        str(audio_path),
        task="transcribe",
        fp16=torch.cuda.is_available(),
        verbose=False,
    )

    segments = []

    for segment in result["segments"]:
        segments.append({
            "start": round(segment["start"], 2),
            "end": round(segment["end"], 2),
            "text": segment["text"].strip(),
        })

    return {
        "text": result["text"].strip(),
        "language": result["language"],
        "segments": segments,
    }

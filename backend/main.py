
import json
import mimetypes
import shutil
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from urllib.parse import urlparse

from src.transcriber import transcribe_audio
from src.summarizer import summarize_transcript
from src.transcript_manager import (
    save_transcript,
    create_transcript_filename,
)
from src.media_handler import process_media
from src.qa_engine import answer_question
from src.langchain_rag import index_transcript
from src.rag_pipeline import answer_from_video


PROJECT_ROOT = Path(__file__).resolve().parent.parent
VIDEO_DIR = PROJECT_ROOT / "data" / "audio"
MAPPING_FILE = PROJECT_ROOT / "data" / "video_mappings.json"

VIDEO_DIR.mkdir(parents=True, exist_ok=True)

SUPPORTED_VIDEO_FORMATS = {
    ".mp4", ".mov", ".mkv", ".webm"
}


def gemini_http_exception(error):
    """Convert Gemini quota/service failures into safe, useful API responses."""
    message = str(error)
    lowered = message.lower()

    if any(marker in lowered for marker in (
        "resource_exhausted",
        "quota exceeded",
        "quota_exceeded",
        "rate limit",
        "429",
    )):
        return HTTPException(
            status_code=429,
            detail=(
                "Gemini daily free-tier quota has been exhausted. "
                "Please try again after the quota resets."
            ),
        )

    print(f"Gemini/API error: {message}")
    return HTTPException(
        status_code=503,
        detail=(
            "The AI service is temporarily unavailable. "
            "Please try again later."
        ),
    )


def load_video_mappings():
    if not MAPPING_FILE.exists():
        return {}

    try:
        with open(MAPPING_FILE, "r", encoding="utf-8") as file:
            return json.load(file)
    except (json.JSONDecodeError, OSError):
        return {}


def save_video_mapping(source_id, video_filename):
    mappings = load_video_mappings()

    mappings[source_id] = video_filename

    with open(MAPPING_FILE, "w", encoding="utf-8") as file:
        json.dump(mappings, file, indent=4)


def prepare_video_file(source):
    source_path = Path(source).expanduser()

    if not source_path.is_file():
        return None

    if source_path.suffix.lower() not in SUPPORTED_VIDEO_FORMATS:
        return None

    destination = (VIDEO_DIR / source_path.name).resolve()

    if destination.parent != VIDEO_DIR.resolve():
        raise ValueError("Invalid video filename.")

    if source_path.resolve() != destination:
        shutil.copy2(source_path, destination)

    return destination.name


app = FastAPI(
    title="AI Video & Meeting Assistant API",
    description="Transcription, summaries, action items and Gemini-powered RAG Q&A",
    version="2.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class MediaRequest(BaseModel):
    source: str = Field(..., min_length=1)


class TranscriptRequest(BaseModel):
    transcript: str = Field(..., min_length=1)


class QuestionRequest(BaseModel):
    transcript: str = Field(..., min_length=1)
    question: str = Field(..., min_length=1)


class VideoQuestionRequest(BaseModel):
    source_id: str = Field(..., min_length=1)
    question: str = Field(..., min_length=1)


class YouTubeRequest(BaseModel):
    url: str = Field(..., min_length=8)


@app.get("/")
def home():
    return {
        "message": "AI Video & Meeting Assistant API is running",
        "docs": "/docs",
    }


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.get("/video/{filename}")
def serve_video(filename: str):

    video_directory = VIDEO_DIR.resolve()
    video_path = (video_directory / filename).resolve()

    if video_path.parent != video_directory:
        raise HTTPException(
            status_code=400,
            detail="Invalid video filename.",
        )

    if video_path.suffix.lower() not in SUPPORTED_VIDEO_FORMATS:
        raise HTTPException(
            status_code=400,
            detail="Unsupported video format.",
        )

    if not video_path.is_file():
        raise HTTPException(
            status_code=404,
            detail="Video file not found.",
        )

    media_type = mimetypes.guess_type(str(video_path))[0]
    media_type = media_type or "application/octet-stream"

    return FileResponse(
        path=str(video_path),
        media_type=media_type,
        headers={
            "Content-Disposition": "inline"
        },
    )


@app.post("/process")
def process_media_endpoint(request: MediaRequest):
    try:
        # Step 1: Preserve the original video for playback
        video_filename = prepare_video_file(request.source)

        # Step 2: Extract or prepare audio
        audio_path = process_media(request.source)

        if not Path(audio_path).is_file():
            raise HTTPException(
                status_code=422,
                detail="Audio file could not be created or found.",
            )

        # Step 3: Transcribe audio using Whisper
        transcription = transcribe_audio(audio_path)

        transcript = transcription["text"]
        segments = transcription["segments"]
        detected_language = transcription["language"]

        if not transcript.strip():
            raise HTTPException(
                status_code=422,
                detail="No speech detected in the media.",
            )

        # Step 4: Save transcript
        filename = create_transcript_filename()
        save_transcript(transcript, filename)

        # Step 5: Index transcript
        indexed_chunks = index_transcript(
            segments,
            source_id=filename,
        )

        # Step 6: Save transcript-to-video mapping
        if video_filename:
            save_video_mapping(filename, video_filename)

        video_url = (
            f"/video/{video_filename}"
            if video_filename
            else None
        )

        return {
            "message": "Media processed successfully.",
            "transcript": transcript,
            "language": detected_language,
            "segments": segments,
            "transcript_file": filename,
            "indexed_chunks": indexed_chunks,
            "video_file": video_filename,
            "video_url": video_url,
        }

    except HTTPException:
        raise

    except FileNotFoundError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        )

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        )

    except Exception as error:
        print(f"Media processing error: {error}")
        raise HTTPException(
            status_code=500,
            detail="Media processing failed. Check the server logs.",
        )


@app.post("/upload")
def upload_media_endpoint(file: UploadFile = File(...)):
    try:
        if not file.filename:
            raise HTTPException(
                status_code=400,
                detail="No file selected.",
            )

        filename = Path(file.filename).name
        extension = Path(filename).suffix.lower()

        allowed_formats = {
            ".mp4", ".mov", ".mkv", ".webm",
            ".mp3", ".wav", ".m4a", ".aac",
            ".flac", ".ogg",
        }

        if extension not in allowed_formats:
            raise HTTPException(
                status_code=400,
                detail="Unsupported media format.",
            )

        destination = (VIDEO_DIR / filename).resolve()

        if destination.parent != VIDEO_DIR.resolve():
            raise HTTPException(
                status_code=400,
                detail="Invalid filename.",
            )

        with destination.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        return process_media_endpoint(
            MediaRequest(source=str(destination))
        )

    except HTTPException:
        raise

    except Exception as error:
        print(f"Upload error: {error}")
        raise HTTPException(
            status_code=500,
            detail="File upload failed. Check server logs.",
        )

    finally:
        file.file.close()


@app.get("/videos")
def list_videos():
    """Return the persistent library from saved transcript files."""
    from src.transcript_manager import TRANSCRIPT_DIR

    mappings = load_video_mappings()
    items = []
    for transcript_path in sorted(
        TRANSCRIPT_DIR.glob("*.txt"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    ):
        source_id = transcript_path.name
        mapped = mappings.get(source_id)
        video_filename = mapped.get("video_filename") if isinstance(mapped, dict) else mapped
        video_path = VIDEO_DIR / video_filename if video_filename else None
        items.append({
            "source_id": source_id,
            "title": (
                mapped.get("title") if isinstance(mapped, dict) else None
            ) or (Path(video_filename).name if video_filename else transcript_path.stem),
            "transcript_file": source_id,
            "video_file": video_filename,
            "video_url": f"/video/{video_filename}" if video_path and video_path.is_file() else None,
            "has_video": bool(video_path and video_path.is_file()),
            "transcript_size": transcript_path.stat().st_size,
            "created_at": transcript_path.stat().st_mtime,
        })
    return {"videos": items, "total": len(items)}


@app.get("/videos/{source_id}")
def get_video_analysis(source_id: str):
    """Load a saved transcript and its linked video for an earlier analysis."""
    from src.transcript_manager import load_transcript

    safe_source_id = Path(source_id).name
    if safe_source_id != source_id or not safe_source_id.endswith(".txt"):
        raise HTTPException(status_code=400, detail="Invalid transcript ID.")
    try:
        transcript = load_transcript(safe_source_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Saved transcript not found.")

    mappings = load_video_mappings()
    mapped = mappings.get(safe_source_id)
    video_filename = mapped.get("video_filename") if isinstance(mapped, dict) else mapped
    video_path = VIDEO_DIR / video_filename if video_filename else None
    video_url = f"/video/{video_filename}" if video_path and video_path.is_file() else None
    title = (mapped.get("title") if isinstance(mapped, dict) else None) or (
        Path(video_filename).name if video_filename else Path(safe_source_id).stem
    )
    return {
        "source_id": safe_source_id,
        "transcript_file": safe_source_id,
        "title": title,
        "transcript": transcript,
        "video_file": video_filename,
        "video_url": video_url,
    }


@app.post("/youtube")
def import_youtube_video(request: YouTubeRequest):
    """Download a publicly accessible YouTube video, then run the normal pipeline."""
    parsed = urlparse(request.url.strip())
    host = (parsed.hostname or "").lower()
    allowed_hosts = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "www.youtube-nocookie.com"}
    if host not in allowed_hosts:
        raise HTTPException(status_code=400, detail="Please provide a valid YouTube URL.")

    try:
        import yt_dlp
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="YouTube import dependency is missing. Install it with: pip install yt-dlp",
        )

    try:
        options = {
            "format": "bestvideo*+bestaudio/best",
            "outtmpl": str(VIDEO_DIR / "%(title).120B_%(id)s.%(ext)s"),
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "restrictfilenames": True,
            "merge_output_format": "mp4",
        }
        with yt_dlp.YoutubeDL(options) as downloader:  # type: ignore[arg-type]
            info = downloader.extract_info(request.url.strip(), download=True)
            downloaded = Path(downloader.prepare_filename(info))
            if not downloaded.exists():
                mp4_candidate = downloaded.with_suffix(".mp4")
                if mp4_candidate.exists():
                    downloaded = mp4_candidate
            if not downloaded.is_file():
                raise FileNotFoundError("Downloaded video file was not found.")

        result = process_media_endpoint(MediaRequest(source=str(downloaded)))
        # Store a friendly title while remaining compatible with old string mappings.
        mappings = load_video_mappings()
        source_id = result["transcript_file"]
        mappings[source_id] = {
            "video_filename": downloaded.name,
            "title": info.get("title") or downloaded.stem,
        }
        with open(MAPPING_FILE, "w", encoding="utf-8") as file:
            json.dump(mappings, file, indent=4)
        result["title"] = info.get("title") or downloaded.stem
        return result

    except HTTPException:
        raise
    except Exception as error:
        print(f"YouTube import error: {error}")
        raise HTTPException(
            status_code=422,
            detail=f"YouTube import failed: {error}",
        )

@app.post("/summary")
def summary_endpoint(request: TranscriptRequest):
    try:
        # Run the full analysis once. The old wrappers each called Gemini
        # independently and could consume three requests for one summary.
        analysis = summarize_transcript(request.transcript)

        return {
            "summary": analysis.get("summary", ""),
            "key_points": analysis.get("key_points", []),
            "action_items": analysis.get("action_items", []),
            "decisions": analysis.get("decisions", []),
            "completed_actions": analysis.get("completed_actions", []),
            "important_numbers": analysis.get("important_numbers", []),
            "provider": analysis.get("provider", "Gemini"),
        }

    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))

    except Exception as error:
        raise gemini_http_exception(error)


@app.post("/ask")
def ask_endpoint(request: QuestionRequest):
    try:
        answer = answer_question(
            request.transcript,
            request.question,
        )

        return {"answer": answer}

    except Exception as error:
        print(f"Question answering error: {error}")
        raise HTTPException(
            status_code=500,
            detail="Question answering failed. Check the server logs.",
        )



@app.post("/ask-video")
def ask_video_endpoint(request: VideoQuestionRequest):
    try:
        result = answer_from_video(
            question=request.question,
            source_id=request.source_id,
        )

        mappings = load_video_mappings()
        mapped = mappings.get(request.source_id)
        video_filename = (
            mapped.get("video_filename")
            if isinstance(mapped, dict)
            else mapped
        )

        video_url = (
            f"/video/{video_filename}"
            if video_filename
            else None
        )

        result["video_url"] = video_url

        for source in result.get("sources", []):
            source["video_url"] = video_url

        return result

    except HTTPException:
        raise

    except Exception as error:
        raise gemini_http_exception(error)

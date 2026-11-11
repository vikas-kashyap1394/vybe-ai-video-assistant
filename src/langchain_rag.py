from pathlib import Path

from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma


PROJECT_ROOT = Path(__file__).resolve().parent.parent
VECTOR_DIR = PROJECT_ROOT / "data" / "langchain_vectorstore"

_embedding_model = None
_vector_store = None

CHUNK_SIZE_WORDS = 180
CHUNK_OVERLAP_WORDS = 40


def get_embeddings():
    global _embedding_model

    if _embedding_model is None:
        _embedding_model = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2",
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )

    return _embedding_model


def get_vector_store():
    global _vector_store

    if _vector_store is None:
        VECTOR_DIR.mkdir(parents=True, exist_ok=True)
        _vector_store = Chroma(
            collection_name="video_transcripts_langchain",
            embedding_function=get_embeddings(),
            persist_directory=str(VECTOR_DIR),
        )

    return _vector_store


def create_documents(
    segments,
    source_id="current_video",
    chunk_size=CHUNK_SIZE_WORDS,
    overlap=CHUNK_OVERLAP_WORDS,
):
    """Combine Whisper segments into overlapping chunks with timestamps."""
    if chunk_size <= 0 or overlap < 0 or overlap >= chunk_size:
        raise ValueError(
            "chunk_size must be positive and overlap must be smaller than chunk_size"
        )

    if not segments:
        return []

    valid_segments = []
    for segment in segments:
        text = str(segment.get("text", "")).strip()
        if not text:
            continue

        start = float(segment.get("start", 0.0))
        valid_segments.append({
            "text": text,
            "start": start,
            "end": float(segment.get("end", start)),
            "word_count": len(text.split()),
        })

    documents = []
    start_index = 0

    while start_index < len(valid_segments):
        end_index = start_index
        word_count = 0

        while end_index < len(valid_segments) and word_count < chunk_size:
            word_count += valid_segments[end_index]["word_count"]
            end_index += 1

        chunk_segments = valid_segments[start_index:end_index]
        if not chunk_segments:
            break

        chunk_text = " ".join(item["text"] for item in chunk_segments).strip()

        documents.append(
            Document(
                page_content=chunk_text,
                metadata={
                    "source": source_id,
                    "start": chunk_segments[0]["start"],
                    "end": chunk_segments[-1]["end"],
                    "matched_text": chunk_text,
                },
            )
        )

        if end_index >= len(valid_segments):
            break

        # Retain approximately 40 words of context in the next chunk.
        next_start = end_index
        overlap_words = 0

        while next_start > start_index and overlap_words < overlap:
            next_start -= 1
            overlap_words += valid_segments[next_start]["word_count"]

        # Guarantee forward progress.
        start_index = max(start_index + 1, next_start)

    return documents


def index_transcript(segments, source_id="current_video"):
    documents = create_documents(segments, source_id)

    if not documents:
        return 0

    vector_store = get_vector_store()

    # Replace old chunks for this video; do not retain stale embeddings.
    vector_store.delete(where={"source": source_id})
    vector_store.add_documents(documents)

    return len(documents)


def search_transcript(question, source_id=None, k=10):
    if not question or not question.strip():
        return []

    vector_store = get_vector_store()
    search_filter = {"source": source_id} if source_id else None

    results = vector_store.similarity_search(
        question,
        k=k,
        filter=search_filter,
    )

    return [
        {
            "text": doc.page_content,
            "matched_text": doc.metadata.get("matched_text"),
            "source": doc.metadata.get("source"),
            "start": doc.metadata.get("start"),
            "end": doc.metadata.get("end"),
        }
        for doc in results
    ]

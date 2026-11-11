
from pathlib import Path
import chromadb
from sentence_transformers import SentenceTransformer

PROJECT_ROOT = Path(__file__).resolve().parent.parent
VECTOR_DIR = PROJECT_ROOT / "data" / "vectorstore"

_client = None
_collection = None
_embedding_model = None


def get_collection():
    global _client, _collection

    if _collection is None:
        VECTOR_DIR.mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(path=str(VECTOR_DIR))
        _collection = _client.get_or_create_collection(
            name="video_transcripts"
        )

    return _collection


def get_embedding_model():
    global _embedding_model

    if _embedding_model is None:
        _embedding_model = SentenceTransformer(
            "sentence-transformers/all-MiniLM-L6-v2",
            device="cpu",
        )

    return _embedding_model


def chunk_text(text, chunk_size=120, overlap=30):
    words = text.split()
    chunks = []
    step = chunk_size - overlap

    if step <= 0:
        raise ValueError("chunk_size must be greater than overlap")

    for start in range(0, len(words), step):
        chunk = " ".join(words[start:start + chunk_size])
        if chunk:
            chunks.append(chunk)

    return chunks


def index_transcript(transcript, source_id):
    chunks = chunk_text(transcript)

    if not chunks:
        return 0

    collection = get_collection()
    model = get_embedding_model()

    embeddings = model.encode(
        chunks,
        normalize_embeddings=True,
    ).tolist()

    ids = [f"{source_id}_{i}" for i in range(len(chunks))]

    collection.upsert(
        ids=ids,
        documents=chunks,
        embeddings=embeddings,
        metadatas=[{"source": source_id, "chunk": i} for i in range(len(chunks))],
    )

    return len(chunks)


def search_transcript(question, source_id=None, n_results=3):
    collection = get_collection()

    if collection.count() == 0:
        return []

    model = get_embedding_model()
    query_embedding = model.encode(
        [question],
        normalize_embeddings=True,
    ).tolist()

    count = min(n_results, collection.count())
    where = {"source": source_id} if source_id else None

    results = collection.query(
        query_embeddings=query_embedding,
        n_results=count,
        where=where,
        include=["documents", "metadatas", "distances"],
    )

    return [
        {
            "text": doc,
            "source": meta["source"],
            "distance": distance,
        }
        for doc, meta, distance in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        )
    ]

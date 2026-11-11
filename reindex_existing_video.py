from src.langchain_rag import get_vector_store, index_transcript

SOURCE_ID = "transcript_20261111_051444.txt"

# Read the old Whisper segments BEFORE index_transcript deletes the old entries.
store = get_vector_store()
data = store.get(
    where={"source": SOURCE_ID},
    include=["documents", "metadatas"],
)

documents = data.get("documents") or []
metadatas = data.get("metadatas") or []

segments = []
for document, metadata in zip(documents, metadatas):
    metadata = metadata or {}
    text = (metadata.get("matched_text") or document or "").strip()

    if not text:
        continue

    start = float(metadata.get("start", 0.0))
    end = float(metadata.get("end", start))

    segments.append({
        "text": text,
        "start": start,
        "end": end,
    })

segments.sort(key=lambda item: item["start"])

if not segments:
    raise RuntimeError(
        f"No old indexed segments found for {SOURCE_ID}. "
        "Nothing was deleted. Check the source ID before trying again."
    )

print(f"Recovered {len(segments)} old Whisper segments.")
print("Rebuilding the index with larger, overlapping chunks...")

chunk_count = index_transcript(segments, source_id=SOURCE_ID)

print(f"Done. Created {chunk_count} improved chunks for {SOURCE_ID}.")
print("You can now test the same question in VYBE AI.")

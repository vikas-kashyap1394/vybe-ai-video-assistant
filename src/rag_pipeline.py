import re

from src.langchain_rag import search_transcript
from src.llm import generate_answer


STOP_WORDS = {
    "the", "is", "are", "was", "were", "what", "when",
    "where", "who", "why", "how", "did", "does", "do",
    "a", "an", "and", "or", "to", "of", "in", "on",
    "for", "with", "he", "she", "they", "it", "his",
    "her", "their", "this", "that", "be", "been",
    "can", "could", "would", "should", "me", "we",
    "you", "i", "based", "video", "context", "during",
    "meeting", "discussed", "discuss", "related", "points",
    "key", "about", "being", "have", "has", "had",
}


def format_timestamp(seconds):
    if seconds is None:
        return "Unknown"

    seconds = int(seconds)
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def extract_keywords(text):
    words = re.findall(r"[a-zA-Z0-9]+", str(text).lower())
    return {
        word for word in words
        if len(word) > 2 and word not in STOP_WORDS
    }


def extract_relevant_excerpt(text, reference_keywords):
    """
    Return only sentences that match the question/answer keywords.
    The displayed timestamp remains the containing chunk's time range,
    not an exact sentence-level timestamp.
    """
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    scored = []

    for index, sentence in enumerate(sentences):
        keywords = extract_keywords(sentence)
        overlap = keywords & reference_keywords

        if len(overlap) >= 1:
            scored.append((index, len(overlap), sentence.strip()))

    if not scored:
        return ""

    # Include directly adjacent sentences when they provide context.
    selected_indices = set()
    for index, _, _ in scored:
        selected_indices.add(index)
        if index > 0:
            selected_indices.add(index - 1)
        if index + 1 < len(sentences):
            selected_indices.add(index + 1)

    return " ".join(
        sentences[index].strip()
        for index in sorted(selected_indices)
        if sentences[index].strip()
    )


def filter_relevant_sources(results, question, answer, max_sources=5):
    question_keywords = extract_keywords(question)
    answer_keywords = extract_keywords(answer)
    reference_keywords = question_keywords | answer_keywords

    if not reference_keywords:
        return []

    scored_results = []

    for result in results:
        full_text = result.get("matched_text") or result.get("text") or ""
        if not full_text.strip():
            continue

        segment_keywords = extract_keywords(full_text)
        question_overlap = question_keywords & segment_keywords
        answer_overlap = answer_keywords & segment_keywords

        score = (2 * len(question_overlap)) + len(answer_overlap)

        if not question_overlap and len(answer_overlap) < 2:
            continue

        start = result.get("start")
        end = result.get("end")
        if start is None or end is None:
            continue

        excerpt = extract_relevant_excerpt(full_text, reference_keywords)
        if not excerpt:
            # Keep the original passage if sentence extraction cannot
            # confidently isolate a useful excerpt.
            excerpt = full_text.strip()

        scored_results.append({
            "score": score,
            "text": excerpt,
            "source": result.get("source"),
            "start": float(start),
            "end": float(end),
        })

    scored_results.sort(key=lambda item: item["score"], reverse=True)

    selected = []
    for item in scored_results:
        duplicate = False

        for chosen in selected:
            overlap_start = max(item["start"], chosen["start"])
            overlap_end = min(item["end"], chosen["end"])
            overlap_duration = max(0, overlap_end - overlap_start)
            shorter_duration = min(
                item["end"] - item["start"],
                chosen["end"] - chosen["start"],
            )

            if (
                item["source"] == chosen["source"]
                and shorter_duration > 0
                and overlap_duration / shorter_duration >= 0.70
            ):
                duplicate = True
                break

        if not duplicate:
            selected.append(item)

        if len(selected) >= max_sources:
            break

    selected.sort(key=lambda item: item["start"])

    return [
        {
            "text": item["text"],
            "source": item["source"],
            "start": item["start"],
            "end": item["end"],
            "start_timestamp": format_timestamp(item["start"]),
            "end_timestamp": format_timestamp(item["end"]),
        }
        for item in selected
    ]


def answer_from_video(question, source_id="current_video"):
    results = search_transcript(
        question=question,
        source_id=source_id,
        k=20,
    )

    print("\n========== RAG DEBUG ==========")
    print("Source ID:", source_id)
    print("Question:", question)
    print("Retrieved chunks:", len(results))

    for i, result in enumerate(results):
        print(f"\nChunk {i + 1}:")
        print("Source:", result.get("source"))
        print("Start:", result.get("start"))
        print("Text:", result.get("text", "")[:500])

    print("================================\n")

    if not results:
        return {
            "answer": "I could not find this information in the video.",
            "sources": [],
        }

    context = "\n".join(
        result.get("text", "")
        for result in results
        if result.get("text")
    )

    prompt = f"""
You are an AI video assistant.

Answer the user's question using ONLY the context provided below.

Rules:
1. Do not use outside knowledge.
2. If the answer is unavailable, say:
   "I could not find this information in the video."
3. Keep the answer clear and concise.
4. Do not generate or mention timestamps.
5. For questions involving multiple people or actions,
   explain each person's action separately.
6. Do not infer decisions or details from incomplete sentences.

Context:
{context}

Question:
{question}

Answer:
"""

    try:
        answer = generate_answer(prompt)

    except Exception as error:
        error_message = str(error)

        if "429" in error_message or "RESOURCE_EXHAUSTED" in error_message:
            raise RuntimeError(
                "Gemini API daily free-tier quota exceeded. "
                "Please try again after the quota resets."
            ) from error

        raise RuntimeError(
            "Gemini API is temporarily unavailable. Please try again later."
        ) from error

    timestamp_sources = filter_relevant_sources(
        results=results,
        question=question,
        answer=answer,
    )

    return {
        "answer": answer,
        "sources": timestamp_sources,
    }

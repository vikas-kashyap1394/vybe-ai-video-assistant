
from src.vector_store import index_transcript, search_transcript
from transformers import pipeline

_qa_model = None


def get_qa_model():
    global _qa_model

    if _qa_model is None:
        _qa_model = pipeline(
            "question-answering",
            model="distilbert/distilbert-base-cased-distilled-squad",
            device=-1,
        )

    return _qa_model


def answer_question(transcript, question, source_id="current_video"):
    if not transcript.strip():
        return "No transcript available. Please process a video first."

    if not question.strip():
        return "Please enter a question."

    index_transcript(transcript, source_id)

    results = search_transcript(
        question,
        source_id=source_id,
        n_results=3,
    )

    if not results:
        return "I couldn't find relevant information in the transcript."

    context = "\n".join(item["text"] for item in results)

    try:
        model = get_qa_model()
        result = model(
            question=question,
            context=context,
        )

        if result["score"] < 0.10:
            return "I couldn't find a reliable answer in the transcript."

        return result["answer"].strip()

    except Exception:
        return (
            "Could not generate an answer. Relevant transcript context:\n"
            + context
        )

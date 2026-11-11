import json
import re

from src.llm import generate_answer


def _clean_transcript(transcript):
    if not transcript:
        return ""
    return re.sub(r"\s+", " ", str(transcript)).strip()


def _extract_json(text):
    """Parse JSON returned by Gemini, including optional Markdown fences."""
    if isinstance(text, dict):
        return text

    cleaned = str(text).strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            return json.loads(cleaned[start:end + 1])
        raise ValueError("Gemini did not return valid JSON for the summary.")


def _normalize_list(value, limit=10):
    if not isinstance(value, list):
        return []
    result = []
    seen = set()
    for item in value:
        if isinstance(item, str):
            text = item.strip()
        elif isinstance(item, dict):
            text = item.get("text") or item.get("task") or item.get("description") or ""
            text = str(text).strip()
        else:
            continue
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            result.append(text)
        if len(result) >= limit:
            break
    return result


def _analyze_with_gemini(transcript):
    prompt = f"""
You are VYBE AI, an accurate meeting and video analyst.
Analyze the transcript below. Treat it as the ONLY source of truth.

Return ONLY valid JSON with exactly these keys:
{{
  "summary": "A detailed but concise executive summary in 1-2 paragraphs.",
  "key_points": ["5-8 important factual insights, decisions, progress updates or outcomes"],
  "decisions": ["Explicit decisions or approvals only"],
  "completed_actions": ["Actions explicitly stated as already completed"],
  "action_items": ["Pending tasks or explicit commitments/instructions only"],
  "important_numbers": ["Important metrics, percentages, dates, quantities or deadlines with context"]
}}

STRICT RULES:
- Do not invent names, owners, deadlines, metrics, decisions or tasks.
- Key points must be meaningful facts, not greetings, filler, questions or generic statements.
- Do not put a question or conversational sentence in key_points.
- Do not repeat the same fact across every section unless necessary for clarity.
- action_items must be future/pending work or an explicit instruction/commitment.
- Do not classify a completed action as a pending action item.
- Do not turn an approval such as "you can proceed" into a task.
- Assign an owner only if the transcript clearly identifies one.
- If a task is inferred from unfinished work but not explicitly assigned, label it "Suggested follow-up" and make that clear.
- decisions must be explicit, not assumptions.
- Preserve exact figures and their meaning.
- If a section has no supported information, return an empty array.
- Use clear, professional English. Avoid unnecessary verbosity.

TRANSCRIPT:
{transcript}
"""
    response = generate_answer(prompt)
    data = _extract_json(response)

    return {
        "summary": str(data.get("summary", "")).strip(),
        "key_points": _normalize_list(data.get("key_points"), 8),
        "decisions": _normalize_list(data.get("decisions"), 8),
        "completed_actions": _normalize_list(data.get("completed_actions"), 8),
        "action_items": _normalize_list(data.get("action_items"), 10),
        "important_numbers": _normalize_list(data.get("important_numbers"), 10),
        "provider": "Gemini",
    }


def summarize_transcript(transcript):
    """
    Gemini-only meeting analysis.
    Deliberately does not silently fall back to DistilBART when quota is exhausted.
    """
    text = _clean_transcript(transcript)
    if not text:
        raise ValueError("No transcript available.")

    # A single request is preferred to conserve free-tier quota.
    # For unusually long transcripts, split into overlapping sections and ask
    # Gemini to synthesize their content in one final request.
    max_chars = 26000
    if len(text) <= max_chars:
        return _analyze_with_gemini(text)

    chunk_size = 22000
    overlap = 1200
    partials = []
    start = 0

    while start < len(text):
        chunk = text[start:start + chunk_size]
        partials.append(_analyze_with_gemini(chunk))
        if start + chunk_size >= len(text):
            break
        start += chunk_size - overlap

    combined = json.dumps(partials, ensure_ascii=False)
    final_prompt = f"""
You are VYBE AI. Consolidate these Gemini analyses of consecutive sections
of the SAME transcript into one accurate meeting report.
Return ONLY valid JSON with keys:
summary, key_points, decisions, completed_actions, action_items, important_numbers.
Do not invent facts, owners or deadlines. Remove duplicates. Preserve figures.
Only include pending tasks in action_items; keep completed work separate.
If a task is inferred rather than explicitly assigned, label it Suggested follow-up.
ANALYSES:
{combined}
"""
    data = _extract_json(generate_answer(final_prompt))
    return {
        "summary": str(data.get("summary", "")).strip(),
        "key_points": _normalize_list(data.get("key_points"), 8),
        "decisions": _normalize_list(data.get("decisions"), 8),
        "completed_actions": _normalize_list(data.get("completed_actions"), 8),
        "action_items": _normalize_list(data.get("action_items"), 10),
        "important_numbers": _normalize_list(data.get("important_numbers"), 10),
        "provider": "Gemini",
    }


# Backward-compatible wrappers for any existing imports elsewhere.
def generate_summary(transcript, max_sentences=5):
    return summarize_transcript(transcript)["summary"]


def extract_key_points(transcript, max_points=7):
    return summarize_transcript(transcript)["key_points"][:max_points]


def extract_action_items(transcript):
    return summarize_transcript(transcript)["action_items"]

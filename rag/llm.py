from app_config import GEMINI_MODEL, USE_MOCK_AI
from rag.gemini_client import get_client, with_retries
from rag.mock_ai import mock_answer, mock_summary
from rag.prompt import SUMMARY_SYSTEM_PROMPT, SYSTEM_PROMPT, build_prompt, build_summary_prompt


def generate_answer(question: str, excerpts: list[dict]) -> str:
    if USE_MOCK_AI:
        return mock_answer(question, [e["text"] for e in excerpts])
    return _generate(build_prompt(question, excerpts), SYSTEM_PROMPT)


def generate_summary(documents: list[dict], language: str) -> str:
    """documents: [{'title': ..., 'text': ...}] -> plain-text summary in 'lt' or 'en'."""
    if USE_MOCK_AI:
        return mock_summary(documents, language)
    return _generate(build_summary_prompt(documents, language), SUMMARY_SYSTEM_PROMPT)


def _generate(contents: str, system_instruction: str) -> str:
    from google.genai import types
    response = with_retries(lambda: get_client().models.generate_content(
        model=GEMINI_MODEL,
        contents=contents,
        config=types.GenerateContentConfig(system_instruction=system_instruction, temperature=0.2),
    ))
    if not response.text:                 # e.g. blocked by a safety filter: .text is empty or None
        raise RuntimeError("Gemini returned no text")
    return response.text.strip()

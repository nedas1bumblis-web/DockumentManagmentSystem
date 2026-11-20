"""Offline stand-in for Gemini: deterministic, free, instant. Switch on with USE_MOCK_AI=1."""
import hashlib
import math
import re

_WORD = re.compile(r"\w+", re.UNICODE)


def normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec))
    return vec if norm == 0 else [x / norm for x in vec]


def mock_embed(text: str, dim: int) -> list[float]:
    """Bag-of-words hashing: texts that share words get similar vectors, so retrieval tests are meaningful."""
    vec = [0.0] * dim
    for word in _WORD.findall(text.lower()):
        bucket = int.from_bytes(hashlib.blake2b(word.encode("utf-8"), digest_size=4).digest(), "big") % dim
        vec[bucket] += 1.0
    return normalize(vec)


def mock_answer(question: str, excerpts: list[str]) -> str:
    """Pretends to be the LLM: quotes the best excerpt and cites it as [1]."""
    if not excerpts:
        return "Pasirinktuose dokumentuose tokios informacijos nėra."
    return f"{excerpts[0][:300]} [1]"


_SENTENCE = re.compile(r"(?<=[.!?])\s+")


def mock_summary(documents: list[dict], language: str) -> str:
    """Pretends to summarise: every title followed by its first two sentences."""
    lines = []
    for d in documents:
        lines.append(d["title"])
        lines += [f"- {s.strip()}" for s in _SENTENCE.split(d["text"].strip())[:2] if s.strip()]
    if len(documents) > 1:
        lines += ["Bendra santrauka" if language == "lt" else "Overall summary",
                  f"{len(documents)} documents."]
    return "\n".join(lines)

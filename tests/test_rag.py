import math
import sys
import types
from pathlib import Path

import pytest

import rag.embedder as embedder
from processing.chunker import chunk_pages
from processing.pdf_reader import read_pdf
from processing.text_cleaner import clean_text, strip_repeated_lines
from rag.gemini_client import with_retries
from rag.mock_ai import mock_answer, mock_embed
from rag.prompt import build_prompt, detect_language, parse_citations

SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "metodiniai.pdf"


# ---------- a fake google-genai, so the Gemini plumbing can be tested without a key or a network ----------
class ApiError(Exception):
    def __init__(self, code):
        super().__init__(f"HTTP {code}")
        self.code = code


class FakeModels:
    def __init__(self, errors=(), merge=False):
        self.errors, self.merge, self.batch_sizes = list(errors), merge, []

    def embed_content(self, model, contents, config):
        if self.errors:
            raise ApiError(self.errors.pop(0))
        self.batch_sizes.append(len(contents))
        make = lambda values: types.SimpleNamespace(values=values)
        if self.merge:                                           # one aggregated embedding for the whole list
            return types.SimpleNamespace(embeddings=[make([1.0, 2.0])])
        return types.SimpleNamespace(embeddings=[make([float(len(t)), 1.0, 0.0]) for t in contents])


@pytest.fixture
def fake_genai(monkeypatch):
    config_module = types.ModuleType("google.genai.types")
    config_module.EmbedContentConfig = lambda **kw: types.SimpleNamespace(**kw)
    genai_module = types.ModuleType("google.genai")
    genai_module.types = config_module
    google = sys.modules.get("google") or types.ModuleType("google")
    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setitem(sys.modules, "google.genai", genai_module)
    monkeypatch.setitem(sys.modules, "google.genai.types", config_module)
    monkeypatch.setattr(google, "genai", genai_module, raising=False)
    monkeypatch.setattr(embedder, "USE_MOCK_AI", False)


def fake_client(**kw):
    return types.SimpleNamespace(models=FakeModels(**kw))


def test_embeddings_are_batched_ordered_and_normalised(fake_genai):
    texts = ["x" * n for n in range(1, 121)]
    client = fake_client()
    vectors = embedder.embed_texts(texts, "RETRIEVAL_DOCUMENT", client=client)
    assert client.models.batch_sizes == [50, 50, 20]
    assert len(vectors) == 120
    assert all(math.isclose(math.sqrt(sum(x * x for x in v)), 1.0) for v in vectors)
    assert all(round(v[0] / v[1]) == len(t) for v, t in zip(vectors, texts))     # order preserved


def test_429_is_retried_with_growing_delay_then_succeeds(fake_genai):
    delays, client = [], fake_client(errors=[429, 503])
    vectors = embedder.embed_texts(["abc"], "RETRIEVAL_QUERY", client=client, sleep=delays.append)
    assert len(vectors) == 1 and len(delays) == 2 and 1 <= delays[0] < 2 and 2 <= delays[1] < 3


def test_client_errors_are_not_retried(fake_genai):
    delays = []
    with pytest.raises(ApiError):
        embedder.embed_texts(["abc"], "RETRIEVAL_QUERY", client=fake_client(errors=[400]), sleep=delays.append)
    assert delays == []


def test_gives_up_after_five_attempts():
    delays = []
    with pytest.raises(ApiError):
        with_retries(lambda: (_ for _ in ()).throw(ApiError(429)), sleep=delays.append)
    assert len(delays) == 4


def test_merged_single_embedding_is_detected(fake_genai):
    with pytest.raises(RuntimeError, match="got 1"):
        embedder.embed_texts(["a", "b", "c"], "RETRIEVAL_DOCUMENT", client=fake_client(merge=True))


def test_mock_mode_makes_no_client_calls(monkeypatch):
    monkeypatch.setattr(embedder, "USE_MOCK_AI", True)
    vectors = embedder.embed_texts(["labas rytas", "geras vakaras"], "RETRIEVAL_DOCUMENT")
    assert len(vectors) == 2 and len(vectors[0]) == embedder.EMBEDDING_DIM


# ---------- mock AI ----------
def test_mock_embedding_is_deterministic_and_similar_texts_are_closer():
    dot = lambda a, b: sum(x * y for x, y in zip(a, b))
    a, b, c = (mock_embed(t, 256) for t in ("kasmetinės atostogos trunka 20 dienų", "kiek trunka atostogos", "kelionės išlaidos 100 EUR"))
    assert a == mock_embed("kasmetinės atostogos trunka 20 dienų", 256)
    assert dot(a, b) > dot(a, c)


def test_mock_answer():
    assert mock_answer("?", []) .startswith("Pasirinktuose dokumentuose")
    assert mock_answer("?", ["Pirmas", "Antras"]).endswith("[1]")


# ---------- prompt and citations ----------
def test_prompt_numbers_excerpts_and_names_pages():
    prompt = build_prompt("Kiek dienų?  ", [{"document": "Atostogų tvarka", "page": 2, "text": "20 darbo dienų"},
                                            {"document": "Santrauka", "page": None, "text": "…"}])
    assert "[1] (Atostogų tvarka, p. 2)\n20 darbo dienų" in prompt and "[2] (Santrauka)\n…" in prompt
    assert "Question: Kiek dienų?\n\n" in prompt
    assert prompt.endswith("Write the whole answer in Lithuanian, even though the excerpts may be in another language.")


def test_question_language_is_detected_for_the_answer_language_rule():     # FR-03 / TS-03
    assert detect_language("Kiek dienų trunka atostogos?") == "lt"
    assert detect_language("Kokia referato apimtis?") == "lt"               # Lithuanian without special letters
    assert detect_language("What font size is recommended for slide titles?") == "en"
    assert detect_language("How many pages long should a referatas be?") == "en"
    assert detect_language("???") == "lt"                                   # default: the company language
    assert "in English" in build_prompt("What is the leave policy?", [])


def test_citations_are_parsed_deduplicated_and_validated():
    assert parse_citations("Taip [2]. Taip pat [1, 2] ir [3][1].", excerpt_count=3) == [2, 1, 3]
    assert parse_citations("Išgalvotas šaltinis [9], [0].", excerpt_count=3) == []
    assert parse_citations("Dokumente tokios informacijos nėra.", excerpt_count=3) == []


# ---------- the whole offline pipeline on the real sample file (wiring check, not a quality check) ----------
@pytest.mark.skipif(not SAMPLE.exists(), reason="samples/metodiniai.pdf missing")
def test_retrieval_finds_the_right_page_with_mock_embeddings():
    pages = [{**p, "text": clean_text(p["text"])} for p in strip_repeated_lines(read_pdf(str(SAMPLE)))]
    chunks = chunk_pages(pages)
    vectors = [mock_embed(c["text"], 1536) for c in chunks]
    question = mock_embed("Kokios paraštės paliekamos darbo lape?", 1536)
    ranked = sorted(range(len(chunks)), key=lambda i: -sum(x * y for x, y in zip(question, vectors[i])))
    top5 = [chunks[i] for i in ranked[:5]]            # the mock is a crude word counter, so only 'in the top 5'
    assert any("dešinioji – 1 cm" in c["text"] and c["page"] == 8 for c in top5)

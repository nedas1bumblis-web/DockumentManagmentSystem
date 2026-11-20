from pathlib import Path

import pytest
from docx import Document as new_docx
from pypdf import PdfWriter

from processing.chunker import chunk_pages
from processing.docx_reader import read_docx
from processing.pdf_reader import UnreadableDocument, read_pdf
from processing.text_cleaner import clean_text, strip_repeated_lines

SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "metodiniai.pdf"


# ---------- chunker ----------
def test_short_page_is_one_chunk():
    chunks = chunk_pages([{"text": "Sveiki pasauli", "page": 7}])
    assert chunks == [{"index": 0, "page": 7, "text": "Sveiki pasauli"}]


def test_empty_and_blank_pages_give_no_chunks():
    assert chunk_pages([]) == []
    assert chunk_pages([{"text": "  \n ", "page": 1}]) == []


def test_chunks_respect_size_keep_page_and_overlap():
    text = " ".join(f"zodis{i}" for i in range(1000))
    chunks = chunk_pages([{"text": text, "page": 4}], size=1000, overlap=150)
    assert len(chunks) > 5
    assert all(0 < len(c["text"]) <= 1000 for c in chunks)
    assert [c["index"] for c in chunks] == list(range(len(chunks)))
    assert {c["page"] for c in chunks} == {4}
    for a, b in zip(chunks, chunks[1:]):                      # overlap: next chunk starts inside the previous one
        first_word = b["text"].split()[0]
        assert first_word in a["text"].split()[-40:]


def test_no_word_is_lost_or_cut():
    words = [f"zodis{i}" for i in range(2000)]
    chunks = chunk_pages([{"text": " ".join(words), "page": 1}], size=500, overlap=80)
    seen = set(" ".join(c["text"] for c in chunks).split())
    assert seen == set(words)


@pytest.mark.parametrize("n", [999, 1000, 1001, 1149, 1150, 1151])
def test_boundary_lengths_terminate(n):
    chunks = chunk_pages([{"text": "a" * n, "page": 1}])
    assert chunks and all(len(c["text"]) <= 1000 for c in chunks)


def test_text_without_any_whitespace_terminates():
    chunks = chunk_pages([{"text": "x" * 5000, "page": 1}], size=1000, overlap=150)
    assert 5 <= len(chunks) <= 8
    assert all(len(c["text"]) <= 1000 for c in chunks)


def test_bad_parameters_rejected():
    for size, overlap in [(50, 0), (1000, 500), (1000, -1)]:
        with pytest.raises(ValueError):
            chunk_pages([{"text": "x", "page": 1}], size=size, overlap=overlap)


# ---------- cleaner ----------
def test_clean_text_rules():
    assert clean_text("a    b \n\n\n\nc ..... d") == "a b\n\nc d"


def test_running_header_is_removed_but_body_is_kept():
    names = ["alfa", "beta", "gama", "delta", "epsilon", "dzeta", "eta", "teta", "jota", "kapa"]
    pages = [{"text": f"Header A 2024   {n}\n" + "\n".join(f"{w} unikalus tekstas {w}{n}" for w in names), "page": n}
             for n in range(1, 9)]
    cleaned = strip_repeated_lines(pages)
    assert all("Header A" not in p["text"] for p in cleaned)
    assert all(f"alfa unikalus tekstas alfa{p['page']}" in p["text"] for p in cleaned)
    assert all(f"kapa unikalus tekstas kapa{p['page']}" in p["text"] for p in cleaned)


def test_few_pages_are_left_alone():
    pages = [{"text": "Header\nBody", "page": n} for n in range(1, 4)]
    assert strip_repeated_lines(pages) == pages


def test_short_pages_are_left_alone():                      # all lines of a short page would count as 'edge'
    pages = [{"text": f"Slide {n}\nBullet\nBullet two", "page": n} for n in range(1, 9)]
    assert strip_repeated_lines(pages) == pages


# ---------- readers ----------
def test_docx_reader_reads_paragraphs_and_tables(tmp_path):
    doc = new_docx()
    doc.add_paragraph("Kasmetinės atostogos trunka 20 darbo dienų.")
    table = doc.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "Kelionės išlaidos"
    table.rows[0].cells[1].text = "100 EUR"
    path = tmp_path / "t.docx"
    doc.save(path)
    pages = read_docx(str(path))
    assert pages[0]["page"] == 1
    assert "20 darbo dienų" in pages[0]["text"]
    assert "Kelionės išlaidos | 100 EUR" in pages[0]["text"]


def test_docx_virtual_pages_increase(tmp_path):
    doc = new_docx()
    for i in range(200):
        doc.add_paragraph(f"Pastraipa {i} " + "tekstas " * 20)
    path = tmp_path / "long.docx"
    doc.save(path)
    pages = read_docx(str(path))
    assert len(pages) > 3 and [p["page"] for p in pages] == list(range(1, len(pages) + 1))


def test_broken_docx_and_pdf_raise_friendly_error(tmp_path):
    bad = tmp_path / "bad.docx"
    bad.write_bytes(b"not a zip")
    with pytest.raises(UnreadableDocument):
        read_docx(str(bad))
    bad_pdf = tmp_path / "bad.pdf"
    bad_pdf.write_bytes(b"%PDF-1.4 garbage")
    with pytest.raises(UnreadableDocument):
        read_pdf(str(bad_pdf))


def test_password_protected_pdf_is_reported_as_such(tmp_path):
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.encrypt("secret")
    path = tmp_path / "locked.pdf"
    with open(path, "wb") as fh:
        writer.write(fh)
    with pytest.raises(UnreadableDocument, match="slaptažodžiu"):
        read_pdf(str(path))


def test_pdf_without_text_gives_no_pages(tmp_path):         # what a scanned PDF looks like to pypdf
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    path = tmp_path / "blank.pdf"
    with open(path, "wb") as fh:
        writer.write(fh)
    assert read_pdf(str(path)) == []


# ---------- real sample file ----------
@pytest.mark.skipif(not SAMPLE.exists(), reason="samples/metodiniai.pdf missing")
def test_sample_pdf_end_to_end():
    pages = read_pdf(str(SAMPLE))
    assert len(pages) >= 30
    before = sum(len(p["text"]) for p in pages)
    cleaned = [{**p, "text": clean_text(p["text"])} for p in strip_repeated_lines(pages)]
    after = sum(len(p["text"]) for p in cleaned)
    assert after < before                                    # the running header/footer was really removed
    chunks = chunk_pages(cleaned)
    assert chunks and all(len(c["text"]) <= 1000 for c in chunks)
    assert {c["page"] for c in chunks} <= {p["page"] for p in pages}


@pytest.mark.skipif(not SAMPLE.exists(), reason="samples/metodiniai.pdf missing")
def test_lithuanian_words_are_not_split_by_the_extractor():
    text = " ".join(p["text"] for p in read_pdf(str(SAMPLE)))
    assert "paraštės" in text and "rašomas" in text           # pypdf splits these ("r ašomas") on this file

import re
from collections import Counter

_HEADER_FOOTER_LINES = 3   # only the first/last 3 non-empty lines of a page are header/footer candidates


def clean_text(text: str) -> str:
    text = re.sub(r"\.{4,}", " ", text)      # dot leaders in a table of contents
    text = re.sub(r" {2,}", " ", text)       # runs of spaces
    text = re.sub(r" +\n", "\n", text)       # trailing spaces
    text = re.sub(r"\n{3,}", "\n\n", text)   # blank-line runs
    return text.strip()


def _shape(line: str) -> str:
    """Line with whitespace collapsed and stand-alone numbers masked, so '... 2024   5' and '... 2024   6' look equal."""
    return re.sub(r"\b\d+\b", "#", re.sub(r"\s+", " ", line)).strip()


def _edge_indexes(lines: list[str]) -> set[int]:
    """Indexes of the first/last few non-empty lines (nothing for very short pages: all of it would be 'edge')."""
    non_empty = [i for i, ln in enumerate(lines) if ln.strip()]
    if len(non_empty) <= 2 * _HEADER_FOOTER_LINES:
        return set()
    return set(non_empty[:_HEADER_FOOTER_LINES]) | set(non_empty[-_HEADER_FOOTER_LINES:])


def strip_repeated_lines(pages: list[dict], min_pages: int = 5, share: float = 0.4) -> list[dict]:
    """Drop running headers/footers: header/footer-zone lines that repeat on >= `share` of the pages."""
    if len(pages) < min_pages:
        return pages
    counts: Counter[str] = Counter()
    for page in pages:
        lines = page["text"].split("\n")
        counts.update({_shape(lines[i]) for i in _edge_indexes(lines)} - {""})
    repeated = {shape for shape, n in counts.items() if n >= share * len(pages)}
    result = []
    for page in pages:
        lines = page["text"].split("\n")
        edges = _edge_indexes(lines)
        kept = [ln for i, ln in enumerate(lines) if not (i in edges and _shape(ln) in repeated)]
        result.append({**page, "text": "\n".join(kept)})
    return result

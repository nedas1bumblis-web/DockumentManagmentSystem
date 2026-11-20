import re

_WHITESPACE = re.compile(r"\s")


def chunk_pages(pages: list[dict], size: int = 1000, overlap: int = 150) -> list[dict]:
    """Split page texts into overlapping chunks. Every chunk remembers its page.

    Returns [{'index': 0, 'page': 3, 'text': '...'}, ...] with index running over the whole document.
    """
    if size < 100:
        raise ValueError("size must be at least 100")
    if not 0 <= overlap < size // 2:
        raise ValueError("overlap must be between 0 and size/2")
    chunks: list[dict] = []
    for page in pages:
        for piece in _split(page["text"], size, overlap):
            chunks.append({"index": len(chunks), "page": page["page"], "text": piece})
    return chunks


def _split(text: str, size: int, overlap: int) -> list[str]:
    text = text.strip()
    if len(text) <= size:
        return [text] if text else []
    pieces, start = [], 0
    while True:
        end = min(start + size, len(text))
        if end < len(text):
            end = _soft_cut(text, start + size // 2, end)
        piece = text[start:end].strip()
        if piece:
            pieces.append(piece)
        if end >= len(text):
            return pieces
        start = max(end - overlap, start + 1)             # always moves forward -> no endless loop
        if not text[start - 1].isspace():                 # we landed inside a word: skip to the next gap
            gap = _WHITESPACE.search(text, start, end)
            if gap:
                start = gap.end()


def _soft_cut(text: str, low: int, high: int) -> int:
    """Prefer to cut at a paragraph, line, sentence or word boundary inside [low, high]."""
    for separator in ("\n\n", "\n", ". ", " "):
        position = text.rfind(separator, low, high)
        if position != -1:
            return position + len(separator)
    return high                                            # no boundary at all: hard cut

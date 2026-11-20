import time

from app_config import EMBEDDING_DIM, EMBEDDING_MODEL, USE_MOCK_AI
from rag.gemini_client import get_client, with_retries
from rag.mock_ai import mock_embed, normalize

BATCH_SIZE = 50                                   # the docs state no per-request cap, so stay conservative


def embed_texts(texts: list[str], task_type: str, client=None, sleep=time.sleep) -> list[list[float]]:
    """task_type: 'RETRIEVAL_DOCUMENT' for chunks, 'RETRIEVAL_QUERY' for questions (gemini-embedding-001)."""
    if USE_MOCK_AI:
        return [mock_embed(t, EMBEDDING_DIM) for t in texts]
    from google.genai import types
    client = client or get_client()
    config = types.EmbedContentConfig(task_type=task_type, output_dimensionality=EMBEDDING_DIM)
    vectors: list[list[float]] = []
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i:i + BATCH_SIZE]
        result = with_retries(
            lambda: client.models.embed_content(model=EMBEDDING_MODEL, contents=batch, config=config),
            sleep=sleep,
        )
        if len(result.embeddings) != len(batch):    # e.g. a model that merges a list into ONE embedding
            raise RuntimeError(f"Asked for {len(batch)} embeddings, got {len(result.embeddings)}")
        vectors.extend(normalize(list(e.values)) for e in result.embeddings)   # required below 3072 dims
    return vectors

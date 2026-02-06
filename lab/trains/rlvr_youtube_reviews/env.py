from __future__ import annotations

import asyncio
import math


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Return cosine similarity between two vectors.

    Cosine similarity measures the angle between vectors:
    - +1.0: same direction (very similar)
    -  0.0: orthogonal / no directional alignment
    - -1.0: opposite direction (very dissimilar)

    Implementation notes:
    - We compute: dot(a, b) / (||a|| * ||b||).
    - Range is [-1, 1] when both vectors have non-zero norm.
    - We return 0.0 if inputs are empty, have mismatched lengths, or either
      vector has zero norm (avoids divide-by-zero/NaNs and gives a neutral score).
    """
    # Guard against degenerate inputs (treat as "no similarity signal").
    if not a or not b or len(a) != len(b):
        return 0.0

    # Accumulate dot product and squared norms in one pass for efficiency.
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y

    # If either vector has zero magnitude, cosine similarity is undefined.
    # We return a neutral score (0.0) instead of raising/dividing by zero.
    if na <= 0.0 or nb <= 0.0:
        return 0.0

    # Normalize by magnitudes to get cosine of the angle between vectors.
    return dot / (math.sqrt(na) * math.sqrt(nb))


class OpenAIEmbedder:
    """Async OpenAI embeddings with small caching + concurrency limit."""

    def __init__(
        self,
        *,
        api_key: str,
        embedding_model: str = "text-embedding-3-small",
        base_url: str | None = None,
        max_concurrent: int = 32,
    ):
        from openai import AsyncOpenAI  # type: ignore

        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._embedding_model = embedding_model
        self._sem = asyncio.Semaphore(max_concurrent)
        self._cache: dict[str, list[float]] = {}

    async def embed(self, text: str) -> list[float]:
        text = text.strip()
        if not text:
            return []
        cached = self._cache.get(text)
        if cached is not None:
            return cached
        async with self._sem:
            resp = await self._client.embeddings.create(
                model=self._embedding_model, input=text
            )
        emb = [float(x) for x in resp.data[0].embedding]
        if len(self._cache) < 10_000:
            self._cache[text] = emb
        return emb

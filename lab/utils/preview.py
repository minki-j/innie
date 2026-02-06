from __future__ import annotations

from typing import Any


def preview_text(text: str, *, max_chars: int) -> str:
    s = text.replace("\r\n", "\n").replace("\r", "\n")
    if len(s) <= max_chars:
        return s
    return (
        s[: max(0, max_chars // 2 - 20)]
        + "...[TRUNCATED]..."
        + s[-max(0, max_chars // 2 - 20) :]
    )


def truncate_messages(
    messages: list[dict[str, str]], *, max_chars: int
) -> list[dict[str, str]]:
    truncated: list[dict[str, str]] = []
    for message in messages:
        truncated.append(
            {
                "role": message["role"],
                "content": preview_text(message["content"], max_chars=max_chars),
            }
        )
    return truncated


def preview_tokens(tokens: list[int], *, max_tokens: int) -> dict[str, Any]:
    if len(tokens) <= max_tokens:
        return {"len": len(tokens), "tokens": tokens}
    return {"len": len(tokens), "tokens_head": tokens[:max_tokens]}


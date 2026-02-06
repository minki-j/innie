from __future__ import annotations

from typing import Any
from collections.abc import Mapping


def to_int_list(x: Any) -> list[int]:
    """
    Normalize various tokenizer outputs into a plain `list[int]`.

    Handles:
    - None -> []
    - list[int]
    - list[list[int]] (single-item batch)
    - dict-like containers (e.g. HuggingFace BatchEncoding) with `input_ids`
    - numpy/torch containers exposing `.tolist()`
    - generic iterables of ints
    """
    if x is None:
        return []
    if isinstance(x, Mapping):
        # Some APIs (e.g. HuggingFace `apply_chat_template` with certain args/versions)
        # return a dict/BatchEncoding like {"input_ids": ..., "attention_mask": ...}.
        if "input_ids" in x:
            return to_int_list(x["input_ids"])
        raise TypeError(
            "Unsupported mapping token container (missing 'input_ids'): "
            f"keys={list(x.keys())!r}"
        )
    if isinstance(x, list):
        if not x:
            return []
        # Some tokenizers return a batch (list[list[int]]) even for a single prompt.
        if isinstance(x[0], list):
            if len(x) != 1:
                raise ValueError(f"Expected a single sequence, got batch of {len(x)}")
            return [int(t) for t in x[0]]
        return [int(t) for t in x]
    if hasattr(x, "tolist"):
        return to_int_list(x.tolist())
    try:
        return [int(t) for t in x]
    except TypeError as e:
        raise TypeError(f"Unsupported token container type: {type(x)!r}") from e

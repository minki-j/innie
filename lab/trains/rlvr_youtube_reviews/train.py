from __future__ import annotations

import asyncio
import argparse
import json
import logging
import os
import random
import sys
import tempfile
from dataclasses import dataclass
from dataclasses import asdict as dataclass_asdict
from datetime import datetime, timezone
from pathlib import Path
from enum import Enum
from typing import Any, cast

import numpy as np
import tinker

from utils.fs import find_repo_root, load_dotenv
from utils.preview import preview_text, preview_tokens
from utils.tokens import to_int_list

from .dataset import YouTubeReviewDatapoint, load_datapoints
from .env import OpenAIEmbedder, cosine_similarity

PERSONA_FEEDBACK_SYSTEM_PROMPT_TEMPLATE = """
Write a realistic review comment someone would leave after watching the talk.

IMPORTANT:
- Be specific, technical where appropriate, and grounded in the provided content.
- Be colloquial.
- Do not use markdown formatting. Just use plain text.
- Do not use preamble like "Here's my review..." or "Review:". Just write the review directly and finish it when you're done.
- Don't ramble. Be succint. Aim to not exceed 400 words.
- Break the review in multiple paragraphs with double newlines.
""".strip()


PERSONA_FEEDBACK_USER_PROMPT_TEMPLATE = """
Title:
{title}

Summary:
{summary}

Transcript:
{transcript}
""".strip()


@dataclass(frozen=True)
class PersonaEnum(Enum):
    PRINCIPAL_ENGINEER_INFERENCE = "principal_engineer_inference"
    JUNIOR_ENGINEER_SIDE_PROJECTS = "junior_engineer_side_projects"
    EXECUTIVE_AI_STRATEGY = "executive_ai_strategy"


@dataclass(frozen=True)
class Config:
    dry_run: bool = False
    base_model: str = "meta-llama/Llama-3.1-8B-Instruct"
    lora_rank: int = 32
    # Relative to repo root by default (we resolve it at runtime)
    jsonl_path: str = "lab/datasets/ai_dot_engineer/dataset_train.jsonl"
    persona_id: str | None = PersonaEnum.JUNIOR_ENGINEER_SIDE_PROJECTS.value

    # RL batching
    steps: int = 50
    groups_per_batch: int = 2  # datapoints per step
    group_size: int = 8  # rollouts per datapoint
    seed: int = 0

    # Sampling
    max_tokens: int = 512
    temperature: float = 1.0
    sampling_concurrency: int = 80  # concurrent datapoints sampled per step

    # Training
    learning_rate: float = 1e-4
    grad_clip_norm: float = 0.0

    # KL regularization
    kl_penalty_coef: float = 1.0
    kl_discount_factor: float = 0.0
    kl_reference_model: str | None = None  # default: same as `base_model`
    kl_reference_checkpoint_path: str | None = None  # optional reference checkpoint

    # Checkpointing
    checkpoint_every_steps: int = 5  # 0 = only save final checkpoint
    checkpoint_name_prefix: str = "rlvr_youtube_reviews"
    checkpoint_ttl_seconds: int | None = None  # None = never expires

    # Embeddings
    openai_api_key_env: str = "OPENAI_API_KEY"
    openai_base_url: str | None = None
    openai_embedding_model: str = "text-embedding-3-small"
    embed_max_concurrent: int = 64

    # Logging
    log_level: str = "DEBUG"
    log_timestamp: bool = False
    log_prompt_text: bool = False
    log_completions: bool = True
    log_max_preview_chars: int = 600
    log_max_preview_tokens: int = 80
    run_logs_dir: str = "lab/trains/rlvr_youtube_reviews/logs"

    # Miscellaneous
    transcript_max_chars_in_prompt: int = 20_000


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TrainingResult:
    """Result from a training run."""

    checkpoint_path: str
    metrics: dict[str, Any]


def _truncate_transcript_for_prompt(transcript: str, *, max_chars: int) -> str:
    """
    Hard-truncate transcript text for prompt construction.

    This is intentionally character-based (not token-based): it's a simple guardrail
    to reduce prompt size when transcripts are huge.
    """
    if max_chars <= 0:
        return transcript
    s = transcript.replace("\r\n", "\n").replace("\r", "\n")
    if len(s) <= max_chars:
        return s
    return s[:max_chars] + "...[TRUNCATED]..."


def build_prompt(
    dp: YouTubeReviewDatapoint, *, transcript_max_chars_in_prompt: int
) -> str:
    system, user = _system_user_for_dp(
        dp, transcript_max_chars_in_prompt=transcript_max_chars_in_prompt
    )
    # `tinker` sampling here takes a single text prompt, but many base models expect
    # special role tokens / chat templates (which vary by model+tokenizer). We build a
    # structured chat message list and prefer the tokenizer's chat template when possible.
    return f"System:\n{system}\n\nUser:\n{user}\n"


def _system_user_for_dp(
    dp: YouTubeReviewDatapoint, *, transcript_max_chars_in_prompt: int
) -> tuple[str, str]:
    system = PERSONA_FEEDBACK_SYSTEM_PROMPT_TEMPLATE.strip()
    transcript = _truncate_transcript_for_prompt(
        dp.transcript.strip(), max_chars=transcript_max_chars_in_prompt
    )
    user = PERSONA_FEEDBACK_USER_PROMPT_TEMPLATE.format(
        title=dp.title,
        summary=dp.summary.strip(),
        transcript=transcript,
    ).strip()
    return system, user


def _messages_for_dp(
    dp: YouTubeReviewDatapoint, *, transcript_max_chars_in_prompt: int
) -> tuple[str, list[dict[str, str]]]:
    """
    Returns:
      - prompt_text_fallback: a plain-text prompt (for tokenizers without chat templates)
      - messages: [{"role": ..., "content": ...}, ...] for chat-templated tokenization
    """
    system, user = _system_user_for_dp(
        dp, transcript_max_chars_in_prompt=transcript_max_chars_in_prompt
    )

    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": user})
    return messages


def _try_encode_llama_instruct_chat(
    *,
    tokenizer: Any,
    messages: list[dict[str, str]],
    add_generation_prompt: bool,
) -> list[int] | None:
    """
    Best-effort manual chat formatting for Llama-family instruct models.

    We only attempt this if the tokenizer appears to know the expected special tokens,
    otherwise return None and let the caller fall back to plain-text formatting.
    """

    def _has_token(tok: str) -> bool:
        try:
            tok_id = tokenizer.convert_tokens_to_ids(tok)
        except Exception:
            return False
        if tok_id is None:
            return False
        unk_id = getattr(tokenizer, "unk_token_id", None)
        if unk_id is not None and tok_id == unk_id:
            return False
        return True

    bos = "<|begin_of_text|>"
    start_header = "<|start_header_id|>"
    end_header = "<|end_header_id|>"
    eot = "<|eot_id|>"

    if not all(_has_token(t) for t in (bos, start_header, end_header, eot)):
        return None

    parts: list[str] = [bos]
    for m in messages:
        role = m.get("role", "user")
        content = (m.get("content") or "").strip()
        # Llama templates typically separate header/content with blank line.
        parts.append(f"{start_header}{role}{end_header}\n\n{content}{eot}\n")

    if add_generation_prompt:
        parts.append(f"{start_header}assistant{end_header}\n\n")

    text = "".join(parts)
    try:
        return to_int_list(tokenizer.encode(text, add_special_tokens=False))
    except Exception:
        return None


def build_prompt_tokens(
    dp: YouTubeReviewDatapoint,
    *,
    tokenizer: Any,
    model_name: str,
    transcript_max_chars_in_prompt: int,
) -> list[int]:
    messages = _messages_for_dp(
        dp, transcript_max_chars_in_prompt=transcript_max_chars_in_prompt
    )

    # Prefer model-specific role tokens / templates.
    if hasattr(tokenizer, "apply_chat_template"):
        try:
            tokens = tokenizer.apply_chat_template(  # type: ignore[attr-defined]
                messages,
                tokenize=True,
                add_generation_prompt=True,
            )
            return to_int_list(tokens)
        except Exception as e:
            logger.error(
                "apply_chat_template failed: %s",
                e,
            )

        # Fallback: manual Llama-Instruct formatting when special tokens are present.
        if "llama" in (model_name or "").lower():
            logger.debug("Attempting manual llama-instruct chat formatting fallback")
            maybe_tokens = _try_encode_llama_instruct_chat(
                tokenizer=tokenizer, messages=messages, add_generation_prompt=True
            )
            if maybe_tokens is not None:
                logger.debug(
                    "successfully applied manual llama-instruct chat formatting fallback"
                )
                return maybe_tokens
    else:
        logger.warning(
            "🚨 tokenizer doesn't have apply_chat_template; Can't proceed without proper token instruction. Please check the model documentation and create a manual formatter",
        )
        raise


async def sample_group(
    *,
    sampling_client: tinker.SamplingClient,
    tokenizer: Any,
    dp: YouTubeReviewDatapoint,
    group_size: int,
    max_tokens: int,
    temperature: float,
    transcript_max_chars_in_prompt: int,
    model_name: str,
) -> list[tinker.types.SampledSequence]:
    prompt_tokens = build_prompt_tokens(
        dp,
        tokenizer=tokenizer,
        model_name=model_name,
        transcript_max_chars_in_prompt=transcript_max_chars_in_prompt,
    )
    prompt = tinker.types.ModelInput.from_ints(prompt_tokens)
    params = tinker.types.SamplingParams(max_tokens=max_tokens, temperature=temperature)
    logger.debug(
        "tinker.sample_async(group) prompt=%s sampling_params=%s",
        preview_tokens(prompt_tokens, max_tokens=80),
        {"max_tokens": max_tokens, "temperature": temperature},
    )
    resp = await sampling_client.sample_async(
        prompt=prompt, num_samples=group_size, sampling_params=params
    )
    if hasattr(resp, "samples"):
        return resp.samples  # type: ignore[attr-defined]
    if hasattr(resp, "sequences"):
        return resp.sequences  # type: ignore[attr-defined]
    raise AttributeError("SampleResponse has neither `.samples` nor `.sequences`")


def _build_rl_datum(
    *,
    prompt_tokens: list[int],
    completion_tokens: list[int],
    completion_logprobs: list[float] | None,
    advantage: float,
) -> tinker.types.Datum:
    """Build a token-level RL training datum for a sampled completion.

    This constructs a `tinker.types.Datum` suitable for a next-token loss where:

    - `model_input` is a sequence of input tokens (x)
    - `target_tokens` is the same sequence shifted left by 1 (y)
      so that `y[i]` is the desired next token after seeing `x[: i + 1]`

    RL-specific pieces are carried in `loss_fn_inputs`:

    - `logprobs`: the sampling-time log-probability for each *completion* target
      token. Prompt targets are filled with 0s.
    - `advantages`: the scalar advantage broadcast over completion target
      tokens. Prompt targets are filled with 0s (so we do not apply RL updates to
      prompt/context tokens).

    Indexing detail (the subtle part):
    `target_tokens` is `full[1:]`, so the *first* completion token
    (`completion_tokens[0]`, which is `full[len(prompt_tokens)]`) appears in
    `target_tokens` at index `len(prompt_tokens) - 1`. That is why `start` is
    computed as `len(prompt_tokens) - 1` (clamped at 0 for very short prompts).

    Args:
        prompt_tokens: Token ids for the prompt/context shown to the model.
        completion_tokens: Token ids sampled from the model after the prompt.
        completion_logprobs: Sampling-time log-probabilities corresponding to
            `completion_tokens` (one per sampled token). If `None`, we leave the
            `logprobs`/`advantages` arrays as all-zeros.
        advantage: Scalar advantage/reward signal to apply to completion tokens.

    Returns:
        A `tinker.types.Datum` containing:
        - `model_input`: `full[:-1]`
        - `loss_fn_inputs["target_tokens"]`: `full[1:]`
        - `loss_fn_inputs["logprobs"]`: zeros for prompt targets, then the
          provided completion logprobs (truncated if needed)
        - `loss_fn_inputs["advantages"]`: zeros for prompt targets, then
          `advantage` for completion targets (truncated if needed)
    """

    # Full token sequence the model "experienced" during sampling:
    # prompt context followed by the sampled completion.
    full = prompt_tokens + completion_tokens
    if len(full) < 2:
        # Degenerate: we can't form even a single (input -> target) pair.
        # Return an "empty" datum with correctly-typed arrays so downstream code
        # doesn't have to special-case `None`.
        return tinker.types.Datum(
            model_input=tinker.types.ModelInput.from_ints([]),
            loss_fn_inputs={
                "target_tokens": np.array([], dtype=np.int64),
                "logprobs": np.array([], dtype=np.float32),
                "advantages": np.array([], dtype=np.float32),
            },
        )

    # Standard language-model next-token training format:
    # - inputs are everything except the last token
    # - targets are everything except the first token
    # so that targets[i] is the "next token" after inputs[:i+1].
    input_tokens = full[:-1]
    target_tokens = full[1:]
    n = len(input_tokens)

    # Token-level arrays must align with `target_tokens` (length `n`).
    #
    # We only have sampling logprobs for the sampled completion tokens, not for
    # prompt tokens (which are fixed context), so:
    # - prompt-aligned positions stay 0
    # - completion-aligned positions are filled with provided values
    sampling_logprobs = np.zeros((n,), dtype=np.float32)
    advantages = np.zeros((n,), dtype=np.float32)
    # Client-side only: marks which target positions correspond to sampled action
    # tokens (completion). We will STRIP this before sending datums to Tinker,
    # because the server-side `importance_sampling` loss does not accept extra
    # fields.
    action_mask = np.zeros((n,), dtype=np.float32)

    # `target_tokens` is shifted by 1, so completion token j maps to:
    #   full index:   len(prompt_tokens) + j
    #   target index: (len(prompt_tokens) + j) - 1  == len(prompt_tokens) - 1 + j
    start = max(0, len(prompt_tokens) - 1)
    if completion_logprobs is not None:
        # Be defensive about shape mismatches:
        # - sampling might return fewer/more logprobs than tokens
        # - extremely short sequences can make `n - start` small
        m = min(len(completion_logprobs), n - start)
        sampling_logprobs[start : start + m] = np.array(
            completion_logprobs[:m], dtype=np.float32
        )
        advantages[start : start + m] = float(advantage)
        action_mask[start : start + m] = 1.0

    return tinker.types.Datum(
        model_input=tinker.types.ModelInput.from_ints(input_tokens),
        loss_fn_inputs={
            "target_tokens": np.array(target_tokens, dtype=np.int64),
            "logprobs": sampling_logprobs,
            "advantages": advantages,
            "mask": action_mask,
        },
    )


def _strip_client_only_loss_inputs(datum: tinker.types.Datum) -> tinker.types.Datum:
    """
    Return a copy of `datum` safe to send to `forward_backward_async`.

    For `loss_fn="importance_sampling"`, Tinker expects exactly:
      - target_tokens
      - logprobs
      - advantages

    Extra keys (like `mask`) can trigger server-side array-record conversion errors.
    """
    allowed = {"target_tokens", "logprobs", "advantages"}
    return tinker.types.Datum(
        model_input=datum.model_input,
        loss_fn_inputs={k: v for k, v in datum.loss_fn_inputs.items() if k in allowed},
    )


def _discounted_future_sum(x: np.ndarray, gamma: float) -> np.ndarray:
    """
    Compute discounted sum of future values for each position.

    y[t] = x[t] + gamma * x[t+1] + gamma^2 * x[t+2] + ...
    """
    if gamma <= 0:
        return x
    y = x.astype(np.float32, copy=True)
    running = 0.0
    for i in range(len(y) - 1, -1, -1):
        running = float(y[i]) + float(gamma) * running
        y[i] = running
    return y


async def _incorporate_kl_penalty(
    datums: list[tinker.types.Datum],
    *,
    base_sampling_client: tinker.SamplingClient,
    kl_penalty_coef: float,
    kl_discount_factor: float,
) -> dict[str, float]:
    """
    Cookbook-style KL regularization, implemented as an advantage adjustment.

    For each datum, compute tokenwise logp_current - logp_base for action tokens
    (completion tokens), average this across the batch, and add:
      kl_adv = kl_penalty_coef * mask * (avg_logp_diff - (logp_current - logp_base))
    optionally with a discounted future-sum.
    """
    if kl_penalty_coef <= 0:
        return {}

    def _as_numpy(x: Any, *, dtype: Any | None) -> np.ndarray:
        """
        Convert loss_fn_inputs values to numpy.

        In Tinker, `loss_fn_inputs` entries may be plain numpy/torch arrays *or*
        `tinker.TensorData` (pydantic) wrappers.
        """
        to_numpy = getattr(x, "to_numpy", None)
        if callable(to_numpy):
            arr = to_numpy()
        else:
            arr = np.asarray(x)
        if dtype is not None:
            arr = arr.astype(dtype, copy=False)
        return arr

    full_sequence_inputs: list[tinker.types.ModelInput] = []
    datum_indices: list[int] = []
    for i, datum in enumerate(datums):
        target_tokens = _as_numpy(datum.loss_fn_inputs["target_tokens"], dtype=np.int64)
        if target_tokens.size == 0:
            continue
        full_sequence_inputs.append(
            datum.model_input.append_int(int(target_tokens[-1]))
        )
        datum_indices.append(i)

    if not full_sequence_inputs:
        return {"kl_policy_base": 0.0}

    base_logprobs_list = await asyncio.gather(
        *[
            base_sampling_client.compute_logprobs_async(sequence_input)
            for sequence_input in full_sequence_inputs
        ]
    )

    # First pass: compute batch-average logp diff on action tokens.
    total_diff = 0.0
    total_mask = 0.0
    per_datum: list[tuple[int, np.ndarray, np.ndarray]] = []

    for idx, base_logprobs in zip(datum_indices, base_logprobs_list):
        datum = datums[idx]
        sampled_logprobs = _as_numpy(datum.loss_fn_inputs["logprobs"], dtype=np.float32)
        # Prefer an explicit action-token mask when available (robust).
        # Fall back to a heuristic only if needed.
        if "mask" in datum.loss_fn_inputs:
            mask = _as_numpy(datum.loss_fn_inputs["mask"], dtype=np.float32)
        else:
            # Heuristic fallback: prompt-aligned positions are padded with 0.0.
            # Note: this can be wrong if a sampled logprob is exactly 0.0.
            mask = (np.abs(sampled_logprobs) > 1e-8).astype(np.float32)
        base_lp = np.asarray(base_logprobs[1:], dtype=np.float32)  # align to targets

        m = min(len(sampled_logprobs), len(mask), len(base_lp))
        if m <= 0:
            continue
        sampled_logprobs = sampled_logprobs[:m]
        mask = mask[:m]
        base_lp = base_lp[:m]

        diff = (sampled_logprobs - base_lp) * mask
        total_diff += float(diff.sum())
        total_mask += float(mask.sum())
        per_datum.append((idx, diff, mask))

    if total_mask <= 0:
        return {"kl_policy_base": 0.0}

    avg_logp_diff = total_diff / total_mask

    # Second pass: apply the advantage adjustment in-place.
    for idx, diff, mask in per_datum:
        datum = datums[idx]
        advantages = _as_numpy(datum.loss_fn_inputs["advantages"], dtype=np.float32)

        kl_adv = (float(kl_penalty_coef) * mask * (float(avg_logp_diff) - diff)).astype(
            np.float32
        )
        if kl_discount_factor > 0:
            kl_adv = _discounted_future_sum(kl_adv, float(kl_discount_factor)).astype(
                np.float32
            )

        n = min(len(advantages), len(kl_adv))
        if n > 0:
            advantages = advantages.copy()
            advantages[:n] = advantages[:n] + kl_adv[:n]
            datum.loss_fn_inputs["advantages"] = advantages

    return {"kl_policy_base": float(avg_logp_diff)}


def _now_run_id() -> str:
    # Local time, filesystem-friendly.
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _atomic_write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        delete=False,
        dir=str(path.parent),
        prefix=path.name + ".",
        suffix=".tmp",
    ) as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
        tmp = Path(f.name)
    tmp.replace(path)


def _ensure_unique_run_dir(root: Path, run_id: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    # Prefer run_id exactly; fall back to suffixes if needed.
    for i in range(0, 10_000):
        name = run_id if i == 0 else f"{run_id}_{i:04d}"
        p = root / name
        try:
            p.mkdir(parents=True, exist_ok=False)
            return p
        except FileExistsError:
            continue
    raise RuntimeError(f"Failed to create unique run dir under {root}")


def _is_number(x: Any) -> bool:
    # Exclude booleans (they're ints in Python).
    return isinstance(x, (int, float, np.number)) and not isinstance(x, bool)


def _as_float(x: Any) -> float | None:
    if _is_number(x):
        return float(x)
    return None


def _compute_stats(xs: list[float]) -> dict[str, float]:
    a = np.asarray(xs, dtype=np.float32)
    if a.size == 0:
        return {
            "mean": 0.0,
            "std": 0.0,
            "min": 0.0,
            "max": 0.0,
            "p10": 0.0,
            "p50": 0.0,
            "p90": 0.0,
        }
    return {
        "mean": float(a.mean()),
        "std": float(a.std()),
        "min": float(a.min()),
        "max": float(a.max()),
        "p10": float(np.percentile(a, 10)),
        "p50": float(np.percentile(a, 50)),
        "p90": float(np.percentile(a, 90)),
    }


def _save_training_plots(
    *,
    metadata: dict[str, Any],
    generations_path: Path,
    out_dir: Path,
) -> None:
    """
    Generate additional high-signal plots for RLVR training.

    Plots are written into `out_dir` and are safe to call repeatedly (overwrites).
    """
    steps: list[dict[str, Any]] = cast(list[dict[str, Any]], metadata.get("steps", []))
    if not steps:
        return

    # Import lazily so this module can be imported without matplotlib.
    import matplotlib

    matplotlib.use("Agg")  # headless
    import matplotlib.pyplot as plt

    out_dir.mkdir(parents=True, exist_ok=True)

    xs = [int(s.get("step", i + 1)) for i, s in enumerate(steps)]
    avg_reward = [float(s.get("avg_reward", 0.0)) for s in steps]

    # 1) Reward stats per step (mean + p10/p90 band).
    r_p10 = [float(s.get("reward_p10", s.get("avg_reward", 0.0))) for s in steps]
    r_p90 = [float(s.get("reward_p90", s.get("avg_reward", 0.0))) for s in steps]
    plt.figure(figsize=(8, 4.5))
    plt.plot(xs, avg_reward, marker="o", linewidth=2, label="avg")
    plt.fill_between(xs, r_p10, r_p90, alpha=0.2, label="p10–p90")
    plt.title("Reward stats per step")
    plt.xlabel("Step")
    plt.ylabel("Reward")
    plt.grid(True, alpha=0.3)
    plt.legend(loc="best")
    plt.tight_layout()
    plt.savefig(out_dir / "reward_stats_per_step.png", dpi=160)
    plt.close()

    # 2) Completion length stats per step (mean + p10/p90 band).
    len_mean = [float(s.get("completion_len_mean", 0.0)) for s in steps]
    len_p10 = [
        float(s.get("completion_len_p10", s.get("completion_len_mean", 0.0)))
        for s in steps
    ]
    len_p90 = [
        float(s.get("completion_len_p90", s.get("completion_len_mean", 0.0)))
        for s in steps
    ]
    plt.figure(figsize=(8, 4.5))
    plt.plot(xs, len_mean, marker="o", linewidth=2, label="avg")
    plt.fill_between(xs, len_p10, len_p90, alpha=0.2, label="p10–p90")
    plt.title("Completion length stats per step")
    plt.xlabel("Step")
    plt.ylabel("Completion length (tokens)")
    plt.grid(True, alpha=0.3)
    plt.legend(loc="best")
    plt.tight_layout()
    plt.savefig(out_dir / "completion_len_per_step.png", dpi=160)
    plt.close()

    # 3) Optim metrics per step (one subplot per numeric metric).
    metric_series: dict[str, list[float | None]] = {}
    for s in steps:
        optim = s.get("optim_metrics") or {}
        if not isinstance(optim, dict):
            optim = {}
        for k, v in optim.items():
            fv = _as_float(v)
            if fv is None:
                continue
            metric_series.setdefault(str(k), []).append(fv)

    # Ensure all series align to number of steps (fill missing as None).
    for k, series in list(metric_series.items()):
        if len(series) < len(steps):
            series.extend([None] * (len(steps) - len(series)))
        metric_series[k] = series

    if metric_series:
        keys = sorted(metric_series.keys())
        n = len(keys)
        cols = 2
        rows = (n + cols - 1) // cols
        fig, axes = plt.subplots(
            rows,
            cols,
            figsize=(10, 2.8 * rows),
            squeeze=False,
        )
        for i, k in enumerate(keys):
            ax = axes[i // cols][i % cols]
            ys = metric_series[k]
            xs_present: list[int] = []
            ys_present: list[float] = []
            for x, y in zip(xs, ys):
                if y is None:
                    continue
                xs_present.append(int(x))
                ys_present.append(float(y))
            if xs_present:
                ax.plot(xs_present, ys_present, marker="o", linewidth=2)
            ax.set_title(k)
            ax.grid(True, alpha=0.3)
            ax.set_xlabel("Step")
        # Hide unused axes.
        for j in range(n, rows * cols):
            axes[j // cols][j % cols].axis("off")
        fig.suptitle("Optim metrics per step")
        fig.tight_layout()
        fig.savefig(out_dir / "optim_metrics_per_step.png", dpi=160)
        plt.close(fig)

    # 4) KL metric (if present).
    kl_series: list[float] = []
    xs_kl: list[int] = []
    for x, s in zip(xs, steps):
        kl = s.get("kl_metrics") or {}
        if not isinstance(kl, dict):
            continue
        if "kl_policy_base" in kl:
            fv = _as_float(kl.get("kl_policy_base"))
            if fv is not None:
                xs_kl.append(int(x))
                kl_series.append(float(fv))
    if xs_kl:
        plt.figure(figsize=(8, 4.5))
        plt.plot(xs_kl, kl_series, marker="o", linewidth=2)
        plt.title("KL (policy vs reference) per step")
        plt.xlabel("Step")
        plt.ylabel("Avg logp(current) - logp(reference) on action tokens")
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig(out_dir / "kl_policy_base_per_step.png", dpi=160)
        plt.close()

    # 5) Reward vs completion length scatter.
    # We parse `generations.jsonl` to avoid duplicating bulky per-sample info in metadata.
    rewards_all: list[float] = []
    lens_all: list[float] = []
    if generations_path.exists():
        try:
            with generations_path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    rec = json.loads(line)
                    st = int(rec.get("step", 0))
                    r = _as_float(rec.get("reward"))
                    comp_len = _as_float(rec.get("completion_len"))
                    if st <= 0 or r is None or comp_len is None:
                        continue
                    rewards_all.append(float(r))
                    lens_all.append(float(comp_len))
        except Exception:
            # Plotting should never break training; just skip these plots.
            rewards_all = []
            lens_all = []

    if rewards_all and lens_all:
        plt.figure(figsize=(8, 5))
        plt.scatter(lens_all, rewards_all, s=10, alpha=0.35)
        plt.title("Reward vs completion length (all samples)")
        plt.xlabel("Completion length (tokens)")
        plt.ylabel("Reward")
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig(out_dir / "reward_vs_completion_len.png", dpi=160)
        plt.close()


async def train(
    cfg: Config,
    *,
    datapoints_override: list | None = None,
) -> TrainingResult:
    """
    Run RLVR training.

    Args:
        cfg: Training configuration.
        datapoints_override: If provided, use these datapoints instead of
            loading from the JSONL file. Used by the server to pass DB-sourced data.

    Returns:
        TrainingResult with checkpoint_path and metrics.
    """
    log_format = "%(levelname)s %(name)s\n%(message)s\n"
    if cfg.log_timestamp:
        log_format = "%(asctime)s " + log_format
    logging.basicConfig(
        level=getattr(logging, cfg.log_level.upper(), logging.INFO),
        format=log_format,
    )
    # Keep our own debug logging, but suppress noisy third-party libraries.
    # `httpcore.http2` in particular is extremely chatty at DEBUG.
    for noisy in (
        "httpcore",
        "httpx",
        "h2",
        "hpack",
        "urllib3",
        "openai",
        "tinker",
        "asyncio",
        "matplotlib",
    ):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    repo_root = find_repo_root(Path(__file__).resolve().parent)
    load_dotenv(repo_root / ".env")
    rng = random.Random(cfg.seed)

    # Run artifact directory (timestamped)
    run_root = (repo_root / cfg.run_logs_dir).resolve()
    run_id = _now_run_id()
    run_dir = _ensure_unique_run_dir(run_root, run_id)
    metadata_path = run_dir / "metadata.json"
    generations_path = run_dir / "generations.jsonl"

    metadata: dict[str, Any] = {
        "run_id": run_dir.name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "run_dir": str(run_dir),
        "script": str(Path(__file__).resolve()),
        "config": dataclass_asdict(cfg),
        "steps": [],
    }
    _atomic_write_json(metadata_path, metadata)

    if datapoints_override is not None:
        datapoints = datapoints_override
        rng.shuffle(datapoints)
        logger.info("using %d datapoints from override", len(datapoints))
    else:
        jsonl_path = str((repo_root / cfg.jsonl_path).resolve())
        all_datapoints = load_datapoints(jsonl_path)
        datapoints = all_datapoints
        if cfg.persona_id is not None:
            pid = str(cfg.persona_id).strip()
            datapoints = [dp for dp in all_datapoints if dp.persona_id == pid]
            logger.info(
                "persona filter enabled persona_id=%s kept=%d/%d",
                pid,
                len(datapoints),
                len(all_datapoints),
            )
        rng.shuffle(datapoints)
    if not datapoints:
        raise RuntimeError("No datapoints available for training")

    api_key = os.environ.get(cfg.openai_api_key_env)
    if api_key is None or not api_key.strip():
        raise RuntimeError(
            f"{cfg.openai_api_key_env} is not set (needed for embedding reward)."
        )

    embedder = OpenAIEmbedder(
        api_key=api_key,
        embedding_model=cfg.openai_embedding_model,
        base_url=cfg.openai_base_url,
        max_concurrent=cfg.embed_max_concurrent,
    )

    service_client = tinker.ServiceClient()
    training_client = await service_client.create_lora_training_client_async(
        base_model=cfg.base_model, rank=cfg.lora_rank
    )
    tokenizer = training_client.get_tokenizer()
    logger.info(
        "training init base_model=%s lora_rank=%s tokenizer=%s",
        cfg.base_model,
        cfg.lora_rank,
        type(tokenizer).__name__,
    )
    logger.info(
        "logging config level=%s timestamp=%s prompt_text=%s completions=%s",
        cfg.log_level.upper(),
        cfg.log_timestamp,
        cfg.log_prompt_text,
        cfg.log_completions,
    )

    # Initial sampling client
    sampling_client = await training_client.save_weights_and_get_sampling_client_async()

    # Optional KL reference model for reward-style KL regularization.
    kl_reference_client: tinker.SamplingClient | None = None
    if cfg.kl_penalty_coef > 0:
        ref_model = cfg.kl_reference_model or cfg.base_model
        kl_reference_client = service_client.create_sampling_client(
            base_model=ref_model,
            model_path=cfg.kl_reference_checkpoint_path,
        )
        logger.info(
            "kl_penalty enabled coef=%s discount_factor=%s reference_model=%s reference_checkpoint=%s",
            cfg.kl_penalty_coef,
            cfg.kl_discount_factor,
            ref_model,
            cfg.kl_reference_checkpoint_path,
        )

    sampling_sem = asyncio.Semaphore(max(1, cfg.sampling_concurrency))
    avg_rewards_per_step: list[float] = []

    for step in range(cfg.steps):
        # Select datapoints for this step
        start = (step * cfg.groups_per_batch) % len(datapoints)
        batch = datapoints[start : start + cfg.groups_per_batch]
        if len(batch) < cfg.groups_per_batch:
            batch = batch + datapoints[0 : cfg.groups_per_batch - len(batch)]

        async def run_one(
            dp: YouTubeReviewDatapoint,
        ) -> tuple[
            YouTubeReviewDatapoint,
            list[tinker.types.SampledSequence],
            list[int],
            str,
        ]:
            async with sampling_sem:
                prompt_tokens = build_prompt_tokens(
                    dp,
                    tokenizer=tokenizer,
                    model_name=cfg.base_model,
                    transcript_max_chars_in_prompt=cfg.transcript_max_chars_in_prompt,
                )
                prompt_text_for_logs = build_prompt(
                    dp,
                    transcript_max_chars_in_prompt=cfg.transcript_max_chars_in_prompt,
                )
                if cfg.log_prompt_text:
                    logger.debug(
                        "prompt_text title=%r preview=%r",
                        dp.title,
                        preview_text(
                            prompt_text_for_logs, max_chars=cfg.log_max_preview_chars
                        ),
                    )

                prompt = tinker.types.ModelInput.from_ints(prompt_tokens)
                params = tinker.types.SamplingParams(
                    max_tokens=cfg.max_tokens, temperature=cfg.temperature
                )
                resp: tinker.types.SampleResponse = await sampling_client.sample_async(
                    prompt=prompt, num_samples=cfg.group_size, sampling_params=params
                )
                samples = resp.sequences
                return dp, samples, prompt_tokens, prompt_text_for_logs

        # Run all datapoints in batch concurrently
        results = await asyncio.gather(*[run_one(dp) for dp in batch])

        # Compute rewards + build datums
        datums: list[tinker.types.Datum] = []
        all_rewards: list[float] = []
        all_completion_lens: list[float] = []
        step_generations_written = 0
        with generations_path.open("a", encoding="utf-8") as gf:
            for dp, samples, prompt_tokens, prompt_text_for_logs in results:
                # Embed target once per datapoint
                target_emb = dp.feedback_embedding
                if target_emb is None:
                    target_emb = await embedder.embed(dp.synthetic_user_feedback)

                rewards: list[float] = []
                decoded_texts: list[str] = []
                for s in samples:
                    completion_tokens = list(s.tokens)
                    text = tokenizer.decode(completion_tokens)
                    decoded_texts.append(text)

                    pred_emb = await embedder.embed(text)
                    sim = cosine_similarity(pred_emb, target_emb)
                    if sim == 0.0:
                        logger.warning(
                            "zero similarity for datapoint %s", dp.example_id
                        )
                    rewards.append(sim)

                mean_r = sum(rewards) / max(1, len(rewards))

                # Persist generations: input text + generation text + score.
                for i, (s, text, r) in enumerate(zip(samples, decoded_texts, rewards)):
                    completion_len = int(len(list(s.tokens)))
                    rec = {
                        "step": step + 1,
                        "example_id": dp.example_id,
                        "video_id": dp.video_id,
                        "video_url": dp.video_url,
                        "title": dp.title,
                        "persona_id": dp.persona_id,
                        "persona_title": dp.persona_title,
                        "target_generation": dp.synthetic_user_feedback,
                        "generation_text": text,
                        "reward": float(r),
                        "advantage": float(r - mean_r),
                        "mean_reward_for_datapoint": float(mean_r),
                        "sample_index": int(i),
                        "completion_len": completion_len,
                    }
                    gf.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    step_generations_written += 1
                    all_completion_lens.append(float(completion_len))

                for s, r, completion_len in zip(samples, rewards, all_completion_lens):
                    # 500 token out put gets -5 penalty
                    overflowed_token_penalty = (
                        -0.05 * (completion_len - 400) if completion_len > 400 else 0
                    )
                    # We are calculating advantage with the average reward as a
                    # baseline (GRPO-style) to reduce variance in gradient and
                    # stabilize the learning.
                    adv = r - mean_r + overflowed_token_penalty
                    completion_tokens = list(s.tokens)
                    completion_logprobs = (
                        list(s.logprobs)
                        if getattr(s, "logprobs", None) is not None
                        else None
                    )
                    datums.append(
                        _build_rl_datum(
                            prompt_tokens=prompt_tokens,
                            completion_tokens=completion_tokens,
                            completion_logprobs=completion_logprobs,
                            advantage=adv,
                        )
                    )
                all_rewards.extend(rewards)

        # Optionally incorporate KL penalty against a fixed reference model as part of reward
        # (implemented as an advantage adjustment, cookbook-style).
        kl_metrics: dict[str, float] = {}
        if kl_reference_client is not None and cfg.kl_penalty_coef > 0:
            kl_metrics = await _incorporate_kl_penalty(
                datums,
                base_sampling_client=kl_reference_client,
                kl_penalty_coef=cfg.kl_penalty_coef,
                kl_discount_factor=cfg.kl_discount_factor,
            )

        # Train step (pipeline fwdbwd + optim like docs recommend)
        adam = tinker.types.AdamParams(
            learning_rate=cfg.learning_rate,
            grad_clip_norm=cfg.grad_clip_norm,
            beta1=0.9,
            beta2=0.95,
            eps=1e-8,
        )
        # For importance sampling, we don't need to pass mask.
        # It's because we have advantage modified by KL penalty in the loss function.
        fwdbwd_future = await training_client.forward_backward_async(
            [_strip_client_only_loss_inputs(d) for d in datums],
            loss_fn="importance_sampling",
        )
        optim_future = await training_client.optim_step_async(adam)
        try:
            _ = (
                await fwdbwd_future
            )  # you can inspect loss_fn_outputs/logprobs if desired
            optim_result = await optim_future
        except Exception:
            # Ensure we don't leave an in-flight optim_step task pending (which can
            # cause "Task was destroyed but it is pending!" noise).
            try:
                _ = await optim_future
            except Exception:
                pass
            raise

        reward_stats = _compute_stats([float(r) for r in all_rewards])
        completion_len_stats = _compute_stats([float(x) for x in all_completion_lens])

        avg_reward = sum(all_rewards) / max(1, len(all_rewards))
        avg_rewards_per_step.append(float(avg_reward))
        logger.info(
            "[step %s] avg_reward=%.4f kl_metrics=%s optim_metrics=%s",
            step + 1,
            avg_reward,
            kl_metrics if kl_metrics else None,
            optim_result.metrics,
        )

        # Update run metadata + plot after each step.
        metadata["steps"].append(
            {
                "step": step + 1,
                "avg_reward": float(avg_reward),
                "num_rewards": int(len(all_rewards)),
                "num_generations_logged": int(step_generations_written),
                "reward_std": reward_stats["std"],
                "reward_min": reward_stats["min"],
                "reward_max": reward_stats["max"],
                "reward_p10": reward_stats["p10"],
                "reward_p50": reward_stats["p50"],
                "reward_p90": reward_stats["p90"],
                "completion_len_mean": completion_len_stats["mean"],
                "completion_len_std": completion_len_stats["std"],
                "completion_len_min": completion_len_stats["min"],
                "completion_len_max": completion_len_stats["max"],
                "completion_len_p10": completion_len_stats["p10"],
                "completion_len_p50": completion_len_stats["p50"],
                "completion_len_p90": completion_len_stats["p90"],
                "kl_metrics": kl_metrics if kl_metrics else None,
                "optim_metrics": optim_result.metrics,
            }
        )
        _atomic_write_json(metadata_path, metadata)
        _save_training_plots(
            metadata=metadata,
            generations_path=generations_path,
            out_dir=run_dir,
        )

        # Optional persistent checkpoint for dashboard visibility.
        if (
            cfg.checkpoint_every_steps > 0
            and (step + 1) % cfg.checkpoint_every_steps == 0
            and step + 1 < cfg.steps
        ):
            ckpt_name = f"{cfg.checkpoint_name_prefix}-step-{step + 1:04d}"
            save_future = await training_client.save_state_async(
                ckpt_name, ttl_seconds=cfg.checkpoint_ttl_seconds
            )
            save_result = await save_future
            logger.info("checkpoint saved name=%s path=%s", ckpt_name, save_result.path)

        # Refresh sampling client with latest weights
        sampling_client = (
            await training_client.save_weights_and_get_sampling_client_async()
        )

    # Always save a final persistent checkpoint (easy to find on dashboard).
    final_ckpt_name = f"{cfg.checkpoint_name_prefix}-final"
    final_save_future = await training_client.save_state_async(
        final_ckpt_name, ttl_seconds=cfg.checkpoint_ttl_seconds
    )
    final_save_result = await final_save_future
    logger.info(
        "final checkpoint saved name=%s path=%s",
        final_ckpt_name,
        final_save_result.path,
    )
    _atomic_write_json(metadata_path, metadata)

    # Collect final metrics
    final_metrics: dict[str, Any] = {
        "total_steps": cfg.steps,
        "dataset_size": len(datapoints),
        "run_dir": str(run_dir),
    }
    if avg_rewards_per_step:
        final_metrics["final_avg_reward"] = float(avg_rewards_per_step[-1])
        final_metrics["best_avg_reward"] = float(max(avg_rewards_per_step))
    step_entries = metadata.get("steps", [])
    if step_entries:
        last_step = step_entries[-1]
        final_metrics["final_reward_mean"] = last_step.get("avg_reward")
        final_metrics["final_reward_std"] = last_step.get("reward_std")

    return TrainingResult(
        checkpoint_path=final_save_result.path,
        metrics=final_metrics,
    )


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="youtube-reviews-rlvr-train",
        description="RLVR training for YouTube review generation (Tinker API).",
    )

    # Core
    p.add_argument("--base-model", default=Config.base_model)
    p.add_argument("--lora-rank", type=int, default=Config.lora_rank)
    p.add_argument("--jsonl-path", default=Config.jsonl_path)
    p.add_argument(
        "--persona-id",
        default=Config.persona_id,
        help="If set, filter dataset to this persona_id before training (single-persona training).",
    )

    # RL batching
    p.add_argument("--steps", type=int, default=Config.steps)
    p.add_argument("--groups-per-batch", type=int, default=Config.groups_per_batch)
    p.add_argument("--group-size", type=int, default=Config.group_size)
    p.add_argument("--seed", type=int, default=Config.seed)

    # Sampling
    p.add_argument("--max-tokens", type=int, default=Config.max_tokens)
    p.add_argument("--temperature", type=float, default=Config.temperature)
    p.add_argument(
        "--sampling-concurrency", type=int, default=Config.sampling_concurrency
    )

    # Training
    p.add_argument("--learning-rate", type=float, default=Config.learning_rate)
    p.add_argument("--grad-clip-norm", type=float, default=Config.grad_clip_norm)

    # KL regularization (as reward/advantages)
    p.add_argument(
        "--kl-penalty-coef",
        type=float,
        default=Config.kl_penalty_coef,
        help="If > 0, incorporate KL(current||reference) as a reward-style penalty by adjusting advantages (cookbook-style).",
    )
    p.add_argument(
        "--kl-discount-factor",
        type=float,
        default=Config.kl_discount_factor,
        help="Optional discount factor for the KL advantage adjustment (0 = no discounting).",
    )
    p.add_argument(
        "--kl-reference-model",
        default=None,
        help="Reference base model used for KL regularization (default: --base-model).",
    )
    p.add_argument(
        "--kl-reference-checkpoint-path",
        default=None,
        help="Optional reference checkpoint path for KL regularization.",
    )

    # Checkpointing
    p.add_argument(
        "--checkpoint-every-steps",
        type=int,
        default=Config.checkpoint_every_steps,
        help="Save a persistent (dashboard-visible) checkpoint every N steps. 0 = only final.",
    )
    p.add_argument(
        "--checkpoint-name-prefix",
        default=Config.checkpoint_name_prefix,
        help="Prefix for persistent checkpoint names.",
    )
    p.add_argument(
        "--checkpoint-ttl-seconds",
        type=int,
        default=None,
        help="Optional TTL seconds for checkpoints (default: never expires).",
    )

    # Reward / prompt sizing
    p.add_argument(
        "--transcript-max-chars-in-prompt",
        type=int,
        default=Config.transcript_max_chars_in_prompt,
    )

    # Embeddings
    p.add_argument("--openai-api-key-env", default=Config.openai_api_key_env)
    p.add_argument("--openai-base-url", default=None)
    p.add_argument("--openai-embedding-model", default=Config.openai_embedding_model)
    p.add_argument(
        "--embed-max-concurrent", type=int, default=Config.embed_max_concurrent
    )

    # Logging
    p.add_argument("--log-level", default=Config.log_level)
    p.add_argument(
        "--log-timestamp",
        action=argparse.BooleanOptionalAction,
        default=Config.log_timestamp,
    )
    p.add_argument(
        "--log-prompt-text",
        action=argparse.BooleanOptionalAction,
        default=Config.log_prompt_text,
    )
    p.add_argument(
        "--log-completions",
        action=argparse.BooleanOptionalAction,
        default=Config.log_completions,
    )
    p.add_argument(
        "--log-max-preview-chars", type=int, default=Config.log_max_preview_chars
    )
    p.add_argument(
        "--log-max-preview-tokens", type=int, default=Config.log_max_preview_tokens
    )
    p.add_argument(
        "--run-logs-dir",
        default=Config.run_logs_dir,
        help="Directory (relative to repo root by default) where timestamped run folders are created.",
    )

    # Dry run
    p.add_argument(
        "--dry-run",
        action=argparse.BooleanOptionalAction,
        default=Config.dry_run,
        help="If enabled, do not call Tinker/OpenAI; log would-be requests and exit.",
    )

    return p


def _config_from_args(args: argparse.Namespace) -> Config:
    return Config(
        dry_run=bool(args.dry_run),
        base_model=str(args.base_model),
        lora_rank=int(args.lora_rank),
        jsonl_path=str(args.jsonl_path),
        persona_id=(
            str(args.persona_id).strip() if args.persona_id is not None else None
        ),
        steps=int(args.steps),
        groups_per_batch=int(args.groups_per_batch),
        group_size=int(args.group_size),
        seed=int(args.seed),
        max_tokens=int(args.max_tokens),
        temperature=float(args.temperature),
        sampling_concurrency=int(args.sampling_concurrency),
        learning_rate=float(args.learning_rate),
        grad_clip_norm=float(args.grad_clip_norm),
        kl_penalty_coef=float(args.kl_penalty_coef),
        kl_discount_factor=float(args.kl_discount_factor),
        kl_reference_model=str(args.kl_reference_model)
        if args.kl_reference_model is not None
        else None,
        kl_reference_checkpoint_path=str(args.kl_reference_checkpoint_path)
        if args.kl_reference_checkpoint_path is not None
        else None,
        checkpoint_every_steps=int(args.checkpoint_every_steps),
        checkpoint_name_prefix=str(args.checkpoint_name_prefix),
        checkpoint_ttl_seconds=(
            int(args.checkpoint_ttl_seconds)
            if args.checkpoint_ttl_seconds is not None
            else None
        ),
        transcript_max_chars_in_prompt=int(args.transcript_max_chars_in_prompt),
        openai_api_key_env=str(args.openai_api_key_env),
        openai_base_url=str(args.openai_base_url) if args.openai_base_url else None,
        openai_embedding_model=str(args.openai_embedding_model),
        embed_max_concurrent=int(args.embed_max_concurrent),
        log_level=str(args.log_level),
        log_timestamp=bool(args.log_timestamp),
        log_prompt_text=bool(args.log_prompt_text),
        log_completions=bool(args.log_completions),
        log_max_preview_chars=int(args.log_max_preview_chars),
        log_max_preview_tokens=int(args.log_max_preview_tokens),
        run_logs_dir=str(args.run_logs_dir),
    )


def main(argv: list[str] | None = None) -> None:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    cfg = _config_from_args(args)
    asyncio.run(train(cfg))


if __name__ == "__main__":
    main(sys.argv[1:])

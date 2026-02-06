from __future__ import annotations

import argparse
import asyncio
import json
import logging
import random
import sys
from dataclasses import dataclass
from dataclasses import asdict as dataclass_asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import tinker

from utils.fs import find_repo_root, load_dotenv
from utils.preview import preview_tokens
from utils.tokens import to_int_list

from trains.rlvr_youtube_reviews.dataset import YouTubeReviewDatapoint, load_datapoints
from trains.rlvr_youtube_reviews.train import PersonaEnum

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TrainingResult:
    """Result from a training run."""

    checkpoint_path: str
    metrics: dict[str, Any]


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
class Config:
    # Data
    jsonl_path: str = "lab/datasets/ai_dot_engineer/dataset_train.jsonl"
    persona_id: str | None = PersonaEnum.JUNIOR_ENGINEER_SIDE_PROJECTS.value

    # Model
    base_model: str = "meta-llama/Llama-3.1-8B-Instruct"
    lora_rank: int = 32

    # Prompt
    transcript_max_chars_in_prompt: int = 20_000

    # Training
    batch_size: int = 4
    epochs: int = 1
    learning_rate: float = 1e-3
    grad_clip_norm: float = 0.0
    seed: int = 1
    # Optional hard cap on total tokens in the rendered chat sequence.
    # Prefer leaving this as None and controlling prompt size via transcript truncation.
    max_length_tokens: int | None = None

    # Checkpointing + logs
    run_logs_dir: str = "lab/trains/sft_youtube_reviews/logs"
    checkpoint_every_steps: int = 10  # 0 disables mid-run checkpoints
    checkpoint_name_prefix: str = "sft_youtube_reviews"
    checkpoint_ttl_seconds: int | None = None

    # Resume training
    resume_weight_path: str | None = None  # loads weights only (optimizer resets)
    resume_state_path: str | None = (
        None  # loads weights + optimizer state (true continuation)
    )

    # Logging
    log_level: str = "INFO"
    log_timestamp: bool = False
    log_max_preview_tokens: int = 60

    # Plots (saved into run dir)
    plot_every_steps: int = (
        10  # 0 disables plots; if 0 we default to checkpoint_every_steps
    )
    plot_max_points: int = 5000  # cap points to keep plotting fast


def _configure_logging(*, level: str, timestamp: bool) -> None:
    fmt = "%(levelname)s %(name)s: %(message)s"
    if timestamp:
        fmt = "%(asctime)s " + fmt
    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO), format=fmt)


def _atomic_write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            try:
                rows.append(json.loads(s))
            except Exception:
                continue
    return rows


def _safe_float(x: Any) -> float | None:
    try:
        v = float(x)
    except Exception:
        return None
    if not np.isfinite(v):
        return None
    return float(v)


def _maybe_write_training_plots(
    *,
    run_dir: Path,
    metrics_path: Path,
    step: int,
    total_steps: int,
    max_points: int,
) -> Path | None:
    """
    Save a PNG plot (loss curves) into the run directory.
    Returns the saved plot path when successful.
    """
    try:
        # Ensure headless-friendly backend.
        import matplotlib

        matplotlib.use("Agg", force=True)
        import matplotlib.pyplot as plt
    except Exception as e:
        logger.warning("plotting unavailable (matplotlib import failed): %s", e)
        return None

    rows = _read_jsonl(metrics_path)
    if not rows:
        return None

    xs: list[int] = []
    loss: list[float] = []
    raw_loss: list[float] = []
    num_loss_tokens: list[float] = []
    for r in rows:
        s = r.get("step")
        if s is None:
            continue
        try:
            si = int(s)
        except Exception:
            continue

        lv = _safe_float(r.get("loss"))
        rlv = _safe_float(r.get("raw_loss"))
        nlt = _safe_float(r.get("num_loss_tokens"))
        if lv is None and rlv is None and nlt is None:
            continue
        xs.append(si)
        loss.append(lv if lv is not None else float("nan"))
        raw_loss.append(rlv if rlv is not None else float("nan"))
        num_loss_tokens.append(nlt if nlt is not None else float("nan"))

    if not xs:
        return None

    if max_points > 0 and len(xs) > max_points:
        xs = xs[-max_points:]
        loss = loss[-max_points:]
        raw_loss = raw_loss[-max_points:]
        num_loss_tokens = num_loss_tokens[-max_points:]

    plots_dir = run_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)
    out_path = plots_dir / f"training_curves_step_{step:06d}.png"
    latest_path = plots_dir / "training_curves_latest.png"

    fig, axes = plt.subplots(nrows=3, ncols=1, figsize=(10, 10), sharex=True)
    fig.suptitle(f"SFT training curves (step {step}/{total_steps})")

    axes[0].plot(xs, loss, label="loss (masked sum)")
    axes[0].set_ylabel("loss")
    axes[0].grid(True, alpha=0.3)
    axes[0].legend(loc="best")

    axes[1].plot(xs, raw_loss, label="raw_loss", color="tab:orange")
    axes[1].set_ylabel("raw_loss")
    axes[1].grid(True, alpha=0.3)
    axes[1].legend(loc="best")

    axes[2].plot(xs, num_loss_tokens, label="num_loss_tokens", color="tab:green")
    axes[2].set_ylabel("loss tokens")
    axes[2].set_xlabel("step")
    axes[2].grid(True, alpha=0.3)
    axes[2].legend(loc="best")

    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)

    try:
        latest_path.write_bytes(out_path.read_bytes())
    except Exception:
        # Best-effort: keep step-specific plot even if "latest" fails.
        pass

    return out_path


def _truncate_transcript_for_prompt(transcript: str, *, max_chars: int) -> str:
    if max_chars <= 0:
        return transcript
    s = transcript.replace("\r\n", "\n").replace("\r", "\n")
    if len(s) <= max_chars:
        return s
    return s[:max_chars] + "...[TRUNCATED]..."


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
    dp: YouTubeReviewDatapoint,
    *,
    transcript_max_chars_in_prompt: int,
    assistant_text: str | None,
) -> list[dict[str, str]]:
    system, user = _system_user_for_dp(
        dp, transcript_max_chars_in_prompt=transcript_max_chars_in_prompt
    )
    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": user})
    if assistant_text is not None:
        messages.append({"role": "assistant", "content": assistant_text})
    return messages


def _try_encode_llama_instruct_chat(
    *,
    tokenizer: Any,
    messages: list[dict[str, str]],
    add_generation_prompt: bool,
) -> list[int] | None:
    """
    Best-effort manual chat formatting for Llama-family instruct models.

    This is only used as a fallback if `apply_chat_template` fails.
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
        parts.append(f"{start_header}{role}{end_header}\n\n{content}{eot}\n")

    if add_generation_prompt:
        parts.append(f"{start_header}assistant{end_header}\n\n")

    text = "".join(parts)
    try:
        return to_int_list(tokenizer.encode(text, add_special_tokens=False))
    except Exception:
        return None


def _encode_chat_tokens(
    *,
    tokenizer: Any,
    model_name: str,
    messages: list[dict[str, str]],
    add_generation_prompt: bool,
) -> list[int]:
    """
    Encode a chat message list into tokens in a model-compatible way.
    """
    if hasattr(tokenizer, "apply_chat_template"):
        try:
            tokens = tokenizer.apply_chat_template(  # type: ignore[attr-defined]
                messages,
                tokenize=True,
                add_generation_prompt=add_generation_prompt,
            )
            return to_int_list(tokens)
        except Exception as e:
            logger.error("apply_chat_template failed: %s", e)

    # Fallback: manual Llama formatting when special tokens are present.
    if "llama" in (model_name or "").lower():
        maybe_tokens = _try_encode_llama_instruct_chat(
            tokenizer=tokenizer,
            messages=messages,
            add_generation_prompt=add_generation_prompt,
        )
        if maybe_tokens is not None:
            return maybe_tokens

    raise RuntimeError(
        "Tokenizer does not support `apply_chat_template` and no fallback succeeded. "
        "Pick a chat model with HF templates (recommended), or add a custom formatter."
    )


def build_prompt_tokens(
    dp: YouTubeReviewDatapoint,
    *,
    tokenizer: Any,
    model_name: str,
    transcript_max_chars_in_prompt: int,
) -> list[int]:
    """
    Prompt tokens should include the assistant role header (generation prompt).
    """
    messages = _messages_for_dp(
        dp,
        transcript_max_chars_in_prompt=transcript_max_chars_in_prompt,
        assistant_text=None,
    )
    return _encode_chat_tokens(
        tokenizer=tokenizer,
        model_name=model_name,
        messages=messages,
        add_generation_prompt=True,
    )


def build_full_tokens_for_target(
    dp: YouTubeReviewDatapoint,
    *,
    tokenizer: Any,
    model_name: str,
    transcript_max_chars_in_prompt: int,
    target_text: str,
) -> list[int]:
    """
    Full chat tokens including the assistant target (and any end-of-turn token the template adds).
    """
    messages = _messages_for_dp(
        dp,
        transcript_max_chars_in_prompt=transcript_max_chars_in_prompt,
        assistant_text=target_text,
    )
    return _encode_chat_tokens(
        tokenizer=tokenizer,
        model_name=model_name,
        messages=messages,
        add_generation_prompt=False,
    )


def _build_sft_datum(
    *, prompt_tokens: list[int], completion_tokens: list[int]
) -> tinker.types.Datum:
    """
    Build a cross-entropy supervised datum with a loss mask that only trains on completion tokens.

    Indexing detail (same as RLVR):
    - full = prompt + completion
    - model_input is full[:-1]
    - target_tokens is full[1:]
    - the first completion token sits at target index len(prompt)-1
    """
    full = prompt_tokens + completion_tokens
    if len(full) < 2:
        return tinker.types.Datum(
            model_input=tinker.types.ModelInput.from_ints([]),
            loss_fn_inputs={
                "target_tokens": tinker.TensorData(data=[], dtype="int64", shape=[0]),
                "weights": tinker.TensorData(data=[], dtype="float32", shape=[0]),
            },
        )

    model_input = tinker.types.ModelInput.from_ints(full[:-1])
    target_tokens_list = [int(x) for x in full[1:]]
    weights = np.zeros(shape=(len(target_tokens_list),), dtype=np.float32)

    start = max(0, len(prompt_tokens) - 1)
    end = min(len(target_tokens_list), start + len(completion_tokens))
    if end > start:
        weights[start:end] = 1.0

    return tinker.types.Datum(
        model_input=model_input,
        loss_fn_inputs={
            "target_tokens": tinker.TensorData(
                data=target_tokens_list,
                dtype="int64",
                shape=[len(target_tokens_list)],
            ),
            "weights": tinker.TensorData(
                data=weights.tolist(),
                dtype="float32",
                shape=[len(target_tokens_list)],
            ),
        },
    )


def _masked_cross_entropy_loss_sum(
    *,
    logprobs: tinker.TensorData,
    weights: tinker.TensorData,
) -> float:
    """
    Compute \u2211_t (-logprob_t * weight_t) over tokens with weight>0.

    Masking (instead of multiplying) avoids 0*NaN -> NaN if the backend emits NaNs
    for masked-out tokens.
    """
    lp = [float(x) for x in logprobs.data]
    w = [float(x) for x in weights.data]
    total = 0.0
    for lpi, wi in zip(lp, w, strict=True):
        if wi <= 0.0:
            continue
        total += (-lpi) * wi
    return float(total)


def build_sft_datum_for_dp(
    dp: YouTubeReviewDatapoint,
    *,
    tokenizer: Any,
    model_name: str,
    transcript_max_chars_in_prompt: int,
    max_length_tokens: int | None,
) -> tinker.types.Datum:
    prompt_tokens = build_prompt_tokens(
        dp,
        tokenizer=tokenizer,
        model_name=model_name,
        transcript_max_chars_in_prompt=transcript_max_chars_in_prompt,
    )

    full_tokens = build_full_tokens_for_target(
        dp,
        tokenizer=tokenizer,
        model_name=model_name,
        transcript_max_chars_in_prompt=transcript_max_chars_in_prompt,
        target_text=dp.synthetic_user_feedback.strip(),
    )

    if (
        len(full_tokens) < len(prompt_tokens)
        or full_tokens[: len(prompt_tokens)] != prompt_tokens
    ):
        raise RuntimeError(
            "Chat template prefix mismatch between prompt tokens and full target tokens. "
            "This usually indicates inconsistent chat templating or a missing generation header."
        )

    # Completion includes end-of-turn tokens if the template adds them.
    completion_tokens = full_tokens[len(prompt_tokens) :]

    # Optional token-length cap (prefer using transcript truncation instead).
    if max_length_tokens is not None and max_length_tokens > 0:
        full = prompt_tokens + completion_tokens
        if len(full) > max_length_tokens:
            # Keep the completion intact when possible, trimming from the start of the prompt.
            overflow = len(full) - max_length_tokens
            if overflow < len(prompt_tokens):
                prompt_tokens = prompt_tokens[overflow:]
            else:
                # Degenerate: prompt itself exceeds max_length; fall back to hard truncation.
                prompt_tokens = prompt_tokens[-max_length_tokens:]
                completion_tokens = []

    return _build_sft_datum(
        prompt_tokens=prompt_tokens, completion_tokens=completion_tokens
    )


async def train(
    cfg: Config,
    *,
    datapoints_override: list | None = None,
) -> TrainingResult:
    """
    Run SFT training.

    Args:
        cfg: Training configuration.
        datapoints_override: If provided, use these datapoints instead of
            loading from the JSONL file. Used by the server to pass DB-sourced data.

    Returns:
        TrainingResult with checkpoint_path and metrics.
    """
    repo_root = find_repo_root(Path(__file__).resolve().parent)
    _configure_logging(level=cfg.log_level, timestamp=cfg.log_timestamp)

    run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_dir = (repo_root / cfg.run_logs_dir / run_id).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)

    metadata_path = run_dir / "metadata.json"
    metrics_path = run_dir / "metrics.jsonl"

    if cfg.resume_weight_path and cfg.resume_state_path:
        raise ValueError(
            "Only one of resume_weight_path or resume_state_path may be set."
        )

    _atomic_write_json(
        metadata_path,
        {
            "run_id": run_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "run_dir": str(run_dir),
            "script": str(Path(__file__).resolve()),
            "config": dataclass_asdict(cfg),
            "init_from_checkpoint": (
                {
                    "path": cfg.resume_state_path,
                    "with_optimizer": True,
                }
                if cfg.resume_state_path
                else (
                    {
                        "path": cfg.resume_weight_path,
                        "with_optimizer": False,
                    }
                    if cfg.resume_weight_path
                    else None
                )
            ),
        },
    )

    if datapoints_override is not None:
        datapoints = datapoints_override
        logger.info("using %d datapoints from override", len(datapoints))
    else:
        jsonl_path = str((repo_root / cfg.jsonl_path).resolve())
        all_datapoints = load_datapoints(jsonl_path)
        datapoints = all_datapoints
        if cfg.persona_id is None:
            logger.warning("no persona filter applied")
        else:
            pid = str(cfg.persona_id).strip()
            datapoints = [dp for dp in all_datapoints if dp.persona_id == pid]
            logger.info(
                "persona filter enabled persona_id=%s kept=%d/%d",
                pid,
                len(datapoints),
                len(all_datapoints),
            )

    if not datapoints:
        raise RuntimeError(f"No datapoints loaded from {jsonl_path}")

    rng = random.Random(cfg.seed)
    rng.shuffle(datapoints)

    service_client = tinker.ServiceClient()
    if cfg.resume_state_path:
        training_client = (
            await service_client.create_training_client_from_state_with_optimizer_async(
                cfg.resume_state_path
            )
        )
        logger.info(
            "resumed from checkpoint (with optimizer) path=%s", cfg.resume_state_path
        )
    elif cfg.resume_weight_path:
        training_client = await service_client.create_training_client_from_state_async(
            cfg.resume_weight_path
        )
        logger.info("loaded weights from checkpoint path=%s", cfg.resume_weight_path)
    else:
        training_client = await service_client.create_lora_training_client_async(
            base_model=cfg.base_model, rank=cfg.lora_rank
        )
    tokenizer = training_client.get_tokenizer()
    model_name_for_chat = cfg.base_model
    try:
        info = training_client.get_info()
        info_model_name = getattr(getattr(info, "model_data", None), "model_name", None)
        if isinstance(info_model_name, str) and info_model_name.strip():
            model_name_for_chat = info_model_name.strip()
            if model_name_for_chat != cfg.base_model:
                logger.warning(
                    "base_model differs from checkpoint model_name (using checkpoint for chat templating) "
                    "base_model=%s checkpoint_model_name=%s",
                    cfg.base_model,
                    model_name_for_chat,
                )
    except Exception:
        pass
    logger.info(
        "training init base_model=%s lora_rank=%s tokenizer=%s",
        cfg.base_model,
        cfg.lora_rank,
        type(tokenizer).__name__,
    )

    steps_per_epoch = max(1, (len(datapoints) + cfg.batch_size - 1) // cfg.batch_size)
    total_steps = steps_per_epoch * max(1, cfg.epochs)
    logger.info(
        "dataset size=%d batch_size=%d epochs=%d total_steps=%d",
        len(datapoints),
        cfg.batch_size,
        cfg.epochs,
        total_steps,
    )

    plot_every = int(cfg.plot_every_steps)
    if plot_every <= 0:
        plot_every = int(cfg.checkpoint_every_steps)
    if plot_every > 0:
        logger.info("plotting enabled every_steps=%d", plot_every)
    else:
        logger.info("plotting disabled")

    for step in range(total_steps):
        start = (step * cfg.batch_size) % len(datapoints)
        batch = datapoints[start : start + cfg.batch_size]
        if len(batch) < cfg.batch_size:
            batch = batch + datapoints[0 : cfg.batch_size - len(batch)]

        # Build supervised datums.
        datums: list[tinker.types.Datum] = []
        for dp in batch:
            if not dp.synthetic_user_feedback.strip():
                continue
            datums.append(
                build_sft_datum_for_dp(
                    dp,
                    tokenizer=tokenizer,
                    model_name=model_name_for_chat,
                    transcript_max_chars_in_prompt=cfg.transcript_max_chars_in_prompt,
                    max_length_tokens=cfg.max_length_tokens,
                )
            )

        if not datums:
            logger.warning("empty batch at step=%d (no targets)", step)
            continue

        # Useful debugging: NaN loss is commonly caused by sum(weights)==0.
        num_loss_tokens = 0.0
        for d in datums:
            w = d.loss_fn_inputs.get("weights")
            if isinstance(w, tinker.TensorData):
                num_loss_tokens += float(sum(float(x) for x in w.data))

        # Pipeline fwdbwd + optim (recommended pattern).
        adam = tinker.types.AdamParams(
            learning_rate=cfg.learning_rate,
            grad_clip_norm=cfg.grad_clip_norm,
            beta1=0.9,
            beta2=0.95,
            eps=1e-8,
        )
        fwdbwd_future = await training_client.forward_backward_async(
            datums, loss_fn="cross_entropy"
        )
        optim_future = await training_client.optim_step_async(adam)

        fwdbwd_result = await fwdbwd_future
        optim_result = await optim_future

        # NOTE: some backends may emit NaNs for masked-out (weight=0) tokens in `logprobs`.
        # If they compute loss as (-logprobs * weights).sum(), that becomes NaN due to 0*NaN.
        # We compute a robust masked sum for logging.
        raw_loss = float(getattr(fwdbwd_result, "loss", float("nan")))
        masked_loss_sum = float("nan")
        try:
            loss_fn_outputs = getattr(fwdbwd_result, "loss_fn_outputs", None)
            if loss_fn_outputs is not None:
                per_seq_logprobs = [x["logprobs"] for x in loss_fn_outputs]
                per_seq_weights = [d.loss_fn_inputs["weights"] for d in datums]
                masked_loss_sum = sum(
                    _masked_cross_entropy_loss_sum(logprobs=lp, weights=w)
                    for lp, w in zip(per_seq_logprobs, per_seq_weights, strict=True)
                )
        except Exception:
            masked_loss_sum = float("nan")

        metrics_row: dict[str, Any] = {
            "step": step + 1,
            "loss": masked_loss_sum,
            "raw_loss": raw_loss,
            "num_sequences": int(len(datums)),
            "num_loss_tokens": float(num_loss_tokens),
            "learning_rate": float(cfg.learning_rate),
        }
        if getattr(optim_result, "metrics", None):
            # include any service-side optimizer metrics
            metrics_row.update(
                {f"optim/{k}": v for k, v in optim_result.metrics.items()}
            )

        # Log a tiny preview once in a while to sanity check tokenization boundaries.
        if (step == 0) or ((step + 1) % max(1, cfg.checkpoint_every_steps) == 0):
            try:
                ints = datums[0].model_input.to_ints()
            except Exception:
                ints = []
            metrics_row["preview/model_input_tokens"] = preview_tokens(
                list(ints), max_tokens=cfg.log_max_preview_tokens
            )

        _append_jsonl(metrics_path, metrics_row)
        logger.info(
            "[step %d/%d] loss_sum=%.6f raw_loss=%.6f sequences=%d loss_tokens=%.0f",
            step + 1,
            total_steps,
            float(metrics_row["loss"]),
            float(metrics_row["raw_loss"]),
            len(datums),
            float(metrics_row["num_loss_tokens"]),
        )

        if plot_every > 0 and (
            (step == 0) or ((step + 1) % plot_every == 0) or (step + 1 == total_steps)
        ):
            plot_path = _maybe_write_training_plots(
                run_dir=run_dir,
                metrics_path=metrics_path,
                step=step + 1,
                total_steps=total_steps,
                max_points=int(cfg.plot_max_points),
            )
            if plot_path is not None:
                logger.info("saved plot path=%s", plot_path)

        if (
            cfg.checkpoint_every_steps > 0
            and (step + 1) % cfg.checkpoint_every_steps == 0
        ):
            ckpt_name = f"{cfg.checkpoint_name_prefix}-step-{step + 1:06d}"
            save_future = await training_client.save_state_async(
                ckpt_name, ttl_seconds=cfg.checkpoint_ttl_seconds
            )
            save_result = await save_future
            logger.info("checkpoint saved name=%s path=%s", ckpt_name, save_result.path)

    final_ckpt_name = f"{cfg.checkpoint_name_prefix}-final"
    final_future = await training_client.save_state_async(
        final_ckpt_name, ttl_seconds=cfg.checkpoint_ttl_seconds
    )
    final_result = await final_future
    logger.info(
        "final checkpoint saved name=%s path=%s", final_ckpt_name, final_result.path
    )

    if plot_every > 0:
        plot_path = _maybe_write_training_plots(
            run_dir=run_dir,
            metrics_path=metrics_path,
            step=total_steps,
            total_steps=total_steps,
            max_points=int(cfg.plot_max_points),
        )
        if plot_path is not None:
            logger.info("saved final plot path=%s", plot_path)

    # Collect final metrics from the last metrics row
    final_metrics: dict[str, Any] = {}
    last_rows = _read_jsonl(metrics_path)
    if last_rows:
        last = last_rows[-1]
        final_metrics = {
            "final_loss": last.get("loss"),
            "final_raw_loss": last.get("raw_loss"),
            "total_steps": total_steps,
            "dataset_size": len(datapoints),
            "run_dir": str(run_dir),
        }

    return TrainingResult(
        checkpoint_path=final_result.path,
        metrics=final_metrics,
    )


def _parse_args(argv: list[str]) -> Config:
    p = argparse.ArgumentParser(
        description="SFT training for YouTube review dataset (synthetic_user_feedback as target)."
    )
    p.add_argument("--jsonl-path", default=Config.jsonl_path)
    p.add_argument("--persona-id", default=Config.persona_id)

    p.add_argument("--base-model", default=Config.base_model)
    p.add_argument("--lora-rank", type=int, default=Config.lora_rank)
    p.add_argument(
        "--resume-state-path",
        default=Config.resume_state_path,
        help="Tinker checkpoint path to resume from (loads weights + optimizer state).",
    )
    p.add_argument(
        "--resume-weight-path",
        default=Config.resume_weight_path,
        help="Tinker checkpoint path to initialize from (loads weights only; fresh optimizer).",
    )

    p.add_argument(
        "--transcript-max-chars-in-prompt",
        type=int,
        default=Config.transcript_max_chars_in_prompt,
    )
    p.add_argument("--max-length-tokens", type=int, default=Config.max_length_tokens)

    p.add_argument("--batch-size", type=int, default=Config.batch_size)
    p.add_argument("--epochs", type=int, default=Config.epochs)
    p.add_argument("--learning-rate", type=float, default=Config.learning_rate)
    p.add_argument("--grad-clip-norm", type=float, default=Config.grad_clip_norm)
    p.add_argument("--seed", type=int, default=Config.seed)

    p.add_argument("--run-logs-dir", default=Config.run_logs_dir)
    p.add_argument(
        "--checkpoint-every-steps", type=int, default=Config.checkpoint_every_steps
    )
    p.add_argument("--checkpoint-name-prefix", default=Config.checkpoint_name_prefix)
    p.add_argument(
        "--checkpoint-ttl-seconds", type=int, default=Config.checkpoint_ttl_seconds
    )

    p.add_argument("--log-level", default=Config.log_level)
    p.add_argument("--log-timestamp", action="store_true")
    p.add_argument(
        "--plot-every-steps",
        type=int,
        default=Config.plot_every_steps,
        help="Save matplotlib training curve PNGs every N steps (0 uses checkpoint_every_steps; <0 disables).",
    )
    p.add_argument(
        "--plot-max-points",
        type=int,
        default=Config.plot_max_points,
        help="Cap number of points drawn in plots (keeps plotting fast).",
    )

    args = p.parse_args(argv)

    return Config(
        jsonl_path=str(args.jsonl_path),
        persona_id=(str(args.persona_id).strip() if args.persona_id else None),
        base_model=str(args.base_model),
        lora_rank=int(args.lora_rank),
        resume_state_path=(
            str(args.resume_state_path).strip() if args.resume_state_path else None
        ),
        resume_weight_path=str(args.resume_weight_path).strip()
        if args.resume_weight_path
        else None,
        transcript_max_chars_in_prompt=int(args.transcript_max_chars_in_prompt),
        max_length_tokens=(
            int(args.max_length_tokens) if args.max_length_tokens is not None else None
        ),
        batch_size=int(args.batch_size),
        epochs=int(args.epochs),
        learning_rate=float(args.learning_rate),
        grad_clip_norm=float(args.grad_clip_norm),
        seed=int(args.seed),
        run_logs_dir=str(args.run_logs_dir),
        checkpoint_every_steps=int(args.checkpoint_every_steps),
        checkpoint_name_prefix=str(args.checkpoint_name_prefix),
        checkpoint_ttl_seconds=(
            int(args.checkpoint_ttl_seconds)
            if args.checkpoint_ttl_seconds is not None
            else None
        ),
        log_level=str(args.log_level),
        log_timestamp=bool(args.log_timestamp),
        plot_every_steps=int(args.plot_every_steps),
        plot_max_points=int(args.plot_max_points),
    )


def main(argv: list[str] | None = None) -> int:
    repo_root = find_repo_root(Path(__file__).resolve().parent)
    dotenv_path = repo_root / ".env"
    load_dotenv(dotenv_path)

    cfg = _parse_args(sys.argv[1:] if argv is None else argv)
    asyncio.run(train(cfg))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import json
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Sequence

from tinker import ServiceClient, types

from .fs import find_repo_root
from .tokens import to_int_list

# Default location for the YouTube reviews dataset used in notebooks/scripts.
DEFAULT_DATASET_SUBDIR = Path("lab") / "datasets" / "ai_dot_engineer"

# Prompts are kept here so notebooks and scripts stay in sync.
PERSONA_FEEDBACK_SYSTEM_PROMPT_TEMPLATE = """
Generate a review for the provided video.
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
class RepoPaths:
    repo_root: Path
    dataset_root: Path
    transcripts_dir: Path


@dataclass(frozen=True)
class VideoSample:
    video_id: str
    title: str
    summary: str
    transcript: str
    persona_id: str
    gold_feedback: str


def collect_repo_paths(start: Path | None = None) -> RepoPaths:
    """
    Resolve repository-scoped paths used by checkpoint comparison workflows.
    """
    root = find_repo_root(start or Path.cwd())
    dataset_root = root / DEFAULT_DATASET_SUBDIR
    transcripts_dir = dataset_root / "transcripts"
    return RepoPaths(repo_root=root, dataset_root=dataset_root, transcripts_dir=transcripts_dir)


# --- Tinker helpers ------------------------------------------------------- #


def list_recent_training_runs(rest_client, *, limit: int = 20) -> list[types.TrainingRun]:
    resp = rest_client.list_training_runs(limit=limit).result()
    return list(resp.training_runs)


def list_checkpoints_for_run(rest_client, training_run_id: str) -> list[types.Checkpoint]:
    resp = rest_client.list_checkpoints(training_run_id).result()
    return sorted(resp.checkpoints, key=lambda c: c.time)


def pick_checkpoints_spread(
    checkpoints: Sequence[types.Checkpoint], *, k: int, prefer_training: bool = True
) -> list[types.Checkpoint]:
    """
    Choose up to k checkpoints spread across time, preferring training checkpoints.
    """
    if prefer_training:
        checkpoints = [c for c in checkpoints if c.checkpoint_type == "training"] or list(checkpoints)
    if not checkpoints:
        return []
    if k <= 1:
        return [checkpoints[-1]]
    idxs = sorted({int(round(i * (len(checkpoints) - 1) / (k - 1))) for i in range(k)})
    return [checkpoints[i] for i in idxs]


def _safe_checkpoint_name(s: str, *, max_len: int = 80) -> str:
    s = s.replace("/", "_").replace(":", "-")
    s = "".join(ch for ch in s if ch.isalnum() or ch in {"_", "-", "."})
    return s[:max_len] if len(s) > max_len else s


def resolve_sampler_model_paths(
    service_client: ServiceClient,
    checkpoints: Sequence[types.Checkpoint],
    *,
    auto_materialize: bool = True,
) -> list[str]:
    """
    Ensure we have sampler-capable model paths for sampling checkpoints.
    """
    out: list[str] = []
    for ckpt in checkpoints:
        if "/sampler_weights/" in ckpt.tinker_path:
            out.append(ckpt.tinker_path)
            continue
        if not auto_materialize:
            raise RuntimeError(
                "This run only has training checkpoints. "
                "Set auto_materialize=True or select sampler checkpoints."
            )
        tc = service_client.create_training_client_from_state(ckpt.tinker_path)
        name = _safe_checkpoint_name(f"sampler__{ckpt.checkpoint_id}")
        save_res = tc.save_weights_for_sampler(name=name).result()
        out.append(save_res.path)
    return out


# --- Dataset helpers ------------------------------------------------------ #


def dataset_jsonl_path(dataset_root: Path, split: str) -> Path:
    split = split.lower()
    if split not in {"train", "val"}:
        raise ValueError(f"Invalid split {split!r}; expected 'train' or 'val'")
    return dataset_root / f"dataset_{split}.jsonl"


def list_unique_video_ids_from_jsonl(jsonl_path: Path, *, limit: int | None = None) -> list[str]:
    if not jsonl_path.exists():
        return []
    out: list[str] = []
    seen: set[str] = set()
    with jsonl_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if r.get("kind") != "datapoint":
                continue
            vid = str((r.get("video") or {}).get("video_id") or "")
            if not vid or vid in seen:
                continue
            seen.add(vid)
            out.append(vid)
            if limit is not None and len(out) >= limit:
                break
    return out


def pick_random_unique_video_ids(jsonl_path: Path, *, k: int, seed: int) -> list[str]:
    all_ids = list_unique_video_ids_from_jsonl(jsonl_path)
    rng = random.Random(seed)
    if k >= len(all_ids):
        return all_ids
    return rng.sample(all_ids, k)


def _resolve_dataset_path(dataset_root: Path, path_str: str) -> Path:
    p = Path(path_str)
    return p if p.is_absolute() else (dataset_root / p)


def load_samples_for_video_ids(
    *,
    dataset_root: Path,
    transcripts_dir: Path,
    video_ids: Sequence[str],
    split: str,
) -> tuple[list[VideoSample], list[str]]:
    """
    Load one representative datapoint per video_id from the dataset jsonl split.
    Returns (samples, missing_ids).
    """
    wanted = set(video_ids)
    found: dict[str, VideoSample] = {}

    jsonl_path = dataset_jsonl_path(dataset_root, split)
    if not jsonl_path.exists():
        raise FileNotFoundError(jsonl_path)

    with jsonl_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if r.get("kind") != "datapoint":
                continue

            video = r.get("video") or {}
            inp = r.get("input") or {}
            persona = r.get("persona") or {}
            target = r.get("target") or {}

            vid = str(video.get("video_id") or "")
            if vid not in wanted or vid in found:
                continue

            title = str(video.get("title") or "")
            summary = str(inp.get("summary") or "")
            persona_id = str(persona.get("persona_id") or "")
            gold_feedback = str(target.get("synthetic_user_feedback") or "")

            transcript = ""
            ref = inp.get("transcript_ref")
            if isinstance(ref, dict) and isinstance(ref.get("path"), str):
                p = _resolve_dataset_path(dataset_root, ref["path"])
                transcript = p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""
            else:
                p = transcripts_dir / f"{vid}.txt"
                transcript = p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""

            found[vid] = VideoSample(
                video_id=vid,
                title=title,
                summary=summary,
                transcript=transcript.strip(),
                persona_id=persona_id,
                gold_feedback=gold_feedback.strip(),
            )

            if len(found) == len(wanted):
                break

    missing = [vid for vid in video_ids if vid not in found]
    samples = [found[vid] for vid in video_ids if vid in found]
    return samples, missing


# --- Prompt + sampling helpers ------------------------------------------- #


def truncate_chars(s: str, max_chars: int) -> str:
    if len(s) <= max_chars:
        return s
    return s[:max_chars] + "\n\n[TRUNCATED]"


def build_user_prompt(sample: VideoSample, *, transcript_max_chars: int, template: str) -> str:
    return template.format(
        title=sample.title,
        summary=sample.summary.strip(),
        transcript=truncate_chars(sample.transcript, transcript_max_chars),
    ).strip()


def build_prompt_tokens(*, tokenizer, system: str, user: str) -> list[int]:
    if hasattr(tokenizer, "apply_chat_template"):
        try:
            tokens = tokenizer.apply_chat_template(
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                tokenize=True,
                add_generation_prompt=True,
            )
            return to_int_list(tokens)
        except Exception:
            # Fall back to manual prompt formatting.
            pass
    fallback = f"System:\n{system}\n\nUser:\n{user}\n"
    return to_int_list(tokenizer.encode(fallback, add_special_tokens=True))


def sample_checkpoints_for_videos(
    *,
    service_client: ServiceClient,
    model_paths: Sequence[str],
    samples: Sequence[VideoSample],
    sampling_params: types.SamplingParams,
    system_prompt: str,
    user_prompt_template: str,
    transcript_max_chars: int,
    max_concurrency: int | None = None,
) -> dict[tuple[str, str], str]:
    """
    Sample outputs for each (video_id, model_path) pair.
    Returns a dict keyed by (video_id, model_path) -> text.
    """
    if max_concurrency is None:
        max_concurrency = min(6, len(model_paths))

    user_prompts = {
        s.video_id: build_user_prompt(
            s,
            transcript_max_chars=transcript_max_chars,
            template=user_prompt_template,
        )
        for s in samples
    }

    def _sample_all_for_model(model_path: str) -> tuple[str, dict[str, str]]:
        sampler = service_client.create_sampling_client(model_path=model_path)
        tokenizer = sampler.get_tokenizer()
        out_by_video: dict[str, str] = {}
        for sample in samples:
            tokens = build_prompt_tokens(
                tokenizer=tokenizer,
                system=system_prompt,
                user=user_prompts[sample.video_id],
            )
            prompt = types.ModelInput.from_ints(tokens)
            res = sampler.sample(prompt=prompt, num_samples=1, sampling_params=sampling_params).result()
            seq = res.sequences[0]
            out_by_video[sample.video_id] = tokenizer.decode(seq.tokens)
        return (model_path, out_by_video)

    results: dict[tuple[str, str], str] = {}
    with ThreadPoolExecutor(max_workers=max(1, max_concurrency)) as ex:
        futures = [ex.submit(_sample_all_for_model, mp) for mp in model_paths]
        for fut in as_completed(futures):
            model_path, out_by_video = fut.result()
            for video_id, text in out_by_video.items():
                results[(video_id, model_path)] = text
    return results


# --- High-level workflows ------------------------------------------------ #


@dataclass(frozen=True)
class ComparisonArtifacts:
    """
    All data needed to render / inspect a checkpoint comparison run.
    """

    paths: RepoPaths
    training_run: types.TrainingRun
    checkpoints: list[types.Checkpoint]
    model_paths: list[str]
    samples: list[VideoSample]
    results: dict[tuple[str, str], str]
    split: str


def select_training_run(
    rest_client,
    *,
    training_run_id: str | None = None,
    run_index: int = 0,
    limit: int = 20,
) -> types.TrainingRun:
    """
    Pick a training run either by id (preferred) or by index in the recent list.
    """
    runs = list_recent_training_runs(rest_client, limit=limit)
    if not runs:
        raise RuntimeError("No training runs found. Authenticate and retry.")

    if training_run_id is not None:
        for r in runs:
            if r.training_run_id == training_run_id:
                return r
        raise ValueError(f"Training run id not found in recent runs: {training_run_id!r}")

    if run_index < 0 or run_index >= len(runs):
        raise IndexError(f"run_index out of range: {run_index} (runs={len(runs)})")

    return runs[run_index]


def select_video_ids(
    jsonl_path: Path,
    *,
    split: str,
    num_videos: int,
    seed: int,
    selection: Literal["auto", "first_n", "random"] = "auto",
) -> list[str]:
    """
    Choose which videos to compare from a dataset split jsonl.
    """
    split = split.lower()
    if selection == "auto":
        selection = "random" if split == "train" else "first_n"

    if selection == "random":
        return pick_random_unique_video_ids(jsonl_path, k=num_videos, seed=seed)
    if selection == "first_n":
        return list_unique_video_ids_from_jsonl(jsonl_path, limit=num_videos)
    raise ValueError(f"Invalid selection {selection!r}")


def run_checkpoint_comparison(
    *,
    service_client: ServiceClient | None = None,
    start_path: Path | None = None,
    dataset_split: str = "val",
    num_videos: int = 10,
    video_selection: Literal["auto", "first_n", "random"] = "auto",
    random_seed: int = 42,
    training_run_id: str | None = None,
    run_index: int = 0,
    num_checkpoints: int = 1,
    prefer_training_checkpoints: bool = True,
    auto_materialize_sampler: bool = True,
    sampling_params: types.SamplingParams | None = None,
    system_prompt: str = PERSONA_FEEDBACK_SYSTEM_PROMPT_TEMPLATE,
    user_prompt_template: str = PERSONA_FEEDBACK_USER_PROMPT_TEMPLATE,
    transcript_max_chars: int = 6000,
    max_concurrency: int = 1,
) -> ComparisonArtifacts:
    """
    End-to-end helper used by notebooks/scripts:
    - pick a training run
    - pick checkpoints (+ resolve sampler model paths)
    - load dataset samples
    - sample each checkpoint for each sample
    """
    sc = service_client or ServiceClient()
    rc = sc.create_rest_client()

    paths = collect_repo_paths(start_path or Path.cwd())
    split = dataset_split.lower()

    tr = select_training_run(rc, training_run_id=training_run_id, run_index=run_index)
    checkpoints = list_checkpoints_for_run(rc, tr.training_run_id)
    selected_ckpts = pick_checkpoints_spread(
        checkpoints, k=num_checkpoints, prefer_training=prefer_training_checkpoints
    )
    if not selected_ckpts:
        raise RuntimeError("No checkpoints selected")
    model_paths = resolve_sampler_model_paths(sc, selected_ckpts, auto_materialize=auto_materialize_sampler)

    jsonl_path = dataset_jsonl_path(paths.dataset_root, split)
    video_ids = select_video_ids(
        jsonl_path,
        split=split,
        num_videos=num_videos,
        seed=random_seed,
        selection=video_selection,
    )

    samples, _missing = load_samples_for_video_ids(
        dataset_root=paths.dataset_root,
        transcripts_dir=paths.transcripts_dir,
        video_ids=video_ids,
        split=split,
    )

    if sampling_params is None:
        sampling_params = types.SamplingParams(max_tokens=512, temperature=0.0)

    results = sample_checkpoints_for_videos(
        service_client=sc,
        model_paths=model_paths,
        samples=samples,
        sampling_params=sampling_params,
        system_prompt=system_prompt,
        user_prompt_template=user_prompt_template,
        transcript_max_chars=transcript_max_chars,
        max_concurrency=max_concurrency,
    )

    return ComparisonArtifacts(
        paths=paths,
        training_run=tr,
        checkpoints=selected_ckpts,
        model_paths=list(model_paths),
        samples=list(samples),
        results=results,
        split=split,
    )


def build_comparison_html(artifacts: ComparisonArtifacts) -> list[str]:
    """
    Convenience wrapper to render a `ComparisonArtifacts` into per-video HTML blocks.
    """
    return build_result_tables_html(
        samples=artifacts.samples,
        checkpoints=artifacts.checkpoints,
        model_paths=artifacts.model_paths,
        results=artifacts.results,
        split=artifacts.split,
    )


# --- Presentation helpers ------------------------------------------------ #


def short_label(ckpt: types.Checkpoint) -> str:
    return f"{ckpt.checkpoint_type}:{ckpt.checkpoint_id}".replace("sampler_weights/", "")


def html_escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def build_result_tables_html(
    *,
    samples: Sequence[VideoSample],
    checkpoints: Sequence[types.Checkpoint],
    model_paths: Sequence[str],
    results: dict[tuple[str, str], str],
    split: str,
) -> list[str]:
    """
    Build HTML tables (one per video) that callers can display in notebooks.
    """
    col_labels = [short_label(c) for c in checkpoints]
    html_blocks: list[str] = []

    for sample in samples:
        rows: list[tuple[str, str]] = [("GOLD (target.synthetic_user_feedback)", sample.gold_feedback)]
        for model_path, label in zip(model_paths, col_labels, strict=True):
            rows.append((label, results.get((sample.video_id, model_path), "")))

        table_rows = "\n".join(
            f"<tr><th style='text-align:left; vertical-align:top; white-space:nowrap; padding:8px; border:1px solid #ddd;'>{html_escape(label)}</th>"
            f"<td style='text-align:left; vertical-align:top; padding:8px; border:1px solid #ddd;'><pre style='text-align:left; white-space:pre-wrap; margin:0;'>{html_escape(text)}</pre></td></tr>"
            for (label, text) in rows
        )

        html_blocks.append(
            f"""
            <h3>Video: {html_escape(sample.video_id)} <span style='font-weight:normal; color:#666'>(split={html_escape(split)}, persona={html_escape(sample.persona_id)})</span></h3>
            <table style='border-collapse:collapse; width:100%; text-align:left;'>
              <tbody>
                {table_rows}
              </tbody>
            </table>
            """
        )
    return html_blocks

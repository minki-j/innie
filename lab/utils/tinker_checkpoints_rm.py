from __future__ import annotations

import argparse
import datetime as dt
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import tinker
from tinker import types

from utils import find_repo_root, load_dotenv


@dataclass(frozen=True)
class CheckpointRef:
    training_run_id: str
    checkpoint_id: str
    checkpoint_type: str | None
    tinker_path: str | None
    created_time_s: int | None
    public: bool | None
    size_bytes: int | None


def _to_unix_s(x: object) -> int | None:
    if x is None:
        return None
    if isinstance(x, bool):
        # Avoid treating bool as int.
        return None
    if isinstance(x, (int, float)):
        return int(x)
    if isinstance(x, str):
        s = x.strip()
        if not s:
            return None
        # Common case: already a numeric unix timestamp.
        try:
            return int(s)
        except Exception:
            pass
        # ISO 8601 (often ends with 'Z'); python wants '+00:00'.
        try:
            s2 = s.replace("Z", "+00:00")
            dt_obj = dt.datetime.fromisoformat(s2)
            if dt_obj.tzinfo is None:
                dt_obj = dt_obj.replace(tzinfo=dt.timezone.utc)
            return int(dt_obj.timestamp())
        except Exception:
            return None
    if isinstance(x, dt.datetime):
        dt_obj = x
        if dt_obj.tzinfo is None:
            dt_obj = dt_obj.replace(tzinfo=dt.timezone.utc)
        return int(dt_obj.timestamp())
    # Try generic datetime-like objects (e.g. pandas Timestamp)
    ts = getattr(x, "timestamp", None)
    if callable(ts):
        try:
            return int(ts())
        except Exception:
            return None
    return None


def _format_ts(ts_s: int | None) -> str:
    if ts_s is None:
        return "unknown-time"
    # Tinker timestamps are unix seconds.
    return (
        dt.datetime.fromtimestamp(ts_s, tz=dt.timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _coerce_checkpoint_ref(cp: object) -> CheckpointRef:
    checkpoint_id = getattr(cp, "checkpoint_id", None)
    checkpoint_type = getattr(cp, "checkpoint_type", None)
    tinker_path = getattr(cp, "tinker_path", None)
    created_time_s = _to_unix_s(getattr(cp, "time", None))
    public = getattr(cp, "public", None)
    size_bytes = getattr(cp, "size_bytes", None)

    training_run_id = getattr(cp, "training_run_id", None)

    if tinker_path:
        parsed = types.ParsedCheckpointTinkerPath.from_tinker_path(tinker_path)
        if training_run_id is None:
            training_run_id = parsed.training_run_id
        if checkpoint_id is None:
            checkpoint_id = parsed.checkpoint_id
        if checkpoint_type is None:
            checkpoint_type = parsed.checkpoint_type

    if training_run_id is None or checkpoint_id is None:
        raise ValueError(
            "Could not determine (training_run_id, checkpoint_id) for checkpoint "
            f"(training_run_id={training_run_id!r}, checkpoint_id={checkpoint_id!r}, tinker_path={tinker_path!r})."
        )

    return CheckpointRef(
        training_run_id=str(training_run_id),
        checkpoint_id=str(checkpoint_id),
        checkpoint_type=str(checkpoint_type) if checkpoint_type is not None else None,
        tinker_path=str(tinker_path) if tinker_path is not None else None,
        created_time_s=created_time_s,
        public=bool(public) if public is not None else None,
        size_bytes=int(size_bytes) if size_bytes is not None else None,
    )


def _iter_user_checkpoints(
    rest_client: object, *, page_size: int
) -> Iterable[CheckpointRef]:
    offset = 0
    while True:
        resp = rest_client.list_user_checkpoints(
            limit=page_size, offset=offset
        ).result()
        cps: Sequence[object] = getattr(resp, "checkpoints", [])
        if not cps:
            return
        for cp in cps:
            yield _coerce_checkpoint_ref(cp)

        cursor = getattr(resp, "cursor", None)
        if cursor is None:
            return

        total_count = getattr(cursor, "total_count", None)
        offset += len(cps)
        if total_count is not None and offset >= int(total_count):
            return


def _iter_training_run_checkpoints(
    rest_client: object, *, training_run_id: str
) -> Iterable[CheckpointRef]:
    resp = rest_client.list_checkpoints(training_run_id).result()
    cps: Sequence[object] = getattr(resp, "checkpoints", [])
    for cp in cps:
        yield _coerce_checkpoint_ref(cp)


def _get_last_training_run_id(rest_client: object, *, limit: int) -> str:
    resp = rest_client.list_training_runs(limit=limit, offset=0).result()
    runs: Sequence[object] = getattr(resp, "training_runs", [])
    if not runs:
        raise RuntimeError("No training runs found for current user.")

    # Pick run with greatest last_request_time, falling back to list order if missing.
    def score(r: object) -> int:
        ts = getattr(r, "last_request_time", None)
        try:
            return int(ts) if ts is not None else -1
        except Exception:
            return -1

    best = max(runs, key=score)
    rid = getattr(best, "training_run_id", None)
    if rid is None:
        raise RuntimeError("Training run object missing training_run_id.")
    return str(rid)


def _get_last_checkpoint_for_run(
    rest_client: object, *, training_run_id: str, checkpoint_type: str
) -> CheckpointRef:
    training_run = rest_client.get_training_run(training_run_id).result()
    if checkpoint_type == "training":
        cp = getattr(training_run, "last_checkpoint", None)
    elif checkpoint_type == "sampler":
        cp = getattr(training_run, "last_sampler_checkpoint", None)
    else:
        raise ValueError(f"Unknown checkpoint_type: {checkpoint_type!r}")

    if cp is None:
        raise RuntimeError(
            f"No {checkpoint_type} checkpoints found for training run {training_run_id}."
        )
    return _coerce_checkpoint_ref(cp)


def _get_last_checkpoint_any_for_run(
    rest_client: object, *, training_run_id: str
) -> CheckpointRef:
    training_run = rest_client.get_training_run(training_run_id).result()
    candidates: list[CheckpointRef] = []
    for field in ("last_checkpoint", "last_sampler_checkpoint"):
        cp = getattr(training_run, field, None)
        if cp is not None:
            candidates.append(_coerce_checkpoint_ref(cp))
    if not candidates:
        raise RuntimeError(f"No checkpoints found for training run {training_run_id}.")

    def key(c: CheckpointRef) -> int:
        return c.created_time_s if c.created_time_s is not None else -1

    return max(candidates, key=key)


def _print_plan(checkpoints: Sequence[CheckpointRef], *, apply: bool) -> None:
    mode = "APPLY (will delete)" if apply else "DRY-RUN (no deletions)"
    print(f"{mode}: {len(checkpoints)} checkpoint(s)")
    for cp in checkpoints:
        size = f"{cp.size_bytes}B" if cp.size_bytes is not None else "unknown-size"
        pub = (
            "public"
            if cp.public
            else ("private" if cp.public is not None else "unknown-public")
        )
        ctype = cp.checkpoint_type or "unknown-type"
        ts = _format_ts(cp.created_time_s)
        print(
            f"- {cp.training_run_id} {cp.checkpoint_id} ({ctype}, {pub}, {size}, {ts})"
        )


def _delete_checkpoints(
    rest_client: object, checkpoints: Sequence[CheckpointRef]
) -> None:
    for cp in checkpoints:
        if cp.tinker_path:
            rest_client.delete_checkpoint_from_tinker_path(cp.tinker_path).result()
        else:
            rest_client.delete_checkpoint(cp.training_run_id, cp.checkpoint_id).result()


def _dedupe(checkpoints: Iterable[CheckpointRef]) -> list[CheckpointRef]:
    seen: set[tuple[str, str]] = set()
    out: list[CheckpointRef] = []
    for cp in checkpoints:
        key = (cp.training_run_id, cp.checkpoint_id)
        if key in seen:
            continue
        seen.add(key)
        out.append(cp)
    return out


def _filter_public(
    checkpoints: Iterable[CheckpointRef], *, include_public: bool
) -> list[CheckpointRef]:
    if include_public:
        return list(checkpoints)
    return [cp for cp in checkpoints if cp.public is not True]


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--dotenv",
        type=str,
        default=None,
        help="Path to a .env file to load (defaults to <repo-root>/.env if present).",
    )
    common.add_argument(
        "--page-size",
        type=int,
        default=200,
        help="Page size for REST list calls (default: 200).",
    )
    common.add_argument(
        "--include-public",
        action="store_true",
        help="Also delete published/public checkpoints (default: skip public checkpoints).",
    )
    common.add_argument(
        "--apply",
        action="store_true",
        help="Actually delete checkpoints (default: dry-run).",
    )
    common.add_argument(
        "--yes",
        action="store_true",
        help="Alias for --apply.",
    )

    p = argparse.ArgumentParser(
        prog="tinker-checkpoints-rm",
        description="Delete Tinker checkpoints (dry-run by default).",
        parents=[common],
    )

    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser(
        "remove-all",
        help="Remove all checkpoints for the current user.",
        parents=[common],
    )

    s_training = sub.add_parser(
        "remove-training",
        help="Remove all checkpoints from a specific training run.",
        parents=[common],
    )
    s_training.add_argument("--training-run-id", required=True)

    s_ckpt = sub.add_parser(
        "remove-checkpoint", help="Remove a specific checkpoint.", parents=[common]
    )
    s_ckpt.add_argument("--training-run-id", help="Required if using --checkpoint-id.")
    s_ckpt.add_argument(
        "--checkpoint-id", help="Checkpoint ID (requires --training-run-id)."
    )
    s_ckpt.add_argument(
        "--tinker-path", help="Full tinker path (e.g. tinker://.../weights/0001)."
    )

    s_last = sub.add_parser(
        "remove-last-training-checkpoint",
        help="Remove the most recent checkpoint in the most recent training run.",
        parents=[common],
    )
    s_last.add_argument(
        "--checkpoint-type",
        choices=["any", "training", "sampler"],
        default="any",
        help="Which checkpoint type to consider on the last training run (default: any).",
    )
    s_last.add_argument(
        "--training-limit",
        type=int,
        default=200,
        help="How many recent training runs to consider when selecting the last run (default: 200).",
    )

    s_old = sub.add_parser(
        "remove-older-than",
        help="Remove all checkpoints older than N days (across all training runs).",
        parents=[common],
    )
    window = s_old.add_mutually_exclusive_group(required=True)
    window.add_argument(
        "--days", type=int, help="Remove checkpoints older than this many days."
    )
    window.add_argument(
        "--hour",
        "--hours",
        dest="hours",
        type=int,
        help="Remove checkpoints older than this many hours.",
    )

    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    apply = bool(args.apply or args.yes)
    page_size = int(args.page_size)
    include_public = bool(args.include_public)

    # Load env vars for Tinker (most importantly TINKER_API_KEY).
    # We default to loading <repo-root>/.env if it exists, without overriding
    # already-exported environment variables.
    dotenv_path = (
        Path(args.dotenv) if args.dotenv else (find_repo_root(Path.cwd()) / ".env")
    )
    load_dotenv(dotenv_path)

    service_client = tinker.ServiceClient()
    rest_client = service_client.create_rest_client()

    try:
        if args.cmd == "remove-all":
            cps = _iter_user_checkpoints(rest_client, page_size=page_size)
            plan = _filter_public(_dedupe(cps), include_public=include_public)

        elif args.cmd == "remove-training":
            cps = _iter_training_run_checkpoints(
                rest_client, training_run_id=str(args.training_run_id)
            )
            plan = _filter_public(_dedupe(cps), include_public=include_public)

        elif args.cmd == "remove-checkpoint":
            if args.tinker_path:
                cp = _coerce_checkpoint_ref(
                    types.ParsedCheckpointTinkerPath.from_tinker_path(args.tinker_path)
                )
                # ParsedCheckpointTinkerPath doesn't include created/public/size; keep basics.
                plan = [
                    CheckpointRef(
                        training_run_id=cp.training_run_id,
                        checkpoint_id=cp.checkpoint_id,
                        checkpoint_type=cp.checkpoint_type,
                        tinker_path=args.tinker_path,
                        created_time_s=None,
                        public=None,
                        size_bytes=None,
                    )
                ]
            else:
                if not args.training_run_id or not args.checkpoint_id:
                    raise SystemExit(
                        "remove-checkpoint requires either --tinker-path OR (--training-run-id and --checkpoint-id)."
                    )
                plan = [
                    CheckpointRef(
                        training_run_id=str(args.training_run_id),
                        checkpoint_id=str(args.checkpoint_id),
                        checkpoint_type=None,
                        tinker_path=None,
                        created_time_s=None,
                        public=None,
                        size_bytes=None,
                    )
                ]

            plan = _filter_public(plan, include_public=include_public)

        elif args.cmd == "remove-last-training-checkpoint":
            training_run_id = _get_last_training_run_id(
                rest_client, limit=int(args.training_limit)
            )
            if args.checkpoint_type == "training":
                last = _get_last_checkpoint_for_run(
                    rest_client,
                    training_run_id=training_run_id,
                    checkpoint_type="training",
                )
            elif args.checkpoint_type == "sampler":
                last = _get_last_checkpoint_for_run(
                    rest_client,
                    training_run_id=training_run_id,
                    checkpoint_type="sampler",
                )
            else:
                last = _get_last_checkpoint_any_for_run(
                    rest_client, training_run_id=training_run_id
                )
            plan = _filter_public([last], include_public=include_public)

        elif args.cmd == "remove-older-than":
            if args.days is not None:
                days = int(args.days)
                if days < 0:
                    raise SystemExit("--days must be >= 0")
                seconds = days * 86400
            else:
                hours = int(args.hours)
                if hours < 0:
                    raise SystemExit("--hour/--hours must be >= 0")
                seconds = hours * 3600

            cutoff = int(time.time() - seconds)
            cps = (
                cp
                for cp in _iter_user_checkpoints(rest_client, page_size=page_size)
                if (cp.created_time_s is not None and cp.created_time_s < cutoff)
            )
            plan = _filter_public(_dedupe(cps), include_public=include_public)

        else:
            raise SystemExit(f"Unknown command: {args.cmd!r}")

        _print_plan(plan, apply=apply)
        if apply:
            _delete_checkpoints(rest_client, plan)
            print(f"Deleted {len(plan)} checkpoint(s).")
        else:
            print("No changes made. Re-run with --apply (or --yes) to delete.")

        return 0

    except SystemExit:
        raise
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

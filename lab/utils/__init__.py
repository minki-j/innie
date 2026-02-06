"""
Small, dependency-free utilities shared across `lab/` code.

Note: `lab/` is typically added to `PYTHONPATH`, so packages under `lab/`
(`datasets`, `trains`, `utils`, ...) are imported as top-level modules.
"""

from .checkpoint_comparison import (
    PERSONA_FEEDBACK_SYSTEM_PROMPT_TEMPLATE,
    PERSONA_FEEDBACK_USER_PROMPT_TEMPLATE,
    ComparisonArtifacts,
    RepoPaths,
    VideoSample,
    build_comparison_html,
    build_result_tables_html,
    collect_repo_paths,
    dataset_jsonl_path,
    list_checkpoints_for_run,
    list_recent_training_runs,
    list_unique_video_ids_from_jsonl,
    load_samples_for_video_ids,
    pick_checkpoints_spread,
    pick_random_unique_video_ids,
    resolve_sampler_model_paths,
    run_checkpoint_comparison,
    sample_checkpoints_for_videos,
)
from .fs import find_repo_root, load_dotenv
from .preview import preview_text, preview_tokens, truncate_messages
from .tokens import to_int_list

__all__ = [
    "PERSONA_FEEDBACK_SYSTEM_PROMPT_TEMPLATE",
    "PERSONA_FEEDBACK_USER_PROMPT_TEMPLATE",
    "ComparisonArtifacts",
    "RepoPaths",
    "VideoSample",
    "build_comparison_html",
    "build_result_tables_html",
    "collect_repo_paths",
    "dataset_jsonl_path",
    "find_repo_root",
    "load_dotenv",
    "list_checkpoints_for_run",
    "list_recent_training_runs",
    "list_unique_video_ids_from_jsonl",
    "load_samples_for_video_ids",
    "pick_checkpoints_spread",
    "pick_random_unique_video_ids",
    "preview_text",
    "preview_tokens",
    "resolve_sampler_model_paths",
    "run_checkpoint_comparison",
    "sample_checkpoints_for_videos",
    "truncate_messages",
    "to_int_list",
]

# SFT: YouTube reviews

This training script fine-tunes a chat/instruct model using supervised learning (cross-entropy),
on the same inputs as `trains/rlvr_youtube_reviews`, but uses `synthetic_user_feedback` as the
ground-truth assistant output.

## Run

From the `lab/` environment:

```bash
uv run -m trains.sft_youtube_reviews.train --help
```

Example:

```bash
uv run -m trains.sft_youtube_reviews.train \
  --base-model meta-llama/Llama-3.1-8B-Instruct \
  --persona-id junior_engineer_side_projects \
  --batch-size 8 \
  --epochs 1 \
  --learning-rate 2e-4
```


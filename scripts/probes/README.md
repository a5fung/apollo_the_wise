# scripts/probes/ — throwaway diagnostic probes

One-off, read-only diagnostic / reconstruction scripts written to investigate a
specific incident or question, then kept as the reproduction artifact. They are
NOT part of any pipeline (deploy.sh, CI, cron, the data_gated_reviews registry)
and NOT imported by any module — that's the criterion for living here (#261).

If a probe graduates into a re-runnable tool (cited by a data_gated_review, a
scheduled job, or imported as a shared helper), move it back up to `scripts/`.
Shared helper modules (`_judge_replay_common`, `_grounded_reconstruct`,
`_backward_check_utils`, `_judge_review_sql`) and the coupled `_270_*` replay
cluster deliberately stay in `scripts/` — they are imported by real code/tests.

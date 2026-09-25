# dashpi eval — analysis model comparison harness

Internal dev tool for comparing vision/report model combinations on labelled
incident clips. This README names real provider/model IDs — that's fine here
(the "no provider names" rule applies to the public README and landing page,
not this internal tool).

## Case format

Each case is a folder under `eval/cases/` containing:

- `clip.mp4` — the evidence clip. **Do not commit clip files** (they're real
  or synthetic dashcam footage and can be large); `eval/cases/` only tracks
  `.gitkeep` and each case's `expected.json`.
- `expected.json` — the ground truth for scoring:

```json
{
  "incident_timestamp": 10.0,
  "timestamp_tolerance": 1.0,
  "must_observe": ["브레이크등", "빨간불"],
  "must_not_claim": ["보행자"]
}
```

- `incident_timestamp` (required): the true incident moment, in seconds from
  clip start.
- `timestamp_tolerance` (optional, default `1.0`): how many seconds off the
  located moment may be and still count as a pass.
- `must_observe` (optional): Korean terms that should appear somewhere in the
  model's observations for full recall credit.
- `must_not_claim` (optional): Korean terms (fault/blame words, plus this
  case's forbidden claims) that must not appear in the observations or report.

## Running

```bash
dashpi eval \
  --cases eval/cases \
  --vision-model x-ai/grok-4.7 \
  --vision-model openai/gpt-6-sol \
  --vision-model anthropic/claude-sonnet-5 \
  --report-model x-ai/grok-4.20 \
  --report-model openai/gpt-6-luna \
  --report-model anthropic/claude-haiku-4.5 \
  --out eval/results/2026-09-25.jsonl
```

The harness fetches current OpenRouter prices for every model given, prints an
estimated maximum cost for the full run, and asks for confirmation before
spending anything (pass `--yes` to skip the prompt). Results are appended to
`--out` as JSON Lines (one row per case × vision model × report model) and a
summary table is printed at the end.

# Day 9 — API check (2026-09-22 17:35)

## Stage readiness

- **llm**: ready
- **corpus**: ready
- **detector**: ready
- **case_memory**: ready

Pipeline ready: **True**

## Requests

| case | HTTP | ms | grounded | cited | refused | risk | dets | cases |
|---|---:|---:|---|---|---|---|---:|---:|
| empty query, no image | 400 | 20 | — | — | — | — | — | — |
| whitespace only | 400 | 22 | — | — | — | — | — | — |
| nonsense query | 200 | 12188 | True | True | True | — | 0 | 3 |
| very long query | 200 | 37872 | True | True | False | — | 0 | 3 |
| out-of-corpus query | 200 | 21916 | True | True | True | — | 0 | 3 |
| normal query | 200 | 12161 | True | True | False | — | 0 | 3 |

Average successful request: **21034 ms** (feeds D11-02).

## Per-stage timing, last successful request

| stage | ok | ms | note |
|---|---|---:|---|
| detection | yes | 0 | no image supplied — text-only diagnosis |
| risk | yes | 0 | no detections to score |
| diagnosis | yes | 12136 |  |
| case_memory | yes | 17 |  |

## Edge cases (D10-02)

No 5xx responses. Every edge case degraded gracefully: each one returned a normal response explaining what was missing, or a 4xx naming the problem.

## Response contract (D9-01 step 4)

```
detections[]   label, confidence, box, pretrained
risks[]        level, severity, confidence, rationale, needs_human_review
overall_risk   the governing risk — the WORST, not the average
risk_score     convenience alias: overall_risk.level
diagnosis      grounded text, citations inline as [document p.N]
citations[]    parsed citation labels
sources[]      source, page, score for each retrieved passage
grounded       retrieval found something above threshold
cited_ok       the answer cited a source that was actually retrieved
refused        the model declined because the manuals do not cover it
needs_input    set when there was nothing to diagnose, and why
similar_cases[]  case_id, defect_type, resolution, similarity
stages[]       name, ok, ms, skipped, error, note
timing_ms      total
```

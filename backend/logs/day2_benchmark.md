# Day 2 — LLM performance (2026-09-22 12:20)

- Backend: `ollama`  Model: `phi3:mini`
- GPU: 156 MiB / 4096 MiB (NVIDIA GeForce RTX 3050 Laptop GPU) — 4% used
- Repeats per prompt: 3  Max tokens: 256

| prompt | chars | tok | wall (s) | generation (s) | other (s) | tok/s |
|---|---:|---:|---:|---:|---:|---:|
| short | 28 | 126 | 7.34 | 7.24 | 0.10 | 17.4 |
| short | 28 | 116 | 6.72 | 6.62 | 0.10 | 17.5 |
| short | 28 | 110 | 6.32 | 6.20 | 0.12 | 17.8 |
| medium | 235 | 209 | 12.67 | 12.40 | 0.27 | 16.9 |
| medium | 235 | 213 | 12.78 | 12.65 | 0.14 | 16.8 |
| medium | 235 | 248 | 15.03 | 14.90 | 0.13 | 16.6 |
| long | 2191 | 130 | 9.94 | 9.21 | 0.72 | 14.1 |
| long | 2191 | 256 | 18.42 | 18.31 | 0.10 | 14.0 |
| long | 2191 | 157 | 11.36 | 11.27 | 0.09 | 13.9 |

**Median 16.8 tok/s. Typical call 11.36s, worst 18.42s. Non-generation overhead: median 0.12s, worst 0.72s.**

## Demo verdict

Usable but slow at 11.4s typical. Lower MAX_TOKENS (a diagnosis rarely needs 256) and show a spinner in the Day 9 UI.

## Cold start

Send one throwaway prompt during setup so the jury's first question hits a warm model.

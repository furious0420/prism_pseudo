# PRISM — working agreement

## Commit convention
Use a type prefix on every commit:

| Prefix   | Use for                                        |
|----------|------------------------------------------------|
| `feat:`  | new functionality                              |
| `fix:`   | bug fix                                        |
| `chore:` | deps, config, scaffolding, no behaviour change |
| `docs:`  | README, notes, tracker updates                 |

Example: `feat: wire retrieval into generate() for D4-01`

## Daily handoff
One person works the build per day (see `PRISM_Task_Tracker.xlsx`).
Before ending your session, fill in the **Handoff Notes** column for every task
you touched. The next person starts by reading it. An unfilled handoff note is
the single most expensive thing you can leave behind.

## Never commit
`.env`, AWS keys, `*.gguf` / `*.pt` model weights, or dataset images.
The `.gitignore` covers these — do not override it with `git add -f`.

## Secrets
AWS credentials belong in `backend/.env`, created from `backend/.env.example`.
Use the dedicated `prism-dev` IAM user, **never** root account keys.
Policy to attach: `infra/iam-policy-prism-dev.json`.

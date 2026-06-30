# CLAUDE.md — read this first, every session

This file is loaded automatically at the start of every session in this project. If you are a fresh session, do this before anything else:

1. **Read `STATUS.md`** — it's the single source of truth for where we are and what the next step is.
2. Skim `README.md` for the big picture if needed.
3. Only then respond to the user.

## What this project is
The user is building an **options trading bot** that automates their **wheel strategy** (cash-secured puts → covered calls). The bot is primarily a **resume project**; real profit is a bonus. Honesty and rigor matter more than headline returns.

The user is a near-beginner coder and beginner at stats/probability, but motivated. Teach concepts *through* the trading, go slowly, hand-hold, one step at a time. They trade on **Schwab / ThinkorSwim**, small account.

## How we stay organized (so nobody gets lost across sessions)
- `STATUS.md` — living "where we left off + next step + session log." **Update it at the end of meaningful work**, and whenever a decision is made.
- `README.md` — human-readable project overview (also doubles as resume material).
- `strategies/` — one plain-English explainer per strategy we study (written for the user).
- `research/` — raw transcripts and user notes (messy is fine). Option Alpha transcripts live here.
- `decisions/strategy-choice.md` — the scorecard comparing strategies, toward picking THE one to build.
- `bot/` — code (added later, once a strategy is chosen).

## Current phase
**Research phase:** studying different strategies from the user's YouTube transcripts to choose the best one to automate. We have NOT started coding yet. Do not jump ahead to building until a strategy is chosen.

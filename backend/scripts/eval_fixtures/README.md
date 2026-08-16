# RM-12 eval fixtures

Input content for `scripts/rm12_model_eval.py`. One `.txt` per fixture; the
stem becomes the row label in the report.

These are **resolved content**, not raw documents — the planner takes the
outline/brief a generation would actually hand it, never a whole notebook
(`COST-AND-MODEL-STRATEGY.md` §4.1).

Committed so the eval is reproducible: comparing models across different
inputs measures nothing. Replace these with real BRI-style material before
treating the scores as decision-grade — the Bahasa Indonesia fluency rating in
particular only means something on content resembling your actual decks.

**Do not commit anything confidential here.** These files are in version
control and the eval sends them to a third-party API.

"""GRPO reward + advantage helpers for MODEL-FORGE (Milestone 5).

The reward is *executable*, not opinion-based (the whole point of picking a verifiable
domain): run the candidate SQL against the real demo DB and compare rows to gold.

    R = 1.0   query runs AND returns the gold rows
        0.2   valid SQL but wrong rows (partial credit — kept the shape, missed the answer)
        0.0   syntax error / execution failure / timeout

GRPO (Group-Relative Policy Optimization) samples K candidates per prompt and updates
toward those that beat the *group's own average* — so we also expose the group-relative
advantage. This module is the reward the TRL/vLLM notebook imports; keeping it here makes
it unit-testable and shared with FORGE's eval harness.
"""

from __future__ import annotations

import sqlite3
import statistics

from app.model_forge.data_gen import build_db, rows_match

REWARD_CORRECT = 1.0
REWARD_VALID_WRONG = 0.2
REWARD_INVALID = 0.0


def _clean_sql(text: str) -> str:
    """Strip markdown fences / prose the model may wrap around the query."""
    t = (text or "").strip()
    t = t.removeprefix("```sql").removeprefix("```").removesuffix("```").strip()
    return t


def sql_reward(candidate_sql: str, gold_rows: list[list],
               conn: sqlite3.Connection | None = None) -> float:
    """Executable reward for one candidate query."""
    close = conn is None
    conn = conn or build_db()
    try:
        try:
            rows = [list(map(str, r)) for r in conn.execute(_clean_sql(candidate_sql)).fetchall()]
        except sqlite3.Error:
            return REWARD_INVALID
        return REWARD_CORRECT if rows_match(rows, gold_rows) else REWARD_VALID_WRONG
    finally:
        if close:
            conn.close()


def group_advantages(rewards: list[float]) -> list[float]:
    """Group-relative advantage A_i = (R_i - mean) / std — the core GRPO signal."""
    if not rewards:
        return []
    if len(rewards) == 1:
        return [0.0]
    mean = sum(rewards) / len(rewards)
    std = statistics.pstdev(rewards)
    if std == 0:
        return [0.0] * len(rewards)
    return [(r - mean) / std for r in rewards]


def score_group(candidates: list[str], gold_rows: list[list],
                conn: sqlite3.Connection | None = None) -> tuple[list[float], list[float]]:
    """Score K sampled completions for one prompt → (rewards, advantages)."""
    close = conn is None
    conn = conn or build_db()
    try:
        rewards = [sql_reward(c, gold_rows, conn) for c in candidates]
    finally:
        if close:
            conn.close()
    return rewards, group_advantages(rewards)

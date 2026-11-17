"""Context compressors for CLI logs, Python ASTs, and multi-turn coding-agent sessions."""

from __future__ import annotations


def estimate_tokens(text: str) -> int:
    """Fast deterministic token estimator (~4 chars per token)."""
    if not text:
        return 0
    return max(1, (len(text) + 3) // 4)

"""CLI & test output pruner backed by the C++20 Order-Preserving Salience Knapsack kernel."""

from __future__ import annotations

import re

from tokendiet.compressors import estimate_tokens
from tokendiet.kernels.native_prune import active_backend_name, hash_text_u64, salience_knapsack
from tokendiet.types import PrunedOutputReport, PruneLineResult

_MANDATORY_PATTERNS = (
    re.compile(r"traceback \(most recent call last\)", re.IGNORECASE),
    re.compile(r'file\s+".+",\s+line\s+\d+', re.IGNORECASE),
    re.compile(
        r"\b(error|exception|failed|fatal|assertionerror|zerodivisionerror|modulenotfounderror|"
        r"typeerror|valueerror|keyerror|attributeerror|importerror|syntaxerror|runtimeerror|"
        r"checkviolationerror|timeouterror)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\berror TS\d+:", re.IGNORECASE),
    re.compile(r"error\[[a-z0-9]+\]", re.IGNORECASE),
    re.compile(r"\bviolates\b", re.IGNORECASE),
    re.compile(r"^E\s{2,}\S"),
)

_HIGH_PATTERNS = (
    re.compile(r"\b(warn|warning|summary|caused by|detail:)\b", re.IGNORECASE),
    re.compile(r"short test summary", re.IGNORECASE),
    re.compile(r"^={3,}|^-{3,}"),
)

_MEDIUM_PATTERNS = (
    re.compile(r"^[+-]{1,3}\s+\S|^@@\s"),
    re.compile(r"\b(src/|tests?/|apps?/|packages?/)\S+\.(py|ts|tsx|js|cpp|rs|go)\b"),
    re.compile(r"\bexit\s+code\b", re.IGNORECASE),
)

_NOISE_PATTERNS = (
    re.compile(
        r"^\s*(collecting|downloading|using cached|copying|building|running|passed|ok|info|\[\s*\d+%\]|#\d+\s+cached)",
        re.IGNORECASE,
    ),
    re.compile(r"\bPASSED\s+\[\s*\d+%\]$"),
)


def score_output_line(line: str) -> tuple[int, bool]:
    """Classify a tool/log line into (integer_salience_score, is_mandatory_anchor)."""
    stripped = line.strip()
    if not stripped:
        return 10, False

    for pat in _MANDATORY_PATTERNS:
        if pat.search(stripped):
            return 1000, True

    for pat in _HIGH_PATTERNS:
        if pat.search(stripped):
            return 650, False

    for pat in _MEDIUM_PATTERNS:
        if pat.search(stripped):
            return 250, False

    for pat in _NOISE_PATTERNS:
        if pat.search(stripped):
            return 25, False

    return 120, False


def prune_tool_output(
    text: str,
    budget_tokens: int = 180,
    halo_radius: int = 2,
) -> PrunedOutputReport:
    """Prune bloated CLI/test logs while preserving chronological order and 100% feasible anchors."""
    if not text.strip():
        return PrunedOutputReport(
            kernel_backend=active_backend_name(),
            budget_tokens=budget_tokens,
            halo_radius=halo_radius,
            total_lines=0,
            kept_lines=0,
            omitted_lines=0,
            original_tokens=0,
            compressed_tokens=0,
            savings_pct=0.0,
            total_anchors=0,
            kept_anchors=0,
            anchor_retention_pct=100.0,
            compressed_text="",
            line_details=[],
        )

    lines = text.splitlines()
    orig_tokens = estimate_tokens(text)
    costs: list[int] = []
    scores: list[int] = []
    hashes: list[int] = []
    mand_flags: list[int] = []

    for line in lines:
        cost = max(1, estimate_tokens(line))
        score, mand = score_output_line(line)
        costs.append(cost)
        scores.append(score)
        hashes.append(hash_text_u64(line.strip()))
        mand_flags.append(1 if mand else 0)

    selected_indices, _, _ = salience_knapsack(
        token_costs=costs,
        raw_scores=scores,
        line_hashes=hashes,
        mandatory_flags=mand_flags,
        budget_tokens=budget_tokens,
        halo_radius=halo_radius,
    )
    selected_set = set(selected_indices)

    total_anchors = sum(1 for i in range(len(lines)) if mand_flags[i] == 1 or scores[i] >= 800)
    kept_anchors = sum(1 for i in selected_indices if mand_flags[i] == 1 or scores[i] >= 800)
    retention = round((kept_anchors / total_anchors) * 100.0, 2) if total_anchors > 0 else 100.0

    if len(selected_indices) == len(lines):
        compressed_text = text
    else:
        chunks: list[str] = []
        prev = -1
        for idx in selected_indices:
            if idx - prev > 1:
                omitted = idx - prev - 1
                chunks.append(f"[... tokendiet: omitted {omitted} low-salience lines ...]")
            chunks.append(lines[idx])
            prev = idx
        if len(lines) - 1 > prev:
            omitted_tail = (len(lines) - 1) - prev
            chunks.append(f"[... tokendiet: omitted {omitted_tail} trailing lines ...]")
        compressed_text = "\n".join(chunks)

    comp_tokens = estimate_tokens(compressed_text)
    savings = round(max(0.0, (1.0 - comp_tokens / max(1, orig_tokens)) * 100.0), 2)
    details = [
        PruneLineResult(
            line_index=i,
            raw_score=scores[i],
            mandatory=bool(mand_flags[i]),
            token_cost=costs[i],
            kept=i in selected_set,
            text=lines[i],
        )
        for i in range(len(lines))
    ]

    return PrunedOutputReport(
        kernel_backend=active_backend_name(),
        budget_tokens=budget_tokens,
        halo_radius=halo_radius,
        total_lines=len(lines),
        kept_lines=len(selected_indices),
        omitted_lines=len(lines) - len(selected_indices),
        original_tokens=orig_tokens,
        compressed_tokens=comp_tokens,
        savings_pct=savings,
        total_anchors=total_anchors,
        kept_anchors=kept_anchors,
        anchor_retention_pct=retention,
        compressed_text=compressed_text,
        line_details=details,
    )

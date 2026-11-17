"""FinOps multi-tier model router with Cascade Escalation Guard."""

from __future__ import annotations

from tokendiet.types import FinOpsRouteDecision, ModelTier

_TIER_SPECS: dict[ModelTier, tuple[str, float]] = {
    ModelTier.LOCAL_FLASH: ("qwen3.5:4b / flash-tier", 0.10),
    ModelTier.BALANCED_CODING: ("sonnet-class / medium-coding", 3.00),
    ModelTier.FRONTIER_REASONING: ("opus-class / frontier-reasoning", 15.00),
}

_ARCHITECTURAL_HINTS = (
    "refactor",
    "architect",
    "migration",
    "distributed",
    "consensus",
    "schema",
    "cross-service",
    "pipeline",
)


def route_turn_finops(
    prompt_summary: str,
    context_tokens_raw: int,
    context_tokens_compressed: int,
    retry_count: int = 0,
    requires_formal_or_security_proof: bool = False,
    multi_file_count: int = 1,
) -> FinOpsRouteDecision:
    """Route a turn cleanly across Local Flash, Balanced Coding, and Frontier Reasoning tiers."""
    lowered = prompt_summary.lower()
    raw_tok = max(1, context_tokens_raw)
    comp_tok = max(1, min(raw_tok, context_tokens_compressed))

    arch_hits = sum(1 for kw in _ARCHITECTURAL_HINTS if kw in lowered)
    complexity = min(
        100,
        15
        + multi_file_count * 12
        + arch_hits * 18
        + retry_count * 25
        + (40 if requires_formal_or_security_proof else 0),
    )

    escalated = False
    if requires_formal_or_security_proof or retry_count >= 1:
        tier = ModelTier.FRONTIER_REASONING
        escalated = True
        reason = (
            "Cascade Escalation Guard triggered: formal/security invariant or retry recovery "
            f"(retries={retry_count}) requires Frontier Reasoning."
        )
    elif multi_file_count >= 3 or arch_hits >= 1 or complexity >= 50:
        tier = ModelTier.BALANCED_CODING
        reason = (
            f"Multi-file or architectural edit (files={multi_file_count}, score={complexity}) "
            "routed to Balanced Coding tier."
        )
    else:
        tier = ModelTier.LOCAL_FLASH
        reason = (
            f"Bounded single-unit extraction/fix (files={multi_file_count}, score={complexity}) "
            "routed to Local Flash tier with compressed context."
        )

    model_id, unit_cost = _TIER_SPECS[tier]
    naive_cost = round(raw_tok * 15.0 / 1_000_000.0, 6)
    routed_cost = round(comp_tok * unit_cost / 1_000_000.0, 6)
    reduction_pct = (
        round(max(0.0, (1.0 - routed_cost / naive_cost) * 100.0), 2) if naive_cost > 0 else 0.0
    )
    # Extrapolated illustrative rate assuming 180 turns/day across 250 workdays for a 50-engineer org.
    per_turn_delta = max(0.0, naive_cost - routed_cost)
    annual_50_eng = round(per_turn_delta * 180 * 250 * 50, 2)

    return FinOpsRouteDecision(
        selected_tier=tier,
        model_id=model_id,
        unit_cost_per_1m_usd=unit_cost,
        complexity_score=complexity,
        cascade_escalated=escalated,
        reason=reason,
        naive_frontier_cost_usd=naive_cost,
        routed_compressed_cost_usd=routed_cost,
        cost_reduction_pct=reduction_pct,
        annualized_50_eng_savings_usd=annual_50_eng,
    )

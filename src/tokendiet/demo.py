"""Deterministic coding-agent fixtures and showcase payload for tokendiet CLI and UI."""

from __future__ import annotations

from pydantic import BaseModel

from tokendiet.compressors.ast_skeleton import skeletonize_python_source
from tokendiet.compressors.log_pruner import prune_tool_output
from tokendiet.compressors.session_pruner import compress_agent_session
from tokendiet.router.finops_router import route_turn_finops
from tokendiet.types import (
    FinOpsRouteDecision,
    PrunedOutputReport,
    SessionCompressionReport,
    SessionTurnInput,
    SkeletonReport,
    TurnKind,
)

DEMO_PYTHON_MODULE = '''"""Production invoice settlement & proration engine."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class InvoiceLine:
    sku: str
    qty: int
    unit_cents: int
    tax_bps: int


def normalize_currency(code: str) -> str:
    """Validate and uppercase an ISO-4217 currency code."""
    cleaned = code.strip().upper()
    aliases = {"UKP": "GBP", "RMB": "CNY", "EURO": "EUR"}
    mapped = aliases.get(cleaned, cleaned)
    if len(mapped) != 3 or not mapped.isalpha():
        raise ValueError(f"Unsupported currency code: {code!r}")
    return mapped


def format_ledger_entry(account_id: str, amount_cents: int, currency: str) -> str:
    """Render deterministic double-entry ledger audit string."""
    norm = normalize_currency(currency)
    sign = "CR" if amount_cents >= 0 else "DR"
    abs_cents = abs(amount_cents)
    whole, frac = divmod(abs_cents, 100)
    return f"{account_id} | {sign} {norm} {whole:,}.{frac:02d}"


def compute_tax_breakdown(lines: list[InvoiceLine]) -> dict[str, int]:
    """Accumulate net subtotal and integer tax cents per line."""
    subtotal = 0
    tax_total = 0
    for item in lines:
        line_net = item.qty * item.unit_cents
        subtotal += line_net
        tax_total += (line_net * item.tax_bps + 5000) // 10000
    return {"subtotal_cents": subtotal, "tax_cents": tax_total, "gross_cents": subtotal + tax_total}


def compute_monthly_discount(annual_cents: int, discount_months: int) -> int:
    """Return amortized monthly credit in integer cents."""
    if annual_cents < 0:
        raise ValueError("annual_cents must be non-negative")
    return annual_cents // discount_months  # Bug when discount_months == 0
'''


def build_demo_pytest_log() -> str:
    passing = [
        f"tests/test_billing_{i:02d}.py::test_settlement_case_{i:02d} PASSED [{min(99, i + 10):3d}%]"
        for i in range(1, 55)
    ]
    core_failure = [
        "=================================== FAILURES ===================================",
        "_______________________ test_zero_month_discount_guard _________________________",
        "Traceback (most recent call last):",
        '  File "src/billing.py", line 142, in compute_monthly_discount',
        "    return annual_cents // discount_months",
        "ZeroDivisionError: integer division or modulo by zero",
        "=========================== short test summary info ============================",
        "FAILED tests/test_billing_discount.py::test_zero_month_discount_guard - ZeroDivisionError",
    ]
    return "\n".join(passing[:28] + core_failure + passing[28:])


class DemoShowcasePayload(BaseModel):
    sample_log: str
    sample_code: str
    prune_report: PrunedOutputReport
    skeleton_report: SkeletonReport
    session_report: SessionCompressionReport
    finops_flash_route: FinOpsRouteDecision
    finops_escalated_route: FinOpsRouteDecision


def build_demo_showcase(budget_tokens: int = 180) -> DemoShowcasePayload:
    sample_log = build_demo_pytest_log()
    prune_report = prune_tool_output(sample_log, budget_tokens=budget_tokens, halo_radius=2)
    skeleton_report = skeletonize_python_source(
        DEMO_PYTHON_MODULE, focus_symbols={"compute_monthly_discount"}, min_elide_lines=4
    )
    turns = [
        SessionTurnInput(
            turn_id=1,
            kind=TurnKind.READ_FILE,
            label="src/billing.py",
            content=DEMO_PYTHON_MODULE,
        ),
        SessionTurnInput(
            turn_id=2,
            kind=TurnKind.BASH_OUTPUT,
            label="pytest tests/",
            content=sample_log,
        ),
        SessionTurnInput(
            turn_id=3,
            kind=TurnKind.READ_FILE,
            label="src/billing.py (re-read before patch)",
            content=DEMO_PYTHON_MODULE,
        ),
        SessionTurnInput(
            turn_id=4,
            kind=TurnKind.PYTHON_CONTEXT,
            label="src/billing.py (AST focus: compute_monthly_discount)",
            content=DEMO_PYTHON_MODULE,
        ),
    ]
    session_report = compress_agent_session(
        turns,
        log_budget_tokens=budget_tokens,
        focus_symbols={"compute_monthly_discount"},
    )
    finops_flash = route_turn_finops(
        prompt_summary="Extract failing line from pytest log and guard discount_months == 0",
        context_tokens_raw=session_report.original_tokens,
        context_tokens_compressed=session_report.compressed_tokens,
        retry_count=0,
        requires_formal_or_security_proof=False,
        multi_file_count=1,
    )
    finops_escalated = route_turn_finops(
        prompt_summary="Verify cryptographic double-entry invariant across payment ledger",
        context_tokens_raw=session_report.original_tokens,
        context_tokens_compressed=session_report.compressed_tokens,
        retry_count=1,
        requires_formal_or_security_proof=True,
        multi_file_count=4,
    )
    return DemoShowcasePayload(
        sample_log=sample_log,
        sample_code=DEMO_PYTHON_MODULE,
        prune_report=prune_report,
        skeleton_report=skeleton_report,
        session_report=session_report,
        finops_flash_route=finops_flash,
        finops_escalated_route=finops_escalated,
    )

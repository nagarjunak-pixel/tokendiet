"""Unit and Hypothesis property tests for AST skeletonizer, log/session pruners & FinOps router."""

from __future__ import annotations

import ast

from hypothesis import given, settings
from hypothesis import strategies as st

from tokendiet.compressors import estimate_tokens
from tokendiet.compressors.ast_skeleton import skeletonize_python_source
from tokendiet.compressors.log_pruner import prune_tool_output
from tokendiet.compressors.session_pruner import compress_agent_session
from tokendiet.demo import build_demo_showcase
from tokendiet.router.finops_router import route_turn_finops
from tokendiet.types import ModelTier, SessionTurnInput, TurnKind


def test_estimate_tokens_empty() -> None:
    assert estimate_tokens("") == 0
    assert estimate_tokens("abcd") == 1


def test_skeletonizer_edge_cases_and_async_class() -> None:
    assert skeletonize_python_source("").original_tokens == 0
    bad = skeletonize_python_source("def broken(:\n  pass")
    assert bad.syntax_valid is False
    assert bad.elided_symbols == []

    src = '''"""Module docstring."""

async def short_fn() -> int:
    """Doc only."""
    return 1

def inline_fn() -> int: return 42

class Service:
    """Service docs."""

    def helper_long(self, x: int) -> int:
        """Elide this long body."""
        a = x + 1
        b = a * 2
        c = b - 3
        d = c + 4
        e = d * 5
        return e

    async def focus_buggy(self, x: int) -> int:
        a = x + 1
        b = a * 2
        c = b - 3
        d = c + 4
        e = d * 5
        return e
'''
    skel = skeletonize_python_source(src, focus_symbols={"Service.focus_buggy"}, min_elide_lines=4)
    assert skel.syntax_valid is True
    ast.parse(skel.compressed_source)
    assert "Service.helper_long" in skel.elided_symbols
    assert "Service.focus_buggy" in skel.preserved_symbols
    assert "def short_fn" in skel.compressed_source
    assert "def inline_fn" in skel.compressed_source
    assert skel.savings_pct > 0.0


@settings(max_examples=30, deadline=None)
@given(
    fn_count=st.integers(min_value=2, max_value=6), focus_idx=st.integers(min_value=0, max_value=5)
)
def test_skeletonizer_preserves_valid_ast_property(fn_count: int, focus_idx: int) -> None:
    focus_idx = focus_idx % fn_count
    blocks = ['"""Generated test module."""\n']
    for idx in range(fn_count):
        blocks.append(
            f"def func_{idx}(v: int) -> int:\n"
            f'    """Docstring {idx}."""\n'
            f"    x0 = v + {idx}\n"
            f"    x1 = x0 * 2\n"
            f"    x2 = x1 + 3\n"
            f"    x3 = x2 - 4\n"
            f"    x4 = x3 + 5\n"
            f"    return x4\n"
        )
    src = "\n".join(blocks)
    rep = skeletonize_python_source(src, focus_symbols={f"func_{focus_idx}"}, min_elide_lines=4)
    assert rep.syntax_valid is True
    ast.parse(rep.compressed_source)
    assert f"func_{focus_idx}" in rep.preserved_symbols
    assert len(rep.elided_symbols) == fn_count - 1


def test_log_pruner_empty_small_and_bloated() -> None:
    empty = prune_tool_output("   ")
    assert empty.total_lines == 0
    assert empty.anchor_retention_pct == 100.0

    small = prune_tool_output("INFO running step 1\nassert ok", budget_tokens=500)
    assert small.compressed_text == "INFO running step 1\nassert ok"
    assert small.omitted_lines == 0

    demo = build_demo_showcase(budget_tokens=180)
    assert demo.prune_report.savings_pct >= 50.0
    assert demo.prune_report.anchor_retention_pct == 100.0
    assert "ZeroDivisionError" in demo.prune_report.compressed_text
    assert "src/billing.py" in demo.prune_report.compressed_text


def test_session_pruner_and_finops_router() -> None:
    empty_sess = compress_agent_session([])
    assert empty_sess.turn_count == 0
    assert empty_sess.anchor_retention_pct == 100.0

    demo = build_demo_showcase()
    assert demo.session_report.dedup_blocks_replaced >= 1
    assert demo.session_report.savings_pct >= 50.0
    assert demo.session_report.estimated_frontier_usd_saved > 0.0

    # Balanced tier test (multi_file_count >= 3, no retry, no formal proof)
    balanced = route_turn_finops(
        prompt_summary="Refactor auth middleware across 3 routers",
        context_tokens_raw=2000,
        context_tokens_compressed=700,
        retry_count=0,
        requires_formal_or_security_proof=False,
        multi_file_count=3,
    )
    assert balanced.selected_tier == ModelTier.BALANCED_CODING
    assert balanced.cascade_escalated is False
    assert demo.finops_flash_route.selected_tier == ModelTier.LOCAL_FLASH
    assert demo.finops_escalated_route.selected_tier == ModelTier.FRONTIER_REASONING
    assert demo.finops_escalated_route.cascade_escalated is True

    # Ensure single-block READ_FILE without blank lines dedups too
    single_blk = "\n".join(f"line_{i} = {i * 2}" for i in range(12))
    turns = [
        SessionTurnInput(turn_id=1, kind=TurnKind.READ_FILE, label="cfg.py", content=single_blk),
        SessionTurnInput(turn_id=2, kind=TurnKind.READ_FILE, label="cfg.py", content=single_blk),
    ]
    sess = compress_agent_session(turns)
    assert sess.dedup_blocks_replaced == 1

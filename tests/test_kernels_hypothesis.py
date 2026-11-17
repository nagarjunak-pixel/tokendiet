"""Differential Hypothesis fuzzing: C++20 native kernel vs Python reference."""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from tokendiet.kernels.native_prune import (
    active_backend_name,
    dedup_blocks,
    python_dedup_blocks,
    python_salience_knapsack,
    salience_knapsack,
)


def test_native_kernel_compiled_on_host() -> None:
    assert "c++20-native" in active_backend_name()


def test_empty_and_zero_budget_edges() -> None:
    assert salience_knapsack([], [], [], [], 100, 2) == ([], 0, 0)
    assert salience_knapsack([5], [100], [1], [0], 0, 2) == ([], 0, 0)
    assert python_salience_knapsack([], [], [], [], 100, 2) == ([], 0, 0)
    assert dedup_blocks([], [], []) == ([], 0, 0)
    assert python_dedup_blocks([], [], []) == ([], 0, 0)


@settings(max_examples=80, deadline=None)
@given(
    n=st.integers(min_value=1, max_value=24),
    data=st.data(),
)
def test_salience_knapsack_cpp_python_parity(n: int, data: st.DataObject) -> None:
    costs = data.draw(st.lists(st.integers(min_value=1, max_value=28), min_size=n, max_size=n))
    scores = data.draw(st.lists(st.integers(min_value=0, max_value=1200), min_size=n, max_size=n))
    hashes = data.draw(st.lists(st.integers(min_value=1, max_value=12), min_size=n, max_size=n))
    mand = data.draw(st.lists(st.integers(min_value=0, max_value=1), min_size=n, max_size=n))
    budget = data.draw(st.integers(min_value=5, max_value=220))
    halo = data.draw(st.integers(min_value=0, max_value=3))

    cpp_res = salience_knapsack(costs, scores, hashes, mand, budget, halo)
    py_res = python_salience_knapsack(costs, scores, hashes, mand, budget, halo)

    assert cpp_res == py_res
    sel, kept_tok, _ = cpp_res
    assert sel == sorted(sel)
    assert len(set(sel)) == len(sel)
    assert kept_tok <= budget
    assert kept_tok == sum(costs[i] for i in sel)


def test_salience_knapsack_scaled_large_budget() -> None:
    costs = [3000, 3500, 3000, 1500]
    scores = [200, 1000, 100, 900]
    hashes = [11, 22, 33, 44]
    mand = [0, 1, 0, 1]
    budget = 9000
    cpp_res = salience_knapsack(costs, scores, hashes, mand, budget, 1)
    py_res = python_salience_knapsack(costs, scores, hashes, mand, budget, 1)
    assert cpp_res == py_res
    sel, kept_tok, _ = cpp_res
    assert kept_tok <= budget
    assert 1 in sel and 3 in sel


@settings(max_examples=80, deadline=None)
@given(
    n=st.integers(min_value=1, max_value=30),
    data=st.data(),
)
def test_dedup_blocks_cpp_python_parity(n: int, data: st.DataObject) -> None:
    hashes = data.draw(st.lists(st.integers(min_value=1, max_value=9), min_size=n, max_size=n))
    turns = data.draw(st.lists(st.integers(min_value=1, max_value=6), min_size=n, max_size=n))
    tokens = data.draw(st.lists(st.integers(min_value=8, max_value=300), min_size=n, max_size=n))

    cpp_res = dedup_blocks(hashes, turns, tokens)
    py_res = python_dedup_blocks(hashes, turns, tokens)
    assert cpp_res == py_res

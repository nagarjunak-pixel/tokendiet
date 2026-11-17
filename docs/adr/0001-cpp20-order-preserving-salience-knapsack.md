# ADR 0001: Native C++20 Order-Preserving Salience Knapsack Kernel

- **Status**: Accepted
- **Date**: 2026-11-17

## Context
Agent bash outputs (`pytest`, `tsc`, Docker builds, SQL migrations) routinely dump 200–2,000 lines of low-signal progress bars and passing boilerplate around 3–12 critical error/traceback anchor lines. Naive head/tail truncation frequently deletes mid-log tracebacks, while stochastic LLM summarizers add latency, non-determinism, and floating-point drift.

## Decision
Implement an exact, purely integer (`int32_t` / `int64_t` / `uint64_t`) `C++20` (`clang++ -O3`) kernel (`tokendiet_salience_knapsack`) with three deterministic stages:
1. **Windowed Non-Anchor Duplicate Suppression**: Drops non-anchor lines (`raw_scores[i] < 800`, `mandatory == 0`) whose 64-bit hash already appeared within the preceding 8 lines.
2. **Integer Anchor Halo Propagation**: Boosts context lines within `1 <= |i - a| <= halo_radius` of an anchor (`raw_scores[a] >= 800` or `mandatory == 1`) via exact floor division `raw_scores[a] / (1 + |i - a|)`, plus `1,000,000` mandatory priority weight.
3. **Exact Order-Preserving 0/1 Knapsack DP**: Solves backward 0/1 knapsack DP over scaled integer token weights so chronological line ordering is preserved strictly, earlier tie lines are favored deterministically, and C++20 vs Python reference parity is bit-exact under Hypothesis fuzzing.

## Consequences
- Sub-millisecond pruning on typical multi-hundred-line CLI logs.
- 100% anchor line retention whenever anchors fit within budget, and automatic pure-Python parity fallback when no C++ compiler is present.

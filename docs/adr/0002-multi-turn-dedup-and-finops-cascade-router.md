# ADR 0002: Multi-Turn Block Deduplication & FinOps Cascade Escalation Router

- **Status**: Accepted
- **Date**: 2026-11-17

## Context
Coding-agent costs compound across two axes simultaneously:
1. Re-reading unchanged files or full boilerplate implementations across turns inflates quadratic KV-cache / prompt token billing.
2. Routing every turn—including mechanical log extraction, formatting, or single-function fixes—to frontier reasoning models multiplies unit token price (`$15/1M` vs `$0.10/1M`).

## Decision
Combine three orthogonal layers:
1. **Cross-Turn Hash Deduplication (`tokendiet_dedup_blocks`)**: Native C++20 block-hash matcher replacing repeated `read_file` blocks from prior turns with compact `12`-token deterministic back-references (`[@tokendiet:ref turn=#T sha256=... tokens_saved=...]`).
2. **AST Skeletonization (`ast_skeleton.py`)**: Replaces bodies of unfocused Python functions spanning `>= min_elide_lines` with `pass  # [tokendiet: elided N lines sha256=...]`, always verified via `ast.parse` round-trip.
3. **Cascade Escalation Guard (`finops_router.py`)**: Routes mechanical tasks to `LOCAL_FLASH` (`$0.10/1M`), multi-file edits (`>= 3` files) to `BALANCED_CODING` (`$3.00/1M`), and immediately escalates to `FRONTIER_REASONING` (`$15.00/1M`) whenever `retry_count >= 1` or `requires_formal_or_security_proof=True`.

## Consequences
- Cuts both prompt token count and per-token unit rate while guaranteeing automatic frontier escalation on non-trivial retries or formal/security work.

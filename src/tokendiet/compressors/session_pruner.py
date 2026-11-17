"""Multi-turn coding-agent session compressor combining dedup, log pruning & AST skeletonization."""

from __future__ import annotations

from tokendiet.compressors import estimate_tokens
from tokendiet.compressors.ast_skeleton import skeletonize_python_source
from tokendiet.compressors.log_pruner import prune_tool_output
from tokendiet.kernels.native_prune import active_backend_name, dedup_blocks, hash_text_u64
from tokendiet.types import (
    SessionCompressionReport,
    SessionTurnInput,
    SessionTurnSummary,
    TurnKind,
)


def _split_blocks(text: str) -> list[str]:
    if "\n\n" in text:
        blocks = [b for b in text.split("\n\n") if b.strip()]
        if blocks:
            return blocks
    return [text] if text.strip() else []


def compress_agent_session(
    turns: list[SessionTurnInput],
    log_budget_tokens: int = 180,
    focus_symbols: set[str] | None = None,
) -> SessionCompressionReport:
    """Compress multi-turn coding agent history across repeated reads, CLI logs, and source files."""
    if not turns:
        return SessionCompressionReport(
            kernel_backend=active_backend_name(),
            turn_count=0,
            original_tokens=0,
            compressed_tokens=0,
            tokens_saved=0,
            savings_pct=0.0,
            dedup_blocks_replaced=0,
            anchor_retention_pct=100.0,
            estimated_frontier_usd_saved=0.0,
            turn_summaries=[],
        )

    # First index all eligible blocks in READ_FILE turns so C++20 kernel handles cross-turn dedup.
    block_hashes: list[int] = []
    block_turn_ids: list[int] = []
    block_tokens: list[int] = []
    block_meta: list[tuple[int, int, str, int, str]] = []  # (turn_idx, blk_idx, label, tok, text)
    read_turn_blocks: dict[int, list[str]] = {}

    for t_idx, turn in enumerate(turns):
        if turn.kind == TurnKind.READ_FILE:
            blocks = _split_blocks(turn.content)
            read_turn_blocks[t_idx] = blocks
            for b_idx, blk in enumerate(blocks):
                tok = estimate_tokens(blk)
                if tok >= 16:
                    block_hashes.append(hash_text_u64(blk.strip()))
                    block_turn_ids.append(turn.turn_id)
                    block_tokens.append(tok)
                    block_meta.append((t_idx, b_idx, turn.label, tok, blk))

    ref_indices, _, _ = dedup_blocks(block_hashes, block_turn_ids, block_tokens)
    replacement_map: dict[tuple[int, int], str] = {}
    turn_dedup_counts: dict[int, int] = {}

    for flat_idx, ref_idx in enumerate(ref_indices):
        if ref_idx >= 0:
            t_idx, b_idx, _, tok, blk = block_meta[flat_idx]
            orig_t_idx, _, orig_label, _, _ = block_meta[ref_idx]
            orig_turn_id = turns[orig_t_idx].turn_id
            saved_est = max(0, tok - 12)
            digest = f"{block_hashes[flat_idx]:016x}"[:8]
            replacement_map[(t_idx, b_idx)] = (
                f"[@tokendiet:ref turn=#{orig_turn_id} label={orig_label} "
                f"hash={digest} tokens_saved={saved_est}]"
            )
            turn_dedup_counts[t_idx] = turn_dedup_counts.get(t_idx, 0) + 1

    summaries: list[SessionTurnSummary] = []
    orig_total = 0
    comp_total = 0
    total_anchors = 0
    kept_anchors = 0
    total_dedups = 0

    for t_idx, turn in enumerate(turns):
        orig_tok = estimate_tokens(turn.content)
        dedups = turn_dedup_counts.get(t_idx, 0)
        total_dedups += dedups

        if turn.kind == TurnKind.READ_FILE:
            blocks = read_turn_blocks[t_idx]
            new_blocks = [
                replacement_map.get((t_idx, b_idx), blk) for b_idx, blk in enumerate(blocks)
            ]
            comp_text = "\n\n".join(new_blocks)
        elif turn.kind == TurnKind.BASH_OUTPUT:
            pruned = prune_tool_output(turn.content, budget_tokens=log_budget_tokens)
            comp_text = pruned.compressed_text
            total_anchors += pruned.total_anchors
            kept_anchors += pruned.kept_anchors
        else:
            skel = skeletonize_python_source(turn.content, focus_symbols=focus_symbols)
            comp_text = skel.compressed_source

        comp_tok = estimate_tokens(comp_text)
        turn_savings = round(max(0.0, (1.0 - comp_tok / max(1, orig_tok)) * 100.0), 2)
        orig_total += orig_tok
        comp_total += comp_tok
        summaries.append(
            SessionTurnSummary(
                turn_id=turn.turn_id,
                kind=turn.kind,
                label=turn.label,
                original_tokens=orig_tok,
                compressed_tokens=comp_tok,
                savings_pct=turn_savings,
                dedup_blocks_replaced=dedups,
                compressed_content=comp_text,
            )
        )

    tokens_saved = max(0, orig_total - comp_total)
    total_savings_pct = round(max(0.0, (1.0 - comp_total / max(1, orig_total)) * 100.0), 2)
    anchor_retention = (
        round((kept_anchors / total_anchors) * 100.0, 2) if total_anchors > 0 else 100.0
    )
    usd_saved = round(tokens_saved * 15.0 / 1_000_000.0, 6)

    return SessionCompressionReport(
        kernel_backend=active_backend_name(),
        turn_count=len(turns),
        original_tokens=orig_total,
        compressed_tokens=comp_total,
        tokens_saved=tokens_saved,
        savings_pct=total_savings_pct,
        dedup_blocks_replaced=total_dedups,
        anchor_retention_pct=anchor_retention,
        estimated_frontier_usd_saved=usd_saved,
        turn_summaries=summaries,
    )

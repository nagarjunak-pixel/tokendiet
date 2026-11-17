"""Native C++20 bridge (`clang++ -O3`) for Order-Preserving Salience Knapsack & Block Deduplication."""

from __future__ import annotations

import ctypes
import hashlib
import shutil
import subprocess
import tempfile
from pathlib import Path


def _compile_native_lib() -> tuple[ctypes.CDLL | None, str]:
    src_path = Path(__file__).resolve().parents[3] / "csrc" / "tokendiet_kernels.cpp"
    clang = shutil.which("clang++") or shutil.which("g++")
    if not src_path.exists() or clang is None:
        return None, "python-fallback"

    digest = hashlib.sha256(src_path.read_bytes()).hexdigest()[:16]
    out_dir = Path(tempfile.gettempdir()) / "tokendiet_native_cache"
    out_dir.mkdir(parents=True, exist_ok=True)
    ext = ".dylib" if Path("/System/Library").exists() else ".so"
    lib_path = out_dir / f"libtokendiet_kernels_{digest}{ext}"

    if not lib_path.exists():
        cmd = [clang, "-O3", "-std=c++20", "-shared", "-fPIC", str(src_path), "-o", str(lib_path)]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            return None, "python-fallback"

    lib = ctypes.CDLL(str(lib_path))
    lib.tokendiet_salience_knapsack.argtypes = [
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_uint64),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int64),
    ]
    lib.tokendiet_salience_knapsack.restype = ctypes.c_int32

    lib.tokendiet_dedup_blocks.argtypes = [
        ctypes.POINTER(ctypes.c_uint64),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.c_int32,
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
    ]
    lib.tokendiet_dedup_blocks.restype = ctypes.c_int32
    return lib, "c++20-native (clang++ -O3)"


_NATIVE_LIB, _BACKEND_NAME = _compile_native_lib()


def active_backend_name() -> str:
    return _BACKEND_NAME


def hash_text_u64(text: str) -> int:
    return int.from_bytes(hashlib.blake2b(text.encode("utf-8"), digest_size=8).digest(), "little")


def python_salience_knapsack(
    token_costs: list[int],
    raw_scores: list[int],
    line_hashes: list[int],
    mandatory_flags: list[int],
    budget_tokens: int,
    halo_radius: int = 2,
) -> tuple[list[int], int, int]:
    n = len(token_costs)
    if n <= 0 or budget_tokens <= 0:
        return [], 0, 0

    eff_halo = max(0, halo_radius)
    eligible = [True] * n
    for i in range(n):
        if mandatory_flags[i] == 0 and raw_scores[i] < 800:
            win_start = max(0, i - 8)
            for j in range(win_start, i):
                if line_hashes[j] == line_hashes[i]:
                    eligible[i] = False
                    break

    anchors = [i for i in range(n) if mandatory_flags[i] != 0 or raw_scores[i] >= 800]

    elig_indices: list[int] = []
    raw_costs: list[int] = []
    eff_scores: list[int] = []
    total_raw_cost = 0

    for i in range(n):
        if not eligible[i]:
            continue
        score = int(raw_scores[i])
        if eff_halo > 0:
            for a in anchors:
                dist = abs(i - a)
                if 1 <= dist <= eff_halo:
                    propagated = int(raw_scores[a]) // (1 + dist)
                    if propagated > score:
                        score = propagated
        if mandatory_flags[i] != 0:
            score += 1_000_000
        cost = max(1, int(token_costs[i]))
        elig_indices.append(i)
        raw_costs.append(cost)
        eff_scores.append(score)
        total_raw_cost += cost

    m = len(elig_indices)
    if m == 0:
        return [], 0, 0

    selected: list[int] = []
    kept_tokens = 0
    total_score = 0

    if total_raw_cost <= budget_tokens:
        for k in range(m):
            if eff_scores[k] >= 0:
                selected.append(elig_indices[k])
                kept_tokens += raw_costs[k]
                total_score += eff_scores[k]
        return selected, kept_tokens, total_score

    scale = ((budget_tokens + 8191) // 8192) if budget_tokens > 8192 else 1
    b_cap = budget_tokens // scale
    dp_costs = [(c + scale - 1) // scale for c in raw_costs]

    dp_next = [0] * (b_cap + 1)
    keep = [bytearray(b_cap + 1) for _ in range(m)]

    for k in range(m - 1, -1, -1):
        w = dp_costs[k]
        v = eff_scores[k]
        row_keep = keep[k]
        dp_curr = [0] * (b_cap + 1)
        for b in range(b_cap + 1):
            skip = dp_next[b]
            if b >= w:
                take = v + dp_next[b - w]
                if take >= skip:
                    dp_curr[b] = take
                    row_keep[b] = 1
                else:
                    dp_curr[b] = skip
            else:
                dp_curr[b] = skip
        dp_next = dp_curr

    rem = b_cap
    for k in range(m):
        w = dp_costs[k]
        if rem >= w and keep[k][rem]:
            selected.append(elig_indices[k])
            kept_tokens += raw_costs[k]
            total_score += eff_scores[k]
            rem -= w

    return selected, kept_tokens, total_score


def salience_knapsack(
    token_costs: list[int],
    raw_scores: list[int],
    line_hashes: list[int],
    mandatory_flags: list[int],
    budget_tokens: int,
    halo_radius: int = 2,
    *,
    force_python: bool = False,
) -> tuple[list[int], int, int]:
    if _NATIVE_LIB is None or force_python:
        return python_salience_knapsack(
            token_costs, raw_scores, line_hashes, mandatory_flags, budget_tokens, halo_radius
        )

    n = len(token_costs)
    if n <= 0 or budget_tokens <= 0:
        return [], 0, 0

    c_costs = (ctypes.c_int32 * n)(*(int(x) for x in token_costs))
    c_scores = (ctypes.c_int32 * n)(*(int(x) for x in raw_scores))
    c_hashes = (ctypes.c_uint64 * n)(*(int(x) & 0xFFFFFFFFFFFFFFFF for x in line_hashes))
    c_mand = (ctypes.c_int32 * n)(*(int(x) for x in mandatory_flags))
    out_idx = (ctypes.c_int32 * n)()
    out_cnt = ctypes.c_int32(0)
    out_kept = ctypes.c_int32(0)
    out_score = ctypes.c_int64(0)

    count = int(
        _NATIVE_LIB.tokendiet_salience_knapsack(
            c_costs,
            c_scores,
            c_hashes,
            c_mand,
            n,
            int(budget_tokens),
            int(halo_radius),
            out_idx,
            ctypes.byref(out_cnt),
            ctypes.byref(out_kept),
            ctypes.byref(out_score),
        )
    )
    return [int(out_idx[i]) for i in range(count)], int(out_kept.value), int(out_score.value)


def python_dedup_blocks(
    block_hashes: list[int],
    turn_ids: list[int],
    block_tokens: list[int],
) -> tuple[list[int], int, int]:
    n = len(block_hashes)
    if n <= 0:
        return [], 0, 0

    by_hash: dict[int, list[int]] = {}
    ref_indices = [-1] * n
    dedup_count = 0
    saved_tokens = 0

    for i in range(n):
        h = int(block_hashes[i]) & 0xFFFFFFFFFFFFFFFF
        matched = -1
        for j in by_hash.get(h, ()):
            if turn_ids[j] < turn_ids[i]:
                matched = j
                break
        ref_indices[i] = matched
        if matched >= 0:
            dedup_count += 1
            saved_tokens += max(0, int(block_tokens[i]) - 12)
        by_hash.setdefault(h, []).append(i)

    return ref_indices, dedup_count, saved_tokens


def dedup_blocks(
    block_hashes: list[int],
    turn_ids: list[int],
    block_tokens: list[int],
    *,
    force_python: bool = False,
) -> tuple[list[int], int, int]:
    if _NATIVE_LIB is None or force_python:
        return python_dedup_blocks(block_hashes, turn_ids, block_tokens)

    n = len(block_hashes)
    if n <= 0:
        return [], 0, 0

    c_hashes = (ctypes.c_uint64 * n)(*(int(x) & 0xFFFFFFFFFFFFFFFF for x in block_hashes))
    c_turns = (ctypes.c_int32 * n)(*(int(x) for x in turn_ids))
    c_tokens = (ctypes.c_int32 * n)(*(int(x) for x in block_tokens))
    out_refs = (ctypes.c_int32 * n)()
    out_saved = ctypes.c_int32(0)

    dedup_count = int(
        _NATIVE_LIB.tokendiet_dedup_blocks(
            c_hashes,
            c_turns,
            c_tokens,
            n,
            out_refs,
            ctypes.byref(out_saved),
        )
    )
    return [int(out_refs[i]) for i in range(n)], dedup_count, int(out_saved.value)

# tokendiet

[![TokenDiet CI](https://github.com/nagarjunak-pixel/tokendiet/actions/workflows/ci.yml/badge.svg)](https://github.com/nagarjunak-pixel/tokendiet/actions/workflows/ci.yml)
[![Release v1.0.0](https://img.shields.io/badge/release-v1.0.0-10b981)](https://github.com/nagarjunak-pixel/tokendiet/releases/tag/v1.0.0)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

**A context compressor for AI coding agents: order-preserving knapsack pruning of noisy tool logs (C++20 kernel with a pure-Python fallback), Python AST skeletonizing, cross-turn deduplication of repeated file reads, a rule-based model-tier router, and an MCP server.**

Coding agents spend a large share of their context window on noisy test-runner output, Docker build logs, unfocused helper code, and the same `read_file` payload repeated across turns. `tokendiet` trims that context deterministically before inference. Lines matching error-anchor patterns (tracebacks, `error TS…`, constraint violations, etc.) are always kept, and skeletonized Python is re-checked with `ast.parse`. It is a small, focused tool (~2k lines of Python plus a ~220-line C++20 kernel), not a learned compressor.

---

![tokendiet Workbench UI](docs/assets/workbench-preview.png)

## Architecture

```mermaid
flowchart LR
    Raw["Raw Agent Context<br/>(pytest/tsc/docker logs · Python files · multi-turn reads)"] --> Split{"Tool / Turn Classifier"}
    Split -->|CLI / Test Log| CppKnapsack["C++20 Salience Knapsack<br/>(clang++ -O3 · integer halo DP)"]
    Split -->|Python Source| ASTSkel["Python AST Skeletonizer<br/>(ast.parse-verified stub elision)"]
    Split -->|Repeated Read| CppDedup["C++20 Cross-Turn Block Dedup<br/>([@tokendiet:ref] back-pointers)"]
    CppKnapsack --> Diet["Compressed Context<br/>(100% anchor retention)"]
    ASTSkel --> Diet
    CppDedup --> Diet
    Diet --> Router["FinOps Cascade Router<br/>(Local Flash -> Balanced -> Frontier Guard)"]
    Diet --> MCP["MCP stdio Server (.mcp.json)<br/>& FastAPI + React Workbench (:8110)"]
```

---

## Measured Verification & Benchmarks

All checks ran cleanly on local hardware (`Python 3.13.9`, `clang++ -O3` C++20, `Ollama qwen3.5:4b`):

| Verification Suite | Exact Measured Result |
| :--- | :--- |
| **Static Quality Gates** | `0` Ruff format issues · `0` Ruff lint issues · `0` Mypy `--strict` errors (`21` files) |
| **Pytest + Hypothesis Suite** | **`14 passed` · `97.72%` statement coverage** (differential C++20 vs Python parity across random budgets & turn IDs) |
| **Live `qwen3.5:4b` Audit (`6` tasks)** | **`100.0%` (`6/6`) verified accuracy preserved** · `6,487 -> 1,930` prompt tokens (**`70.25%` reduction**) · **`53.98%` faster end-to-end latency** |
| **`tokendiet demo` (Pytest Log Knapsack)** | `996 -> 213` tokens (**`78.61%` saved**) · `4/4` (`100.0%`) mandatory error anchors kept |
| **`tokendiet demo` (AST Skeletonizer)** | `431 -> 275` tokens (**`36.19%` saved**) · `3` helper functions elided · `ast.parse=True` |
| **`tokendiet demo` (Multi-Turn Session)** | `2,289 -> 1,047` tokens (**`54.26%` saved**) · `5` repeated blocks deduplicated |
| **FinOps Cascade Routing** | Single-unit bugfix routed to `local_flash` (**`99.69%` cost reduction**); retry/formal ledger proof escalated to `frontier_reasoning` |

### Live Ollama (`qwen3.5:4b`) Task Breakdown

Full artifact: [`benchmarks/real_qwen_tokendiet.json`](benchmarks/real_qwen_tokendiet.json)

| Task | Mode | Raw Prompt Tok | Diet Prompt Tok | Token Saved | Latency (Raw → Diet) | Verified |
| :--- | :--- | ---: | ---: | ---: | ---: | :---: |
| `TD-01` Pytest `ZeroDivisionError` | `log_prune` | 1,621 | 312 | **80.75%** | `2970.21ms -> 664.01ms` | PASS → PASS |
| `TD-02` TypeScript `TS2345` Build | `log_prune` | 1,328 | 283 | **78.69%** | `1002.64ms -> 539.67ms` | PASS → PASS |
| `TD-03` Multi-Turn Read + `TimeoutError` | `session_dedup` | 823 | 525 | **36.21%** | `718.44ms -> 615.84ms` | PASS → PASS |
| `TD-04` Python AST Focus Diagnosis | `ast_skeleton` | 358 | 285 | **20.39%** | `624.75ms -> 528.38ms` | PASS → PASS |
| `TD-05` Docker `ModuleNotFoundError` | `log_prune` | 1,270 | 284 | **77.64%** | `1024.04ms -> 552.53ms` | PASS → PASS |
| `TD-06` Postgres `CheckViolationError` | `log_prune` | 1,087 | 241 | **77.83%** | `792.12ms -> 382.16ms` | PASS → PASS |

## Scope & Limitations

- **Token counts are estimates.** The compressors budget with a `ceil(len(text) / 4)` character heuristic, not a real tokenizer; the live-audit token numbers come from Ollama's `prompt_eval_count` for `qwen3.5:4b` and will differ for other models' tokenizers.
- **Small, self-constructed benchmark.** The live audit is 6 hand-built tasks (synthetic pytest/tsc/Docker/Postgres logs and code) run once at temperature 0 on a local 4B model. "Verified" means the answer contains required keyword groups (e.g. file name and line number), not a human or model-graded judgement. Latency numbers are single runs on one laptop.
- **Heuristic salience.** Line scores come from hand-written regex patterns (tracebacks, `error TS…`, `E   ` lines, diff hunks, etc.). Log formats the patterns do not recognise can lose useful context; tune the budget conservatively.
- **Python-only skeletonizer.** AST skeletons are implemented for Python source only; other languages pass through the log pruner or untouched.
- **Router is rule-based.** The cascade router uses keyword hints, retry count and file count with fixed illustrative per-million-token prices; its "cost reduction" figure is relative to those assumed prices, not a measured bill.

## Install

```bash
# From PyPI (once published)
pip install tokendiet

# From source (today)
git clone https://github.com/nagarjunak-pixel/tokendiet.git && cd tokendiet
uv sync --all-extras        # or: pip install .
```

The C++20 kernel source ships inside the package and is compiled on first import with `clang++` or `g++` (cached in your temp dir). If no compiler is available, `tokendiet` falls back to an equivalent pure-Python implementation; `tokendiet demo` prints which backend is active. The React workbench (`tokendiet serve`) and the recorded benchmark replay need a source checkout.

---

## Quickstart

### 1. Install & Run Showcase
```bash
uv sync --all-extras
uv run tokendiet demo
```

### 2. Pipe Bloated Logs or Skeletonize Python Files
```bash
# Prune noisy pytest/tsc/docker output down to a 180-token salience budget
pytest -v 2>&1 | uv run tokendiet prune --budget 180

# Skeletonize unfocused functions while keeping focus symbols intact
uv run tokendiet skeleton src/billing.py --focus compute_monthly_discount
```

### 3. Drop-In Claude Code / Cursor MCP Server (`.mcp.json`)
```json
{
  "mcpServers": {
    "tokendiet": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/tokendiet", "tokendiet", "mcp-stdio"]
    }
  }
}
```

Exposed MCP tools:
- `tokendiet_prune_tool_output`
- `tokendiet_skeletonize_code`
- `tokendiet_compress_session`
- `tokendiet_route_finops`

### 4. Interactive Workbench & Live Ollama Re-Audit
```bash
cd ui && npm install && npm run build && cd ..
uv run tokendiet eval-ollama --live-only
uv run tokendiet serve --host 127.0.0.1 --port 8110
```

---

## Why the Native `C++20` Kernel Matters

Implemented in [`src/tokendiet/_csrc/tokendiet_kernels.cpp`](src/tokendiet/_csrc/tokendiet_kernels.cpp) and automatically compiled via `clang++ -O3` (with automatic pure-Python integer parity fallback):
1. **Windowed Non-Anchor Duplicate Suppression**: Drops repetitive non-anchor boilerplate whose hash appeared in the preceding 8 lines.
2. **Integer Anchor Halo Propagation**: Uses pure `int64_t` division `raw_score / (1 + distance)` to keep traceback frames and nearby failure context intact.
3. **Exact Order-Preserving 0/1 Knapsack DP**: Guarantees selected lines preserve original chronological ordering and respect token budgets without floating-point drift (see [ADR 0001](docs/adr/0001-cpp20-order-preserving-salience-knapsack.md) and [ADR 0002](docs/adr/0002-multi-turn-dedup-and-finops-cascade-router.md)).

---

## Author & Enterprise AI Architecture Hub
Built by **[Nagarjuna Reddy Kamireddy](https://nagarjunak-pixel.github.io/)** (*Nagarjuna Kamireddy / Nagarjuna K*) — Lead AI Architect, GenAI & Agentic AI Lead, and Corporate AI Trainer (20+ years across Enterprise Data, SAP HANA & Production AI; AWS Certified Solutions Architect – Professional & NVIDIA-Certified Professional: Agentic AI).

- **Official Portfolio & Architecture Hub:** [https://nagarjunak-pixel.github.io/](https://nagarjunak-pixel.github.io/)
- **Enterprise Case Studies & Technical Articles:** [Case Studies](https://nagarjunak-pixel.github.io/case-studies.html) · [Architecture Articles](https://nagarjunak-pixel.github.io/articles.html) · [10-Mandate Role Fit](https://nagarjunak-pixel.github.io/roles.html)
- **Master CV & AI Search Index:** [Master CV](https://nagarjunak-pixel.github.io/resume.html) · [`llms-full.txt`](https://nagarjunak-pixel.github.io/llms-full.txt) · [LinkedIn](https://www.linkedin.com/in/nagarjuna-kamireddy)

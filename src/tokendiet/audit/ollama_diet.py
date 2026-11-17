"""Live local Ollama (`qwen3.5:4b`) benchmark comparing Raw Bloated vs tokendiet-Compressed Contexts."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import httpx

from tokendiet.compressors.ast_skeleton import skeletonize_python_source
from tokendiet.compressors.log_pruner import prune_tool_output
from tokendiet.compressors.session_pruner import compress_agent_session
from tokendiet.types import (
    DietBenchmarkTask,
    RealDietAuditReport,
    SessionTurnInput,
    TurnKind,
)


def default_diet_audit_path() -> Path:
    return Path(__file__).resolve().parents[3] / "benchmarks" / "real_qwen_tokendiet.json"


@dataclass(frozen=True)
class _BenchmarkSpec:
    task_id: str
    title: str
    mode: str
    question: str
    raw_context: str
    diet_context: str
    required_groups: tuple[tuple[str, ...], ...]


def _build_benchmark_specs() -> list[_BenchmarkSpec]:
    # TD-01: Python pytest noise around billing.py:142 ZeroDivisionError
    py_noise_a = [
        f"tests/suite_{i:02d}.py::test_invoice_{i:02d} PASSED [{min(99, i + 10):3d}%]"
        for i in range(1, 35)
    ]
    py_err = [
        "Traceback (most recent call last):",
        '  File "src/billing.py", line 142, in compute_monthly_discount',
        "    return annual_cents // discount_months",
        "ZeroDivisionError: integer division or modulo by zero",
        "FAILED tests/test_billing.py::test_zero_discount - ZeroDivisionError",
    ]
    td01_raw = "\n".join(py_noise_a + py_err + py_noise_a)
    td01_diet = prune_tool_output(td01_raw, budget_tokens=160, halo_radius=2).compressed_text

    # TD-02: TypeScript npm/tsc build noise around session.ts TS2345
    ts_noise = [
        f"vite v6.0.5 transforming module src/components/Widget_{i:02d}.tsx ... OK"
        for i in range(1, 36)
    ]
    ts_err = [
        "src/auth/session.ts(88,19): error TS2345: Argument of type 'string | undefined' is not assignable to parameter of type 'string'.",
        "npm ERR! code ELIFECYCLE tsc exited with error code 2",
    ]
    td02_raw = "\n".join(ts_noise + ts_err + ts_noise[:20])
    td02_diet = prune_tool_output(td02_raw, budget_tokens=160, halo_radius=2).compressed_text

    # TD-03: Multi-turn repeated read_file + bash traceback on retry_policy.py
    retry_file = "\n\n".join(
        [
            "class RetryConfig:\n    max_attempts: int = 4\n    base_delay_ms: int = 120\n    backoff_factor: float = 2.0",
            "def compute_delay(attempt: int, base_delay_ms: int, jitter_ms: int) -> int:\n    delay = base_delay_ms * (2 ** attempt) + jitter_ms\n    if delay > 30000:\n        raise TimeoutError('exceeded max retry window')\n    return delay",
            "def summarize_attempts(history: list[int]) -> dict[str, int]:\n    total = sum(history)\n    count = len(history)\n    return {'total_ms': total, 'count': count}",
        ]
    )
    td03_turns = [
        SessionTurnInput(
            turn_id=1, kind=TurnKind.READ_FILE, label="src/retry_policy.py", content=retry_file
        ),
        SessionTurnInput(
            turn_id=2,
            kind=TurnKind.BASH_OUTPUT,
            label="pytest tests/test_retry.py",
            content="\n".join(
                [f"tests/test_net_{i:02d}.py PASSED" for i in range(1, 40)]
                + [
                    "Traceback (most recent call last):",
                    '  File "src/retry_policy.py", line 67, in compute_delay',
                    "    raise TimeoutError('exceeded max retry window')",
                    "TimeoutError: exceeded max retry window",
                ]
            ),
        ),
        SessionTurnInput(
            turn_id=3,
            kind=TurnKind.READ_FILE,
            label="src/retry_policy.py (re-read)",
            content=retry_file,
        ),
    ]
    td03_raw = "\n\n".join(f"[{t.label}]\n{t.content}" for t in td03_turns)
    td03_sess = compress_agent_session(td03_turns, log_budget_tokens=140)
    td03_diet = "\n\n".join(
        f"[{s.label}]\n{s.compressed_content}" for s in td03_sess.turn_summaries
    )

    # TD-04: Python AST skeletonization preserving buggy focus function
    pricing_src = '''"""Revenue and margin calculators."""

def clean_sku(raw: str) -> str:
    """Normalize SKU string."""
    step1 = raw.strip().upper()
    step2 = step1.replace(" ", "-")
    step3 = step2.replace("_", "-")
    return step3[:64]

def convert_fx(amount: float, rate: float) -> float:
    """Convert foreign currency."""
    scaled = round(amount * rate, 4)
    clamped = max(0.0, scaled)
    tax = clamped * 0.05
    return round(clamped + tax, 2)

def apply_tier_rebate(spend: float, tier: str) -> float:
    """Compute enterprise rebate."""
    weights = {"bronze": 0.02, "silver": 0.05, "gold": 0.09}
    factor = weights.get(tier.lower(), 0.0)
    rebate = spend * factor
    return round(rebate, 2)

def compute_net_margin(revenue: float, total_cost: float) -> float:
    """Return net profit margin percentage."""
    profit = revenue - total_cost
    # BUG: denominator should be revenue, not total_cost
    return (profit / total_cost) * 100.0
'''
    td04_raw = pricing_src
    td04_diet = skeletonize_python_source(
        pricing_src, focus_symbols={"compute_net_margin"}, min_elide_lines=4
    ).compressed_source

    # TD-05: Docker build log with cached layers around ModuleNotFoundError
    docker_noise = [
        f"#{i} CACHED [builder {i}/40] RUN pip wheel --no-deps pkg_{i:02d}" for i in range(1, 46)
    ]
    docker_err = [
        '#47 ERROR: process "/bin/sh -c python -m app.main" did not complete successfully: exit code: 1',
        '  File "src/config.py", line 12, in <module>',
        "ModuleNotFoundError: No module named 'pydantic_settings'",
    ]
    td05_raw = "\n".join(docker_noise + docker_err)
    td05_diet = prune_tool_output(td05_raw, budget_tokens=140, halo_radius=2).compressed_text

    # TD-06: Alembic/PostgreSQL migration output with constraint failure
    db_noise = [
        f"INFO  [alembic.runtime.migration] Running step 00{i:02d}_table_{i:02d} ... ok"
        for i in range(1, 42)
    ]
    db_err = [
        'asyncpg.exceptions.CheckViolationError: new row for relation "orders" violates check constraint "chk_positive_qty"',
        "DETAIL:  Failing row contains (ord_991, 0).",
    ]
    td06_raw = "\n".join(db_noise + db_err)
    td06_diet = prune_tool_output(td06_raw, budget_tokens=140, halo_radius=2).compressed_text

    return [
        _BenchmarkSpec(
            task_id="TD-01",
            title="Pytest ZeroDivisionError Isolation",
            mode="log_prune",
            question="In one concise sentence, name the failing file, line number, and exception class.",
            raw_context=td01_raw,
            diet_context=td01_diet,
            required_groups=(("billing.py",), ("142",), ("zerodivisionerror",)),
        ),
        _BenchmarkSpec(
            task_id="TD-02",
            title="TypeScript TS2345 Build Error Extraction",
            mode="log_prune",
            question="In one concise sentence, name the TypeScript file, line number, and TS error code.",
            raw_context=td02_raw,
            diet_context=td02_diet,
            required_groups=(("session.ts",), ("88",), ("ts2345",)),
        ),
        _BenchmarkSpec(
            task_id="TD-03",
            title="Multi-Turn Repeated File Read + TimeoutError",
            mode="session_dedup",
            question="In one concise sentence, name the file, line number, and raised exception in the agent trace.",
            raw_context=td03_raw,
            diet_context=td03_diet,
            required_groups=(("retry_policy.py",), ("67",), ("timeouterror",)),
        ),
        _BenchmarkSpec(
            task_id="TD-04",
            title="Python AST Skeleton Focus Bug Diagnosis",
            mode="ast_skeleton",
            question="In one concise sentence, name the buggy function and which variable is wrongly used as the denominator.",
            raw_context=td04_raw,
            diet_context=td04_diet,
            required_groups=(("compute_net_margin",), ("total_cost",)),
        ),
        _BenchmarkSpec(
            task_id="TD-05",
            title="Docker Cached Layer ModuleNotFoundError",
            mode="log_prune",
            question="In one concise sentence, name the failing file and exact missing Python module.",
            raw_context=td05_raw,
            diet_context=td05_diet,
            required_groups=(("config.py",), ("pydantic_settings",)),
        ),
        _BenchmarkSpec(
            task_id="TD-06",
            title="PostgreSQL Migration CheckViolationError",
            mode="log_prune",
            question="In one concise sentence, name the table (relation) and violated check constraint name.",
            raw_context=td06_raw,
            diet_context=td06_diet,
            required_groups=(("orders",), ("chk_positive_qty",)),
        ),
    ]


def _verify_answer(answer: str, groups: tuple[tuple[str, ...], ...]) -> bool:
    low = answer.lower()
    return all(any(tok.lower() in low for tok in grp) for grp in groups)


def _call_ollama_chat(
    base_url: str, model: str, question: str, context: str
) -> tuple[str, int, float]:
    payload = {
        "model": model,
        "stream": False,
        "think": False,
        "options": {"temperature": 0.0, "num_predict": 96},
        "messages": [
            {
                "role": "system",
                "content": "You are a concise principal software debugger. Cite exact identifiers, files, line numbers, and constraints verbatim.",
            },
            {
                "role": "user",
                "content": f"Context:\n{context}\n\nTask: {question}",
            },
        ],
    }
    t0 = time.perf_counter()
    resp = httpx.post(f"{base_url.rstrip('/')}/api/chat", json=payload, timeout=120.0)
    resp.raise_for_status()
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    body = resp.json()
    text = str(body.get("message", {}).get("content", "")).strip()
    prompt_tokens = int(body.get("prompt_eval_count") or max(1, len(context) // 4))
    return text, prompt_tokens, round(elapsed_ms, 2)


def run_real_diet_ollama_audit(
    *,
    model: str = "qwen3.5:4b",
    base_url: str = "http://127.0.0.1:11434",
    allow_offline_replay: bool = False,
    output_path: Path | None = None,
) -> RealDietAuditReport:
    """Benchmark Raw Bloated Context vs tokendiet-Compressed Context on local Ollama."""
    target_path = output_path or default_diet_audit_path()
    specs = _build_benchmark_specs()

    try:
        tasks: list[DietBenchmarkTask] = []
        for spec in specs:
            raw_ans, raw_tok, raw_ms = _call_ollama_chat(
                base_url, model, spec.question, spec.raw_context
            )
            diet_ans, diet_tok, diet_ms = _call_ollama_chat(
                base_url, model, spec.question, spec.diet_context
            )
            savings = round(max(0.0, (1.0 - diet_tok / max(1, raw_tok)) * 100.0), 2)
            tasks.append(
                DietBenchmarkTask(
                    task_id=spec.task_id,
                    title=spec.title,
                    mode=spec.mode,
                    raw_prompt_tokens=raw_tok,
                    diet_prompt_tokens=diet_tok,
                    prompt_token_savings_pct=savings,
                    raw_latency_ms=raw_ms,
                    diet_latency_ms=diet_ms,
                    raw_verified=_verify_answer(raw_ans, spec.required_groups),
                    diet_verified=_verify_answer(diet_ans, spec.required_groups),
                    raw_answer=raw_ans,
                    diet_answer=diet_ans,
                )
            )
        execution_mode = "live-ollama"
    except Exception:
        if not allow_offline_replay or not target_path.exists():
            raise
        cached = RealDietAuditReport.model_validate_json(target_path.read_text(encoding="utf-8"))
        cached.execution_mode = "recorded-artifact-replay"
        return cached

    n = len(tasks)
    raw_ok = sum(1 for t in tasks if t.raw_verified)
    diet_ok = sum(1 for t in tasks if t.diet_verified)
    tot_raw = sum(t.raw_prompt_tokens for t in tasks)
    tot_diet = sum(t.diet_prompt_tokens for t in tasks)
    tot_raw_ms = sum(t.raw_latency_ms for t in tasks)
    tot_diet_ms = sum(t.diet_latency_ms for t in tasks)

    report = RealDietAuditReport(
        model=model,
        execution_mode=execution_mode,
        total_tasks=n,
        raw_verified_pct=round((raw_ok / max(1, n)) * 100.0, 2),
        diet_verified_pct=round((diet_ok / max(1, n)) * 100.0, 2),
        avg_prompt_token_savings_pct=round(max(0.0, (1.0 - tot_diet / max(1, tot_raw)) * 100.0), 2),
        avg_latency_speedup_pct=round(
            max(0.0, (1.0 - tot_diet_ms / max(1e-6, tot_raw_ms)) * 100.0), 2
        ),
        total_raw_prompt_tokens=tot_raw,
        total_diet_prompt_tokens=tot_diet,
        tasks=tasks,
    )
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return report

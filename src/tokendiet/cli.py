"""Rich Typer CLI for tokendiet: demo, prune, skeleton, eval-ollama, mcp-stdio, and serve."""

from __future__ import annotations

import sys
from pathlib import Path

import typer
import uvicorn
from rich.console import Console
from rich.table import Table

from tokendiet.api.app import create_app
from tokendiet.audit.ollama_diet import run_real_diet_ollama_audit
from tokendiet.compressors.ast_skeleton import skeletonize_python_source
from tokendiet.compressors.log_pruner import prune_tool_output
from tokendiet.demo import build_demo_showcase
from tokendiet.kernels.native_prune import active_backend_name
from tokendiet.mcp.server import TokenDietMCPServer

app = typer.Typer(
    name="tokendiet",
    help="Native C++20 Agent Context Compressor, AST Skeletonizer, FinOps Router & MCP Server.",
    add_completion=False,
)
console = Console()


@app.command()
def demo(budget_tokens: int = typer.Option(180, "--budget", "-b")) -> None:
    """Run an end-to-end compression, deduplication & FinOps routing showcase."""
    payload = build_demo_showcase(budget_tokens=budget_tokens)
    console.print(f"[bold cyan]tokendiet v1.0.0[/] | Kernel: [green]{active_backend_name()}[/]")

    tbl = Table(title="Context Compression & FinOps Summary")
    tbl.add_column("Stage")
    tbl.add_column("Original Tokens", justify="right")
    tbl.add_column("Compressed Tokens", justify="right")
    tbl.add_column("Savings", justify="right")
    tbl.add_column("Invariant")
    tbl.add_row(
        "CLI / Pytest Log Knapsack",
        str(payload.prune_report.original_tokens),
        str(payload.prune_report.compressed_tokens),
        f"{payload.prune_report.savings_pct:.2f}%",
        f"Anchors {payload.prune_report.kept_anchors}/{payload.prune_report.total_anchors} ({payload.prune_report.anchor_retention_pct:.1f}%)",
    )
    tbl.add_row(
        "Python AST Skeletonizer",
        str(payload.skeleton_report.original_tokens),
        str(payload.skeleton_report.compressed_tokens),
        f"{payload.skeleton_report.savings_pct:.2f}%",
        f"ast.parse={payload.skeleton_report.syntax_valid} | Elided {len(payload.skeleton_report.elided_symbols)} fns",
    )
    tbl.add_row(
        "Multi-Turn Session",
        str(payload.session_report.original_tokens),
        str(payload.session_report.compressed_tokens),
        f"{payload.session_report.savings_pct:.2f}%",
        f"Dedup={payload.session_report.dedup_blocks_replaced} blocks | USD saved=${payload.session_report.estimated_frontier_usd_saved:.5f}",
    )
    console.print(tbl)
    console.print(
        f"[bold green]FinOps Flash Route:[/] {payload.finops_flash_route.selected_tier.value} "
        f"({payload.finops_flash_route.cost_reduction_pct:.2f}% cost reduction)"
    )
    console.print(
        f"[bold yellow]Cascade Guard Route:[/] {payload.finops_escalated_route.selected_tier.value} "
        f"(escalated={payload.finops_escalated_route.cascade_escalated})"
    )


@app.command()
def prune(
    file: Path | None = typer.Argument(None, help="Log file to prune (defaults to stdin)."),
    budget: int = typer.Option(180, "--budget", "-b"),
    halo: int = typer.Option(2, "--halo"),
) -> None:
    """Prune noisy CLI/test output from a file or stdin while preserving error anchors."""
    raw = file.read_text(encoding="utf-8") if file is not None else sys.stdin.read()
    report = prune_tool_output(raw, budget_tokens=budget, halo_radius=halo)
    typer.echo(report.compressed_text)


@app.command()
def skeleton(
    file: Path = typer.Argument(..., help="Python file to AST-skeletonize."),
    focus: str = typer.Option("", "--focus", "-f", help="Comma-separated focus symbol names."),
    min_elide_lines: int = typer.Option(5, "--min-lines"),
) -> None:
    """AST-skeletonize a Python source file while preserving signatures, docstrings & focus code."""
    focus_set = {s.strip() for s in focus.split(",") if s.strip()} or None
    report = skeletonize_python_source(
        file.read_text(encoding="utf-8"), focus_symbols=focus_set, min_elide_lines=min_elide_lines
    )
    typer.echo(report.compressed_source)


@app.command("eval-ollama")
def eval_ollama(
    model: str = typer.Option("qwen3.5:4b", "--model"),
    base_url: str = typer.Option("http://127.0.0.1:11434", "--base-url"),
    live_only: bool = typer.Option(False, "--live-only"),
) -> None:
    """Run live 6-task Raw vs tokendiet benchmark against local Ollama."""
    report = run_real_diet_ollama_audit(
        model=model, base_url=base_url, allow_offline_replay=not live_only
    )
    tbl = Table(title=f"Live Ollama Audit ({report.model} | {report.execution_mode})")
    tbl.add_column("Task")
    tbl.add_column("Mode")
    tbl.add_column("Raw Tok", justify="right")
    tbl.add_column("Diet Tok", justify="right")
    tbl.add_column("Saved %", justify="right")
    tbl.add_column("Verified (Raw -> Diet)")
    for t in report.tasks:
        tbl.add_row(
            f"{t.task_id}: {t.title}",
            t.mode,
            str(t.raw_prompt_tokens),
            str(t.diet_prompt_tokens),
            f"{t.prompt_token_savings_pct:.2f}%",
            f"{t.raw_verified} -> {t.diet_verified}",
        )
    console.print(tbl)
    console.print(
        f"[bold green]Summary:[/] Raw={report.raw_verified_pct:.1f}% -> Diet={report.diet_verified_pct:.1f}% | "
        f"Prompt Token Savings={report.avg_prompt_token_savings_pct:.2f}% | "
        f"Latency Speedup={report.avg_latency_speedup_pct:.2f}%"
    )


@app.command("mcp-stdio")
def mcp_stdio() -> None:
    """Start the zero-dependency JSON-RPC 2.0 MCP server over stdio."""
    TokenDietMCPServer().serve_streams()


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8110, "--port"),
) -> None:
    """Launch the tokendiet FastAPI + React/TS Workbench server."""
    uvicorn.run(create_app(), host=host, port=port, log_level="info")

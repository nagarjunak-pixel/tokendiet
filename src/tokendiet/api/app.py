"""FastAPI backend serving tokendiet compression APIs, FinOps router, Ollama audit & SPA UI."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from tokendiet.audit.ollama_diet import default_diet_audit_path, run_real_diet_ollama_audit
from tokendiet.compressors.ast_skeleton import skeletonize_python_source
from tokendiet.compressors.log_pruner import prune_tool_output
from tokendiet.demo import DemoShowcasePayload, build_demo_showcase
from tokendiet.kernels.native_prune import active_backend_name
from tokendiet.router.finops_router import route_turn_finops
from tokendiet.types import (
    FinOpsRouteDecision,
    PrunedOutputReport,
    RealDietAuditReport,
    SkeletonReport,
)


class PruneRequest(BaseModel):
    text: str
    budget_tokens: int = 180
    halo_radius: int = 2


class SkeletonRequest(BaseModel):
    source: str
    focus_symbols: list[str] = Field(default_factory=list)
    min_elide_lines: int = 5


class RouteRequest(BaseModel):
    prompt_summary: str
    context_tokens_raw: int
    context_tokens_compressed: int
    retry_count: int = 0
    requires_formal_or_security_proof: bool = False
    multi_file_count: int = 1


def create_app() -> FastAPI:
    app = FastAPI(
        title="tokendiet — C++20 Agent Context Pruner, AST Skeletonizer, FinOps Router & MCP Server",
        version="1.0.0",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/v1/health")
    def health() -> dict[str, str]:
        return {
            "status": "ok",
            "service": "tokendiet",
            "version": "1.0.0",
            "kernel_backend": active_backend_name(),
        }

    @app.get("/api/v1/demo", response_model=DemoShowcasePayload)
    def api_demo(budget_tokens: int = 180) -> DemoShowcasePayload:
        return build_demo_showcase(budget_tokens=budget_tokens)

    @app.post("/api/v1/prune", response_model=PrunedOutputReport)
    def api_prune(req: PruneRequest) -> PrunedOutputReport:
        return prune_tool_output(
            req.text, budget_tokens=req.budget_tokens, halo_radius=req.halo_radius
        )

    @app.post("/api/v1/skeleton", response_model=SkeletonReport)
    def api_skeleton(req: SkeletonRequest) -> SkeletonReport:
        return skeletonize_python_source(
            req.source,
            focus_symbols=set(req.focus_symbols) or None,
            min_elide_lines=req.min_elide_lines,
        )

    @app.post("/api/v1/route", response_model=FinOpsRouteDecision)
    def api_route(req: RouteRequest) -> FinOpsRouteDecision:
        return route_turn_finops(
            prompt_summary=req.prompt_summary,
            context_tokens_raw=req.context_tokens_raw,
            context_tokens_compressed=req.context_tokens_compressed,
            retry_count=req.retry_count,
            requires_formal_or_security_proof=req.requires_formal_or_security_proof,
            multi_file_count=req.multi_file_count,
        )

    @app.get("/api/v1/audit/ollama", response_model=RealDietAuditReport)
    def api_audit_ollama(refresh: bool = False) -> RealDietAuditReport:
        art = default_diet_audit_path()
        if not refresh and art.exists():
            return RealDietAuditReport.model_validate_json(art.read_text(encoding="utf-8"))
        return run_real_diet_ollama_audit(allow_offline_replay=True)

    ui_dist = Path(__file__).resolve().parents[3] / "ui" / "dist"
    assets_dir = ui_dist / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/", response_model=None)
    def serve_spa() -> FileResponse | HTMLResponse:
        index_html = ui_dist / "index.html"
        if index_html.exists():
            return FileResponse(str(index_html))
        return HTMLResponse(
            "<h1>tokendiet API Online</h1><p>Build UI via <code>cd ui && npm run build</code>.</p>"
        )

    return app

"""Zero-Dependency JSON-RPC 2.0 Model Context Protocol (`MCP`) Server for Claude Code / Cursor.

Exposes 4 agent-ready tools over stdio (`tokendiet mcp-stdio`) and in-process RPC:
- `tokendiet_prune_tool_output`: Run C++20 salience knapsack on bloated CLI/test logs
- `tokendiet_skeletonize_code`: Compress unfocused Python code via AST skeletonization
- `tokendiet_compress_session`: Cross-turn read deduplication + log/AST compression
- `tokendiet_route_finops`: Compute cascade-guarded multi-tier model routing & savings
"""

from __future__ import annotations

import json
import sys
from typing import IO, Any

from tokendiet.compressors.ast_skeleton import skeletonize_python_source
from tokendiet.compressors.log_pruner import prune_tool_output
from tokendiet.compressors.session_pruner import compress_agent_session
from tokendiet.router.finops_router import route_turn_finops
from tokendiet.types import SessionTurnInput


def _tool_definitions() -> list[dict[str, Any]]:
    return [
        {
            "name": "tokendiet_prune_tool_output",
            "description": "Prune noisy CLI, pytest, tsc, or build logs to a token budget using the C++20 Order-Preserving Salience Knapsack while keeping error/traceback anchors.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "budget_tokens": {"type": "integer", "default": 180},
                    "halo_radius": {"type": "integer", "default": 2},
                },
                "required": ["text"],
            },
        },
        {
            "name": "tokendiet_skeletonize_code",
            "description": "AST-skeletonize Python files by keeping imports, signatures, docstrings, and focus symbols while eliding long unfocused helper bodies.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "source": {"type": "string"},
                    "focus_symbols": {"type": "array", "items": {"type": "string"}},
                    "min_elide_lines": {"type": "integer", "default": 5},
                },
                "required": ["source"],
            },
        },
        {
            "name": "tokendiet_compress_session",
            "description": "Compress a multi-turn coding-agent trace using C++20 cross-turn read deduplication, log pruning, and AST skeletonization.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "turns": {"type": "array", "items": {"type": "object"}},
                    "log_budget_tokens": {"type": "integer", "default": 180},
                    "focus_symbols": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["turns"],
            },
        },
        {
            "name": "tokendiet_route_finops",
            "description": "Route an agent turn across Local Flash, Balanced Coding, and Frontier Reasoning tiers with Cascade Escalation Guard.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "prompt_summary": {"type": "string"},
                    "context_tokens_raw": {"type": "integer"},
                    "context_tokens_compressed": {"type": "integer"},
                    "retry_count": {"type": "integer", "default": 0},
                    "requires_formal_or_security_proof": {"type": "boolean", "default": False},
                    "multi_file_count": {"type": "integer", "default": 1},
                },
                "required": ["prompt_summary", "context_tokens_raw", "context_tokens_compressed"],
            },
        },
    ]


class TokenDietMCPServer:
    """In-process and stdio JSON-RPC 2.0 handler exposing all 4 tokendiet MCP tools."""

    def handle_request(self, msg: dict[str, Any]) -> dict[str, Any] | None:
        method = str(msg.get("method", ""))
        req_id = msg.get("id")

        if method == "notifications/initialized" or req_id is None:
            return None

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "tokendiet-mcp", "version": "1.0.0"},
                },
            }

        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": _tool_definitions()}}

        if method == "tools/call":
            params = msg.get("params", {})
            name = str(params.get("name", ""))
            args = params.get("arguments", {}) or {}
            try:
                payload = self._dispatch_tool(name, args)
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": json.dumps(payload, indent=2)}],
                        "isError": False,
                    },
                }
            except Exception as exc:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": f"Error in {name}: {exc}"}],
                        "isError": True,
                    },
                }

        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }

    def _dispatch_tool(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        if name == "tokendiet_prune_tool_output":
            report = prune_tool_output(
                text=str(args["text"]),
                budget_tokens=int(args.get("budget_tokens", 180)),
                halo_radius=int(args.get("halo_radius", 2)),
            )
            return report.model_dump(exclude={"line_details"})

        if name == "tokendiet_skeletonize_code":
            focus = set(str(s) for s in args.get("focus_symbols", []) or [])
            skel = skeletonize_python_source(
                source=str(args["source"]),
                focus_symbols=focus or None,
                min_elide_lines=int(args.get("min_elide_lines", 5)),
            )
            return skel.model_dump()

        if name == "tokendiet_compress_session":
            turns = [SessionTurnInput.model_validate(item) for item in args["turns"]]
            focus = set(str(s) for s in args.get("focus_symbols", []) or [])
            session = compress_agent_session(
                turns=turns,
                log_budget_tokens=int(args.get("log_budget_tokens", 180)),
                focus_symbols=focus or None,
            )
            return session.model_dump()

        if name == "tokendiet_route_finops":
            decision = route_turn_finops(
                prompt_summary=str(args["prompt_summary"]),
                context_tokens_raw=int(args["context_tokens_raw"]),
                context_tokens_compressed=int(args["context_tokens_compressed"]),
                retry_count=int(args.get("retry_count", 0)),
                requires_formal_or_security_proof=bool(
                    args.get("requires_formal_or_security_proof", False)
                ),
                multi_file_count=int(args.get("multi_file_count", 1)),
            )
            return decision.model_dump()

        raise ValueError(f"Unknown MCP tool: {name}")

    def serve_streams(self, stdin: IO[str] = sys.stdin, stdout: IO[str] = sys.stdout) -> None:
        for raw_line in stdin:
            line = raw_line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
                resp = self.handle_request(msg)
                if resp is not None:
                    stdout.write(json.dumps(resp) + "\n")
                    stdout.flush()
            except Exception as exc:
                stdout.write(
                    json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "id": None,
                            "error": {"code": -32700, "message": str(exc)},
                        }
                    )
                    + "\n"
                )
                stdout.flush()

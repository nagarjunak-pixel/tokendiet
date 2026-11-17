"""Tests for MCP stdio server, FastAPI HTTP endpoints, Typer CLI & Ollama audit."""

from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from tokendiet.api.app import create_app
from tokendiet.audit.ollama_diet import run_real_diet_ollama_audit
from tokendiet.cli import app as cli_app
from tokendiet.demo import DEMO_PYTHON_MODULE, build_demo_pytest_log
from tokendiet.mcp.server import TokenDietMCPServer
from tokendiet.types import RealDietAuditReport


def test_mcp_server_rpc_and_stdio() -> None:
    srv = TokenDietMCPServer()
    assert srv.handle_request({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None

    init_resp = srv.handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert init_resp is not None
    assert init_resp["result"]["serverInfo"]["name"] == "tokendiet-mcp"

    list_resp = srv.handle_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    assert list_resp is not None
    names = {t["name"] for t in list_resp["result"]["tools"]}
    assert {
        "tokendiet_prune_tool_output",
        "tokendiet_skeletonize_code",
        "tokendiet_compress_session",
        "tokendiet_route_finops",
    } == names

    prune_call = srv.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "tokendiet_prune_tool_output",
                "arguments": {"text": build_demo_pytest_log(), "budget_tokens": 160},
            },
        }
    )
    assert prune_call is not None and prune_call["result"]["isError"] is False

    skel_call = srv.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "tokendiet_skeletonize_code",
                "arguments": {
                    "source": DEMO_PYTHON_MODULE,
                    "focus_symbols": ["compute_monthly_discount"],
                    "min_elide_lines": 4,
                },
            },
        }
    )
    assert skel_call is not None and skel_call["result"]["isError"] is False

    sess_call = srv.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {
                "name": "tokendiet_compress_session",
                "arguments": {
                    "turns": [
                        {
                            "turn_id": 1,
                            "kind": "read_file",
                            "label": "a.py",
                            "content": DEMO_PYTHON_MODULE,
                        },
                        {
                            "turn_id": 2,
                            "kind": "read_file",
                            "label": "a.py",
                            "content": DEMO_PYTHON_MODULE,
                        },
                    ]
                },
            },
        }
    )
    assert sess_call is not None and sess_call["result"]["isError"] is False

    route_call = srv.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 6,
            "method": "tools/call",
            "params": {
                "name": "tokendiet_route_finops",
                "arguments": {
                    "prompt_summary": "Extract line",
                    "context_tokens_raw": 1000,
                    "context_tokens_compressed": 200,
                },
            },
        }
    )
    assert route_call is not None and route_call["result"]["isError"] is False

    bad_tool = srv.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "tools/call",
            "params": {"name": "nonexistent", "arguments": {}},
        }
    )
    assert bad_tool is not None and bad_tool["result"]["isError"] is True

    bad_method = srv.handle_request({"jsonrpc": "2.0", "id": 8, "method": "bad/method"})
    assert bad_method is not None and bad_method["error"]["code"] == -32601

    stdin = io.StringIO('\n{"jsonrpc":"2.0","id":9,"method":"tools/list"}\n{broken json\n')
    stdout = io.StringIO()
    srv.serve_streams(stdin=stdin, stdout=stdout)
    out_lines = stdout.getvalue().strip().splitlines()
    assert len(out_lines) == 2
    assert json.loads(out_lines[1])["error"]["code"] == -32700


def test_fastapi_endpoints() -> None:
    client = TestClient(create_app())
    assert client.get("/api/v1/health").json()["service"] == "tokendiet"
    assert client.get("/api/v1/demo").status_code == 200
    assert (
        client.post(
            "/api/v1/prune", json={"text": build_demo_pytest_log(), "budget_tokens": 160}
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/v1/skeleton",
            json={
                "source": DEMO_PYTHON_MODULE,
                "focus_symbols": ["compute_monthly_discount"],
                "min_elide_lines": 4,
            },
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/v1/route",
            json={
                "prompt_summary": "Quick fix",
                "context_tokens_raw": 800,
                "context_tokens_compressed": 160,
            },
        ).status_code
        == 200
    )
    assert client.get("/").status_code == 200


def test_ollama_audit_mocked_and_offline_replay(tmp_path: Path) -> None:
    out_file = tmp_path / "audit.json"

    class _FakeResp:
        def __init__(self, content: str, prompt_tok: int) -> None:
            self._body = {"message": {"content": content}, "prompt_eval_count": prompt_tok}

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return self._body

    def _fake_post(url: str, json: dict[str, object], timeout: float) -> _FakeResp:
        msgs = json["messages"]
        assert isinstance(msgs, list)
        user_content = str(msgs[1]["content"])
        tokens = max(50, len(user_content) // 4)
        return _FakeResp(
            "billing.py line 142 ZeroDivisionError session.ts 88 TS2345 "
            "retry_policy.py 67 TimeoutError compute_net_margin total_cost "
            "config.py pydantic_settings orders chk_positive_qty",
            tokens,
        )

    with patch("tokendiet.audit.ollama_diet.httpx.post", side_effect=_fake_post):
        rep = run_real_diet_ollama_audit(output_path=out_file)
    assert rep.execution_mode == "live-ollama"
    assert rep.diet_verified_pct == 100.0
    assert rep.avg_prompt_token_savings_pct > 40.0

    with patch("tokendiet.audit.ollama_diet.httpx.post", side_effect=RuntimeError("offline")):
        replayed = run_real_diet_ollama_audit(allow_offline_replay=True, output_path=out_file)
    assert replayed.execution_mode == "recorded-artifact-replay"
    assert isinstance(replayed, RealDietAuditReport)

    with (
        patch("tokendiet.audit.ollama_diet.httpx.post", side_effect=RuntimeError("offline")),
        pytest.raises(RuntimeError),
    ):
        run_real_diet_ollama_audit(allow_offline_replay=False, output_path=out_file)


def test_cli_and_audit_endpoint(tmp_path: Path) -> None:
    runner = CliRunner()
    assert runner.invoke(cli_app, ["demo"]).exit_code == 0

    log_file = tmp_path / "sample.log"
    log_file.write_text(build_demo_pytest_log(), encoding="utf-8")
    assert runner.invoke(cli_app, ["prune", str(log_file), "--budget", "150"]).exit_code == 0

    py_file = tmp_path / "mod.py"
    py_file.write_text(DEMO_PYTHON_MODULE, encoding="utf-8")
    assert (
        runner.invoke(
            cli_app, ["skeleton", str(py_file), "--focus", "compute_monthly_discount"]
        ).exit_code
        == 0
    )

    client = TestClient(create_app())

    class _Resp:
        def __init__(self, txt: str) -> None:
            self._txt = txt

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"message": {"content": self._txt}, "prompt_eval_count": 120}

    tmp_art = tmp_path / "real_qwen_tokendiet.json"
    with (
        patch("tokendiet.api.app.default_diet_audit_path", return_value=tmp_art),
        patch("tokendiet.audit.ollama_diet.default_diet_audit_path", return_value=tmp_art),
        patch(
            "tokendiet.audit.ollama_diet.httpx.post",
            return_value=_Resp(
                "billing.py line 142 ZeroDivisionError session.ts 88 TS2345 "
                "retry_policy.py 67 TimeoutError compute_net_margin total_cost "
                "config.py pydantic_settings orders chk_positive_qty"
            ),
        ),
    ):
        resp_refresh = client.get("/api/v1/audit/ollama?refresh=true")
        assert resp_refresh.status_code == 200
        cli_eval = runner.invoke(cli_app, ["eval-ollama"])
        assert cli_eval.exit_code == 0
        resp_cached = client.get("/api/v1/audit/ollama")
        assert resp_cached.status_code == 200

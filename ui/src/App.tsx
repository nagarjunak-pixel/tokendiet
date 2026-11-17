import { useEffect, useState } from "react";

interface PrunedOutputReport {
  kernel_backend: string;
  budget_tokens: number;
  total_lines: number;
  kept_lines: number;
  omitted_lines: number;
  original_tokens: number;
  compressed_tokens: number;
  savings_pct: number;
  total_anchors: number;
  kept_anchors: number;
  anchor_retention_pct: number;
  compressed_text: string;
}

interface SkeletonReport {
  original_lines: number;
  compressed_lines: number;
  original_tokens: number;
  compressed_tokens: number;
  savings_pct: number;
  syntax_valid: boolean;
  preserved_symbols: string[];
  elided_symbols: string[];
  compressed_source: string;
}

interface SessionTurnSummary {
  turn_id: number;
  kind: string;
  label: string;
  original_tokens: number;
  compressed_tokens: number;
  savings_pct: number;
  dedup_blocks_replaced: number;
}

interface SessionCompressionReport {
  kernel_backend: string;
  turn_count: number;
  original_tokens: number;
  compressed_tokens: number;
  tokens_saved: number;
  savings_pct: number;
  dedup_blocks_replaced: number;
  anchor_retention_pct: number;
  estimated_frontier_usd_saved: number;
  turn_summaries: SessionTurnSummary[];
}

interface FinOpsRouteDecision {
  selected_tier: string;
  model_id: string;
  unit_cost_per_1m_usd: number;
  complexity_score: number;
  cascade_escalated: boolean;
  reason: string;
  naive_frontier_cost_usd: number;
  routed_compressed_cost_usd: number;
  cost_reduction_pct: number;
  annualized_50_eng_savings_usd: number;
}

interface DemoPayload {
  sample_log: string;
  sample_code: string;
  prune_report: PrunedOutputReport;
  skeleton_report: SkeletonReport;
  session_report: SessionCompressionReport;
  finops_flash_route: FinOpsRouteDecision;
  finops_escalated_route: FinOpsRouteDecision;
}

interface DietTask {
  task_id: string;
  title: string;
  mode: string;
  raw_prompt_tokens: number;
  diet_prompt_tokens: number;
  prompt_token_savings_pct: number;
  raw_latency_ms: number;
  diet_latency_ms: number;
  raw_verified: boolean;
  diet_verified: boolean;
}

interface AuditReport {
  model: string;
  execution_mode: string;
  total_tasks: number;
  raw_verified_pct: number;
  diet_verified_pct: number;
  avg_prompt_token_savings_pct: number;
  avg_latency_speedup_pct: number;
  total_raw_prompt_tokens: number;
  total_diet_prompt_tokens: number;
  tasks: DietTask[];
}

interface HealthInfo {
  status: string;
  service: string;
  version: string;
  kernel_backend: string;
}

const MCP_SNIPPET = `{
  "mcpServers": {
    "tokendiet": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/tokendiet", "tokendiet", "mcp-stdio"]
    }
  }
}`;

export default function App() {
  const [health, setHealth] = useState<HealthInfo | null>(null);
  const [demo, setDemo] = useState<DemoPayload | null>(null);
  const [audit, setAudit] = useState<AuditReport | null>(null);
  const [budget, setBudget] = useState<number>(180);
  const [viewMode, setViewMode] = useState<"prune" | "skeleton">("prune");
  const [livePrune, setLivePrune] = useState<PrunedOutputReport | null>(null);
  const [loadingPrune, setLoadingPrune] = useState<boolean>(false);

  useEffect(() => {
    Promise.all([
      fetch("/api/v1/health").then((r) => r.json()),
      fetch("/api/v1/demo?budget_tokens=180").then((r) => r.json()),
      fetch("/api/v1/audit/ollama").then((r) => r.json()),
    ])
      .then(([h, d, a]) => {
        setHealth(h);
        setDemo(d);
        setLivePrune(d.prune_report);
        setAudit(a);
      })
      .catch(() => {
        // Handled cleanly in empty state
      });
  }, []);

  const handlePruneBudget = async (nextBudget: number) => {
    if (!demo) return;
    setBudget(nextBudget);
    setLoadingPrune(true);
    try {
      const resp = await fetch("/api/v1/prune", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: demo.sample_log,
          budget_tokens: nextBudget,
          halo_radius: 2,
        }),
      });
      const data: PrunedOutputReport = await resp.json();
      setLivePrune(data);
    } finally {
      setLoadingPrune(false);
    }
  };

  if (!demo || !livePrune) {
    return (
      <div className="page">
        <p className="subtitle">Loading tokendiet C++20 Workbench & telemetry...</p>
      </div>
    );
  }

  return (
    <div className="page">
      <header className="header">
        <div>
          <h1 className="title">tokendiet — Agent Context Compressor & FinOps Router</h1>
          <p className="subtitle">
            C++20 Order-Preserving Salience Knapsack · Python AST Skeletonizer · Cross-Turn Block
            Deduplicator · MCP Server
          </p>
        </div>
        <div className="badges">
          <span className="badge">v{health?.version ?? "1.0.0"}</span>
          <span className="badge emerald">{health?.kernel_backend ?? livePrune.kernel_backend}</span>
          <span className="badge">MCP stdio ready</span>
          {audit && <span className="badge emerald">{audit.model} ({audit.execution_mode})</span>}
        </div>
      </header>

      <section className="kpi-grid">
        <div className="kpi-card">
          <div className="kpi-label">Session Token Savings</div>
          <div className="kpi-value">{demo.session_report.savings_pct.toFixed(1)}%</div>
          <div className="kpi-sub">
            {demo.session_report.original_tokens} → {demo.session_report.compressed_tokens} tok (
            {demo.session_report.tokens_saved} trimmed)
          </div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">Error Anchor Retention</div>
          <div className="kpi-value">{livePrune.anchor_retention_pct.toFixed(1)}%</div>
          <div className="kpi-sub">
            {livePrune.kept_anchors}/{livePrune.total_anchors} mandatory anchors kept
          </div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">Live {audit?.model ?? "Qwen"} Audit</div>
          <div className="kpi-value">
            {audit ? `${audit.avg_prompt_token_savings_pct.toFixed(1)}%` : "—"}
          </div>
          <div className="kpi-sub">
            {audit
              ? `${audit.diet_verified_pct.toFixed(0)}% accuracy · ${audit.avg_latency_speedup_pct.toFixed(1)}% faster`
              : "Run eval-ollama"}
          </div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">FinOps Route Reduction</div>
          <div className="kpi-value">
            {demo.finops_flash_route.cost_reduction_pct.toFixed(1)}%
          </div>
          <div className="kpi-sub">
            ${demo.finops_flash_route.naive_frontier_cost_usd.toFixed(5)} → $
            {demo.finops_flash_route.routed_compressed_cost_usd.toFixed(6)}/turn
          </div>
        </div>
      </section>

      <section className="panel">
        <div className="panel-head">
          <h2 className="panel-title">Interactive Compression Playground</h2>
          <div className="controls">
            <button
              className={`btn ${viewMode === "prune" ? "active" : "secondary"}`}
              onClick={() => setViewMode("prune")}
            >
              C++20 Log Pruner
            </button>
            <button
              className={`btn ${viewMode === "skeleton" ? "active" : "secondary"}`}
              onClick={() => setViewMode("skeleton")}
            >
              Python AST Skeletonizer
            </button>
            {viewMode === "prune" && (
              <>
                <select
                  className="select"
                  value={budget}
                  onChange={(e) => void handlePruneBudget(Number(e.target.value))}
                >
                  <option value={120}>Budget: 120 tok</option>
                  <option value={180}>Budget: 180 tok</option>
                  <option value={240}>Budget: 240 tok</option>
                  <option value={320}>Budget: 320 tok</option>
                </select>
                <button
                  className="btn"
                  disabled={loadingPrune}
                  onClick={() => void handlePruneBudget(budget)}
                >
                  {loadingPrune ? "Running C++20..." : "Re-Run Knapsack"}
                </button>
              </>
            )}
          </div>
        </div>

        {viewMode === "prune" ? (
          <div className="split">
            <div>
              <div className="code-label">
                <span>Raw Tool / Pytest Log</span>
                <span>
                  {livePrune.total_lines} lines · {livePrune.original_tokens} tok
                </span>
              </div>
              <pre className="code-box">{demo.sample_log}</pre>
            </div>
            <div>
              <div className="code-label">
                <span>tokendiet Compressed Output ({livePrune.savings_pct.toFixed(1)}% saved)</span>
                <span>
                  {livePrune.kept_lines} lines kept · {livePrune.compressed_tokens} tok
                </span>
              </div>
              <pre className="code-box">{livePrune.compressed_text}</pre>
            </div>
          </div>
        ) : (
          <div className="split">
            <div>
              <div className="code-label">
                <span>Raw Python Source (`src/billing.py`)</span>
                <span>
                  {demo.skeleton_report.original_lines} lines ·{" "}
                  {demo.skeleton_report.original_tokens} tok
                </span>
              </div>
              <pre className="code-box">{demo.sample_code}</pre>
            </div>
            <div>
              <div className="code-label">
                <span>
                  AST Skeleton (`ast.parse={String(demo.skeleton_report.syntax_valid)}` ·{" "}
                  {demo.skeleton_report.savings_pct.toFixed(1)}% saved)
                </span>
                <span>
                  Focus: {demo.skeleton_report.preserved_symbols.join(", ")} ·{" "}
                  {demo.skeleton_report.compressed_tokens} tok
                </span>
              </div>
              <pre className="code-box">{demo.skeleton_report.compressed_source}</pre>
            </div>
          </div>
        )}
      </section>

      <div className="split">
        <section className="panel">
          <div className="panel-head">
            <h2 className="panel-title">Multi-Turn Session Compression</h2>
            <span className="pill-pass">
              {demo.session_report.dedup_blocks_replaced} repeated blocks deduplicated
            </span>
          </div>
          <table>
            <thead>
              <tr>
                <th>Turn</th>
                <th>Kind</th>
                <th>Original</th>
                <th>Compressed</th>
                <th>Saved</th>
              </tr>
            </thead>
            <tbody>
              {demo.session_report.turn_summaries.map((t) => (
                <tr key={t.turn_id}>
                  <td>
                    #{t.turn_id} {t.label}
                  </td>
                  <td>{t.kind}</td>
                  <td>{t.original_tokens}</td>
                  <td>{t.compressed_tokens}</td>
                  <td>
                    <span className="pill-pass">{t.savings_pct.toFixed(1)}%</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        <section className="panel">
          <div className="panel-head">
            <h2 className="panel-title">FinOps Tier Routing & Cascade Guard</h2>
            <span className="pill-warn">Auto Frontier Escalation Active</span>
          </div>
          <table>
            <thead>
              <tr>
                <th>Scenario</th>
                <th>Tier</th>
                <th>Cost / Turn</th>
                <th>Savings</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>Single-unit bugfix</td>
                <td>{demo.finops_flash_route.selected_tier}</td>
                <td>${demo.finops_flash_route.routed_compressed_cost_usd.toFixed(6)}</td>
                <td>
                  <span className="pill-pass">
                    {demo.finops_flash_route.cost_reduction_pct.toFixed(1)}%
                  </span>
                </td>
              </tr>
              <tr>
                <td>Retry / formal ledger proof</td>
                <td>{demo.finops_escalated_route.selected_tier}</td>
                <td>${demo.finops_escalated_route.routed_compressed_cost_usd.toFixed(6)}</td>
                <td>
                  <span className="pill-warn">
                    {demo.finops_escalated_route.cost_reduction_pct.toFixed(1)}% (context diet)
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
          <div style={{ marginTop: 14 }}>
            <div className="code-label">
              <span>Drop-In Claude Code / Cursor `.mcp.json`</span>
              <span>JSON-RPC 2.0 stdio</span>
            </div>
            <pre className="code-box" style={{ maxHeight: 145 }}>
              {MCP_SNIPPET}
            </pre>
          </div>
        </section>
      </div>

      {audit && (
        <section className="panel">
          <div className="panel-head">
            <h2 className="panel-title">
              Live Local LLM Audit ({audit.model} · {audit.total_raw_prompt_tokens} →{" "}
              {audit.total_diet_prompt_tokens} Prompt Tokens)
            </h2>
            <span className="pill-pass">
              Raw {audit.raw_verified_pct.toFixed(0)}% → Diet {audit.diet_verified_pct.toFixed(0)}%
              Verified
            </span>
          </div>
          <table>
            <thead>
              <tr>
                <th>Task</th>
                <th>Mode</th>
                <th>Raw Tokens</th>
                <th>Diet Tokens</th>
                <th>Prompt Saved</th>
                <th>Latency (Raw → Diet)</th>
                <th>Verified</th>
              </tr>
            </thead>
            <tbody>
              {audit.tasks.map((task) => (
                <tr key={task.task_id}>
                  <td>
                    <strong>{task.task_id}</strong> · {task.title}
                  </td>
                  <td>{task.mode}</td>
                  <td>{task.raw_prompt_tokens}</td>
                  <td>{task.diet_prompt_tokens}</td>
                  <td>
                    <span className="pill-pass">{task.prompt_token_savings_pct.toFixed(1)}%</span>
                  </td>
                  <td>
                    {task.raw_latency_ms.toFixed(0)}ms → {task.diet_latency_ms.toFixed(0)}ms
                  </td>
                  <td>
                    <span className="pill-pass">
                      {task.raw_verified ? "PASS" : "FAIL"} →{" "}
                      {task.diet_verified ? "PASS" : "FAIL"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </div>
  );
}

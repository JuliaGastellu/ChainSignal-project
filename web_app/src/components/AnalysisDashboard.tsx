import { BarChart3, Shield, ListChecks } from "lucide-react";
import type { AgentResults } from "@/hooks/useAgentSSE";

function metricValue(v: unknown) {
  if (v === null || v === undefined) return "Baseline telemetry collecting";
  if (typeof v === "number") return Number.isInteger(v) ? String(v) : v.toFixed(3);
  return String(v);
}

function confidencePct(c?: number) {
  if (c === undefined || Number.isNaN(c)) return "Calibrating";
  const value = c > 1 ? c : c * 100;
  return `${Math.round(value)}%`;
}

function renderRiskFactor(r: unknown) {
  if (typeof r === "string") return { title: "Risk factor", severity: "info", detail: r };
  if (r && typeof r === "object") {
    const obj = r as Record<string, unknown>;
    return {
      title: typeof obj.factor === "string" ? obj.factor : "Risk factor",
      severity: typeof obj.severity === "string" ? obj.severity : "info",
      detail: typeof obj.detail === "string" ? obj.detail : "Signal detail is being inferred from latest cycle",
    };
  }
  return { title: "Risk factor", severity: "info", detail: "Signal detail is being inferred from latest cycle" };
}

export function AnalysisDashboard({ results }: { results: AgentResults }) {
  const full = results.full_analysis || {};
  const metrics = (results.metrics || (full.metrics as Record<string, unknown>) || {}) as Record<string, unknown>;
  const profile = ((full as Record<string, unknown>).profile || {}) as Record<string, unknown>;
  const scores = ((full as Record<string, unknown>).scores || {}) as Record<string, unknown>;
  const riskBreakdown = (((scores.risk as Record<string, unknown> | undefined)?.breakdown as unknown[]) || results.risk_factors || []) as unknown[];

  return (
    <div className="space-y-4">
      <div className="bg-card border border-border rounded-xl p-4">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <BarChart3 className="h-4 w-4" /> Metrics Panel
        </div>
        <div className="mt-3 grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
          <div className="rounded-lg border border-border bg-secondary/30 p-3"><div className="text-muted-foreground">Tx Count</div><div className="font-semibold">{metricValue(metrics.total_transactions)}</div></div>
          <div className="rounded-lg border border-border bg-secondary/30 p-3"><div className="text-muted-foreground">ETH Balance</div><div className="font-semibold">{metricValue(metrics.eth_balance)}</div></div>
          <div className="rounded-lg border border-border bg-secondary/30 p-3"><div className="text-muted-foreground">Activity Score</div><div className="font-semibold">{metricValue(results.activity_score)}</div></div>
          <div className="rounded-lg border border-border bg-secondary/30 p-3"><div className="text-muted-foreground">Contract %</div><div className="font-semibold">{metricValue(metrics.contract_interactions_pct)}</div></div>
        </div>
      </div>

      <div className="bg-card border border-border rounded-xl p-4">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <Shield className="h-4 w-4" /> Behavioral Analysis
        </div>
        <div className="mt-2 text-xs text-muted-foreground">Profile: {metricValue(profile.type || results.perfil)}</div>
        <div className="mt-2 flex flex-wrap gap-2">
          {(Array.isArray(profile.signals) ? profile.signals : []).map((s, i) => (
            <span key={i} className="text-[10px] px-2 py-1 rounded border border-border bg-secondary/40">{String(s)}</span>
          ))}
        </div>
        {riskBreakdown.length > 0 && (
          <div className="mt-3 space-y-2">
            {riskBreakdown.slice(0, 6).map((r, i) => (
              <div key={i} className="text-xs rounded border border-border bg-secondary/30 p-2">
                <div className="font-semibold text-foreground">{renderRiskFactor(r).title}</div>
                <div className="text-[10px] mt-1 uppercase text-muted-foreground">{renderRiskFactor(r).severity}</div>
                <div className="mt-1 text-muted-foreground">{renderRiskFactor(r).detail}</div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="bg-card border border-border rounded-xl p-4">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <ListChecks className="h-4 w-4" /> Reasoning & Execution Decision
        </div>
        <div className="mt-2 text-sm text-muted-foreground">
          {results.reasoning || results.why_not_acting || "Agent is maintaining autonomous monitoring posture with safe controls."}
        </div>
        <div className="mt-3 text-xs">
          <span className="text-muted-foreground">Action:</span>{" "}
          <span className="font-semibold">{results.recommended_action || "monitor"}</span>
        </div>
      </div>
    </div>
  );
}

import { Brain, BarChart3, Shield, ListChecks } from "lucide-react";
import type { AgentResults } from "@/hooks/useAgentSSE";

function metricValue(v: unknown) {
  if (v === null || v === undefined) return "N/A";
  if (typeof v === "number") return Number.isInteger(v) ? String(v) : v.toFixed(3);
  return String(v);
}

function confidencePct(c?: number) {
  if (c === undefined || Number.isNaN(c)) return "N/A";
  const value = c > 1 ? c : c * 100;
  return `${Math.round(value)}%`;
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
          <Brain className="h-4 w-4" /> Agent Summary
        </div>
        <div className="mt-3 grid grid-cols-1 md:grid-cols-4 gap-3">
          <div className="rounded-lg border border-border bg-secondary/30 p-3">
            <div className="text-[10px] uppercase text-muted-foreground">Decision</div>
            <div className="text-sm font-semibold">{results.agent_decision || "N/A"}</div>
          </div>
          <div className="rounded-lg border border-border bg-secondary/30 p-3">
            <div className="text-[10px] uppercase text-muted-foreground">Intent</div>
            <div className="text-sm">{results.agent_intent || "N/A"}</div>
          </div>
          <div className="rounded-lg border border-border bg-secondary/30 p-3">
            <div className="text-[10px] uppercase text-muted-foreground">Confidence</div>
            <div className="text-sm font-semibold">{confidencePct(results.confidence)}</div>
          </div>
          <div className="rounded-lg border border-border bg-secondary/30 p-3">
            <div className="text-[10px] uppercase text-muted-foreground">Risk</div>
            <div className="text-sm font-semibold">{metricValue(results.risk_score)}</div>
          </div>
        </div>
      </div>

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
              <div key={i} className="text-xs rounded border border-border bg-secondary/30 p-2">{typeof r === "string" ? r : JSON.stringify(r)}</div>
            ))}
          </div>
        )}
      </div>

      <div className="bg-card border border-border rounded-xl p-4">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <ListChecks className="h-4 w-4" /> Reasoning & Execution Decision
        </div>
        <div className="mt-2 text-sm text-muted-foreground">
          {results.reasoning || results.why_not_acting || "No reasoning available yet."}
        </div>
        <div className="mt-3 text-xs">
          <span className="text-muted-foreground">Action:</span>{" "}
          <span className="font-semibold">{results.recommended_action || "monitor"}</span>
        </div>
      </div>
    </div>
  );
}


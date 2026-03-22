import { useEffect, useState } from "react";
import { ArrowRight } from "lucide-react";
import { API_BASE } from "@/hooks/useAgentSSE";

export function ActionFlowBanner() {
  const [summary, setSummary] = useState<{ runs?: number; signals?: number; executions?: number }>({});

  useEffect(() => {
    const load = async () => {
      try {
        const [stateRes, learningRes] = await Promise.all([
          fetch(`${API_BASE}/agent/state`),
          fetch(`${API_BASE}/agent/learning`),
        ]);
        const state = await stateRes.json();
        const learning = await learningRes.json();
        setSummary({
          runs: state?.metrics?.total_runs ?? 0,
          signals: learning?.signals_count ?? 0,
          executions: state?.stats?.total_executions ?? 0,
        });
      } catch {
        setSummary({ runs: 0, signals: 0, executions: 0 });
      }
    };
    load();
    const id = window.setInterval(load, 8000);
    return () => window.clearInterval(id);
  }, []);

  return (
    <div className="bg-card border border-border rounded-xl p-3">
      <div className="text-xs text-muted-foreground">Autonomous Value Loop</div>
      <div className="mt-2 flex items-center gap-2 text-xs">
        <span className="px-2 py-1 rounded border border-border bg-secondary/40">Analyzed: {summary.runs ?? 0} cycles</span>
        <ArrowRight className="h-3.5 w-3.5 text-muted-foreground" />
        <span className="px-2 py-1 rounded border border-border bg-secondary/40">Signals: {summary.signals ?? 0} detected</span>
        <ArrowRight className="h-3.5 w-3.5 text-muted-foreground" />
        <span className="px-2 py-1 rounded border border-border bg-secondary/40">Executed: {summary.executions ?? 0} actions</span>
      </div>
    </div>
  );
}

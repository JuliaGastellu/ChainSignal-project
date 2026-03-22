import { useEffect, useMemo, useState } from "react";
import { Shield, Activity, Clock, Bot, AlertCircle, CheckCircle2, Loader2 } from "lucide-react";
import { API_BASE } from "@/hooks/useAgentSSE";
import type { AgentEvent } from "@/hooks/useAgentSSE";

type HealthPayload = {
  agent_loop?: "active" | "inactive";
  global_metrics?: {
    total_runs?: number;
    executions_triggered?: number;
    executions_blocked?: number;
    last_execution_time?: string | null;
  };
};

type SafetyStateValue = "passed" | "blocked" | "failed" | "aborted" | "safe" | "unsafe" | "skipped" | "not_required";
type SafetyState = {
  idempotency: SafetyStateValue;
  simulation: SafetyStateValue;
  exposure: SafetyStateValue;
  note?: string;
};

function formatWhen(iso?: string | null) {
  if (!iso) return "Monitoring active";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "Not available yet";
  return d.toLocaleString();
}

function deriveSafety(events: AgentEvent[]): SafetyState {
  const hasExecution = events.some((e) => {
    const p = e.paso.toLowerCase();
    return p === "execution_safety" || p === "execution_step" || p === "execution_verification";
  });

  if (!hasExecution) {
    return { idempotency: "not_required", simulation: "not_required", exposure: "not_required", note: "No execution yet → safety checks are idle until first action." };
  }

  const safetyEvents = events.filter((e) => e.paso.toLowerCase() === "execution_safety");
  const lastSafety = safetyEvents[safetyEvents.length - 1];
  const lastSafetyText = (lastSafety?.detalle || "").toLowerCase();
  const lastSafetyStatus = (lastSafety?.estado || "").toLowerCase();

  const isAborted = lastSafetyStatus === "error" || lastSafetyStatus === "failed";
  const hasSuccessSignal =
    lastSafetyStatus === "completed" &&
    (lastSafetyText.includes("safety checks passed") ||
      lastSafetyText.includes("validation successful") ||
      lastSafetyText.includes("fingerprint"));

  const idempotency =
    lastSafetyText.includes("already executed") || lastSafetyText.includes("already executing")
      ? "blocked"
      : hasSuccessSignal
        ? "passed"
        : isAborted
          ? "aborted"
          : "skipped";

  const simulation =
    lastSafetyText.includes("strict simulation") && isAborted
      ? "failed"
      : hasSuccessSignal
        ? "passed"
        : isAborted
          ? "aborted"
          : "skipped";

  const exposure =
    lastSafetyText.includes("exposure") && isAborted
      ? "unsafe"
      : lastSafetyText.includes("exposure") && hasSuccessSignal
        ? "safe"
        : isAborted
          ? "skipped"
          : "skipped";

  return { idempotency, simulation, exposure };
}

function StatusRow({
  label,
  value,
  icon: Icon,
}: {
  label: string;
  value: string;
  icon: React.ElementType;
}) {
  return (
    <div className="flex items-start justify-between gap-3 rounded-lg border border-border bg-secondary/40 p-3">
      <div className="flex items-center gap-2 text-xs font-semibold text-muted-foreground uppercase tracking-wider">
        <Icon className="h-3.5 w-3.5" />
        {label}
      </div>
      <div className="text-xs font-mono text-foreground text-right break-all">{value}</div>
    </div>
  );
}

function CheckItem({
  label,
  state,
}: {
  label: string;
  state: SafetyStateValue;
}) {
  if (state === "not_required") {
    return (
      <div className="flex items-center justify-between rounded-lg border border-border bg-secondary/40 px-3 py-2">
        <span className="text-xs font-medium text-muted-foreground">{label}</span>
        <span className="text-xs font-semibold text-muted-foreground">READY</span>
      </div>
    );
  }
  if (state === "passed" || state === "safe") {
    return (
      <div className="flex items-center justify-between rounded-lg border border-green-500/20 bg-green-500/5 px-3 py-2">
        <span className="text-xs font-medium text-muted-foreground">{label}</span>
        <span className="inline-flex items-center gap-1 text-xs font-semibold text-green-500">
          <CheckCircle2 className="h-3.5 w-3.5" /> PASSED
        </span>
      </div>
    );
  }
  if (state === "blocked") {
    return (
      <div className="flex items-center justify-between rounded-lg border border-yellow-500/20 bg-yellow-500/5 px-3 py-2">
        <span className="text-xs font-medium text-muted-foreground">{label}</span>
        <span className="inline-flex items-center gap-1 text-xs font-semibold text-yellow-600">
          <AlertCircle className="h-3.5 w-3.5" /> BLOCKED
        </span>
      </div>
    );
  }
  if (state === "aborted") {
    return (
      <div className="flex items-center justify-between rounded-lg border border-yellow-500/20 bg-yellow-500/5 px-3 py-2">
        <span className="text-xs font-medium text-muted-foreground">{label}</span>
        <span className="inline-flex items-center gap-1 text-xs font-semibold text-yellow-600">
          <AlertCircle className="h-3.5 w-3.5" /> ABORTED
        </span>
      </div>
    );
  }
  if (state === "skipped") {
    return (
      <div className="flex items-center justify-between rounded-lg border border-border bg-secondary/40 px-3 py-2">
        <span className="text-xs font-medium text-muted-foreground">{label}</span>
        <span className="inline-flex items-center gap-1 text-xs font-semibold text-muted-foreground">
          <AlertCircle className="h-3.5 w-3.5" /> SKIPPED
        </span>
      </div>
    );
  }
  if (state === "failed" || state === "unsafe") {
    return (
      <div className="flex items-center justify-between rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2">
        <span className="text-xs font-medium text-muted-foreground">{label}</span>
        <span className="inline-flex items-center gap-1 text-xs font-semibold text-destructive">
          <AlertCircle className="h-3.5 w-3.5" /> FAILED
        </span>
      </div>
    );
  }
  return (
    <div className="flex items-center justify-between rounded-lg border border-border bg-secondary/40 px-3 py-2">
      <span className="text-xs font-medium text-muted-foreground">{label}</span>
      <span className="text-xs font-semibold text-muted-foreground">Pending next safeguarded execution</span>
    </div>
  );
}

export function SidePanel({ events }: { events: AgentEvent[] }) {
  const [health, setHealth] = useState<HealthPayload | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [secondsToRefresh, setSecondsToRefresh] = useState(7);

  const safety = useMemo(() => deriveSafety(events), [events]);

  useEffect(() => {
    let cancelled = false;

    const fetchHealth = async () => {
      try {
        const res = await fetch(`${API_BASE}/health`);
        const data = (await res.json()) as HealthPayload;
        if (cancelled) return;
        setHealth(data);
        setHealthError(null);
      } catch {
        if (cancelled) return;
        setHealthError("Could not fetch /health");
      }
    };

    fetchHealth();

    const refreshEveryS = 7;
    const interval = window.setInterval(() => {
      fetchHealth();
      setSecondsToRefresh(refreshEveryS);
    }, refreshEveryS * 1000);

    const countdown = window.setInterval(() => {
      setSecondsToRefresh((s) => (s <= 1 ? 1 : s - 1));
    }, 1000);

    return () => {
      cancelled = true;
      window.clearInterval(interval);
      window.clearInterval(countdown);
    };
  }, []);

  const loopState = health?.agent_loop === "active" ? "ACTIVE" : "READY";
  const metrics = health?.global_metrics;

  return (
    <div className="space-y-4 lg:sticky lg:top-6 h-fit lg:border-l lg:border-border lg:pl-4">
      <div className="bg-card border border-border rounded-xl p-4">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
            <Bot className="h-4 w-4" /> Autonomous Status
          </div>
          <span className="text-xs text-muted-foreground uppercase tracking-wider">/health</span>
        </div>

        {healthError ? (
          <div className="flex items-center gap-2 text-xs text-destructive">
            <AlertCircle className="h-4 w-4" />
            {healthError}
          </div>
        ) : !health ? (
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Loader2 className="h-3 w-3 animate-spin text-primary" />
            Loading status...
          </div>
        ) : (
          <div className="space-y-2">
            <StatusRow label="Loop" value={loopState} icon={Activity} />
            <StatusRow label="Last action" value={formatWhen(metrics?.last_execution_time)} icon={Clock} />
            <StatusRow label="Next eval" value={`~${secondsToRefresh}s`} icon={Clock} />
            <StatusRow
              label="Runs"
              value={`${metrics?.total_runs ?? 0} · Exec ${metrics?.executions_triggered ?? 0} · Blocked ${metrics?.executions_blocked ?? 0}`}
              icon={Activity}
            />
          </div>
        )}
      </div>

      <div className="bg-card border border-border rounded-xl p-4">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
            <Shield className="h-4 w-4" /> Execution Safety
          </div>
          <span className="text-xs text-muted-foreground uppercase tracking-wider">ESL</span>
        </div>

        <div className="space-y-2">
          <CheckItem label="Idempotency" state={safety.idempotency} />
          <CheckItem label="Simulation" state={safety.simulation} />
          <CheckItem label="Exposure" state={safety.exposure} />
          {safety.note && <div className="mt-2 text-[11px] text-muted-foreground">{safety.note}</div>}
        </div>
      </div>
    </div>
  );
}

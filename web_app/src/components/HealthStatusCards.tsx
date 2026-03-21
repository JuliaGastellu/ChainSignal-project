import { Activity, RefreshCcw, ShieldCheck, Ban } from "lucide-react";

type HealthObj = {
  status?: string;
  agent_loop?: "active" | "inactive";
  global_metrics?: {
    total_runs?: number;
    executions_triggered?: number;
    executions_blocked?: number;
  };
};

function Card({ label, value, icon: Icon }: { label: string; value: string; icon: React.ElementType }) {
  return (
    <div className="rounded-lg border border-border bg-card p-3">
      <div className="flex items-center gap-2 text-[10px] uppercase tracking-wider text-muted-foreground">
        <Icon className="h-3.5 w-3.5" />
        {label}
      </div>
      <div className="mt-1 text-sm font-semibold text-foreground">{value}</div>
    </div>
  );
}

export function HealthStatusCards({ health }: { health: HealthObj | null }) {
  const status = (health?.status || "unknown").toUpperCase();
  const loop = health?.agent_loop === "active" ? "ACTIVE" : "IDLE";
  const runs = String(health?.global_metrics?.total_runs ?? 0);
  const executions = String(health?.global_metrics?.executions_triggered ?? 0);
  const blocked = String(health?.global_metrics?.executions_blocked ?? 0);

  return (
    <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
      <Card label="Status" value={status} icon={ShieldCheck} />
      <Card label="Loop" value={loop} icon={Activity} />
      <Card label="Runs" value={runs} icon={RefreshCcw} />
      <Card label="Executions" value={executions} icon={Activity} />
      <Card label="Blocked" value={blocked} icon={Ban} />
    </div>
  );
}


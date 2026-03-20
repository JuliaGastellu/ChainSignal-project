import { motion } from "framer-motion";
import { CheckCircle2, Circle, AlertCircle, Loader2, ArrowRight, Sparkles } from "lucide-react";
import type { AgentEvent } from "@/hooks/useAgentSSE";

interface AgentTimelineProps {
  events: AgentEvent[];
  isStreaming: boolean;
}

const STEP_ORDER = [
  "analizando_wallet",
  "calculando_scores",
  "clasificando_perfil",
  "generando_insight",
  "evaluando_decision",
  "decision_final",
  "contrato_activo",
  "operacion_financiera",
  "generando_contrato",
  "compilando_contrato",
  "deployando_contrato",
];

const STEP_LABELS: Record<string, string> = {
  analizando_wallet: "Analyzing Wallet",
  calculando_scores: "Calculating Scores",
  clasificando_perfil: "Classifying Profile",
  generando_insight: "Generating Insight",
  evaluando_decision: "Evaluating Decision",
  decision_final: "Final Decision",
  contrato_activo: "Contract Active",
  operacion_financiera: "Financial Operation",
  generando_contrato: "Generating Contract",
  compilando_contrato: "Compiling Contract",
  deployando_contrato: "Deploying Contract",
};

function getStepIcon(estado: string) {
  switch (estado) {
    case "completado":
    case "completed":
      return <CheckCircle2 className="h-4 w-4 text-risk-low" />;
    case "error":
    case "failed":
      return <AlertCircle className="h-4 w-4 text-destructive" />;
    case "iniciando":
    case "processing":
    case "running":
      return <Loader2 className="h-4 w-4 text-primary animate-spin" />;
    default:
      return <Circle className="h-4 w-4 text-muted-foreground" />;
  }
}

function getStatusBadge(estado: string) {
  const base = "text-[10px] font-semibold px-2 py-0.5 rounded-full";
  switch (estado) {
    case "completado":
    case "completed":
      return <span className={`${base} bg-risk-low/15 text-risk-low`}>Completed</span>;
    case "iniciando":
    case "processing":
    case "running":
      return <span className={`${base} bg-primary/15 text-primary`}>Running</span>;
    case "error":
    case "failed":
      return <span className={`${base} bg-destructive/15 text-destructive`}>Error</span>;
    default:
      return <span className={`${base} bg-muted text-muted-foreground`}>{estado}</span>;
  }
}

function buildStepSummary(events: AgentEvent[]) {
  const summary: Record<string, AgentEvent> = {};
  for (const event of events) {
    const key = event.paso.toLowerCase();
    summary[key] = event; // keeps latest by same step
  }
  return summary;
}

export function AgentTimeline({ events, isStreaming }: AgentTimelineProps) {
  if (events.length === 0) return null;

  const summary = buildStepSummary(events);
  const orderedSteps = STEP_ORDER.filter((s) => summary[s]);

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.3 }}
      className="w-full max-w-2xl mx-auto mt-8"
    >
      <div className="mb-3 flex items-center justify-between">
        <div>
          <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wider">Agent Execution</h2>
          <p className="text-xs text-muted-foreground">Stream progress with quick action states.</p>
        </div>
        <span className="inline-flex items-center gap-1 text-xs font-semibold text-primary"><Sparkles className="h-3.5 w-3.5" /> Live</span>
      </div>

      <div className="bg-card border border-border rounded-xl p-3 space-y-2">
        {orderedSteps.map((stepKey, index) => {
          const event = summary[stepKey];
          const label = STEP_LABELS[stepKey] || stepKey;
          const isActive = event.estado === "iniciando" || event.estado === "processing" || event.estado === "running";
          return (
            <motion.div
              key={stepKey}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.22, delay: index * 0.04 }}
              className={`rounded-lg border px-3 py-2 ${event.estado === "completado" || event.estado === "completed" ? "border-risk-low/30 bg-risk-low/5" : "border-border bg-secondary/50"}`}
            >
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">
                  {getStepIcon(event.estado)}
                  <span>{label}</span>
                </div>
                <div>{getStatusBadge(event.estado)}</div>
              </div>
              <div className="mt-2 flex flex-col gap-1">
                <p className={`text-sm ${isActive ? "text-foreground font-semibold" : "text-muted-foreground"}`}>
                  {event.detalle || "Waiting for new update..."}
                </p>
                {event.data && (event.data as Record<string, unknown>).decision && (
                  <p className="text-[11px] text-primary font-medium">Decision: {((event.data as Record<string, unknown>).decision as string)}</p>
                )}
              </div>
              <div className="text-[11px] text-muted-foreground font-mono mt-1">{new Date(event.timestamp).toLocaleTimeString()}</div>
            </motion.div>
          );
        })}
        {isStreaming && (
          <div className="flex items-center gap-2 mt-2 text-xs text-muted-foreground">
            <Loader2 className="h-3 w-3 animate-spin text-primary" />
            <span>Processing next step...</span>
          </div>
        )}
      </div>
    </motion.div>
  );
}

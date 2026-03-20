import { motion } from "framer-motion";
import { CheckCircle2, Circle, AlertCircle, Loader2 } from "lucide-react";
import type { AgentEvent } from "@/hooks/useAgentSSE";

interface AgentTimelineProps {
  events: AgentEvent[];
  isStreaming: boolean;
}

const STEP_LABELS: Record<string, string> = {
  analizando_wallet: "Analyzing Wallet",
  calculando_scores: "Calculating Scores",
  clasificando_perfil: "Classifying Profile",
  generando_insight: "Generating Insight",
  decision_agente: "Agent Decision",
  ejecutando_accion: "Executing Action",
  resultado_final: "Final Result",
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
      return <Loader2 className="h-4 w-4 text-primary animate-spin" />;
    default:
      return <Circle className="h-4 w-4 text-muted-foreground" />;
  }
}

function getStatusBadge(estado: string) {
  const base = "text-xs font-medium px-2 py-0.5 rounded-full";
  switch (estado) {
    case "completado":
    case "completed":
      return <span className={`${base} bg-risk-low/10 text-risk-low`}>Completed</span>;
    case "iniciando":
    case "processing":
      return <span className={`${base} bg-primary/10 text-primary`}>Running</span>;
    case "error":
    case "failed":
      return <span className={`${base} bg-destructive/10 text-destructive`}>Error</span>;
    default:
      return <span className={`${base} bg-muted text-muted-foreground`}>{estado}</span>;
  }
}

export function AgentTimeline({ events, isStreaming }: AgentTimelineProps) {
  if (events.length === 0) return null;

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.3 }}
      className="w-full max-w-2xl mx-auto mt-8"
    >
      <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wider mb-4">
        Agent Execution
      </h2>
      <div className="relative">
        {/* Vertical line */}
        <div className="absolute left-[7px] top-2 bottom-2 w-px bg-border" />

        <div className="space-y-1">
          {events.map((event, i) => (
            <motion.div
              key={event.id}
              initial={{ opacity: 0, x: -12 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.3, delay: i * 0.05 }}
              className="relative flex items-start gap-4 pl-6 py-2.5 rounded-lg hover:bg-secondary/30 transition-colors group"
            >
              <div className="absolute left-0 top-3">
                {getStepIcon(event.estado)}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-0.5">
                  <span className="text-sm font-medium text-foreground">
                    {STEP_LABELS[event.paso] || event.paso}
                  </span>
                  {getStatusBadge(event.estado)}
                </div>
                {event.detalle && (
                  <p className="text-xs text-muted-foreground leading-relaxed truncate">
                    {event.detalle}
                  </p>
                )}
              </div>
              <span className="text-xs text-muted-foreground font-mono opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0">
                {new Date(event.timestamp).toLocaleTimeString()}
              </span>
            </motion.div>
          ))}
        </div>

        {isStreaming && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="flex items-center gap-2 pl-6 pt-3 text-xs text-muted-foreground"
          >
            <Loader2 className="h-3 w-3 animate-spin text-primary" />
            <span>Waiting for next step...</span>
          </motion.div>
        )}
      </div>
    </motion.div>
  );
}

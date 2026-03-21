import { motion } from "framer-motion";
import { CheckCircle2, Circle, AlertCircle, Loader2, ArrowRight, Sparkles } from "lucide-react";
import type { AgentEvent } from "@/hooks/useAgentSSE";

interface AgentTimelineProps {
  events: AgentEvent[];
  isStreaming: boolean;
}

const STEP_ORDER = [
  "analyzing_wallet",
  "calculating_scores",
  "classifying_profile",
  "generating_insight",
  "evaluating_decision",
  "x402_validation",
  "strategy_execution",
  "execution_safety",
  "execution_step",
  "execution_verification",
  "execution_lock",
  "execution_final_status",
  "decision_final",
  "contract_active",
  "financial_operation",
  "contract_generation",
  "contract_compilation",
  "contract_deployment",
];

const STEP_LABELS: Record<string, string> = {
  analyzing_wallet: "Analyzing Wallet",
  calculating_scores: "Calculating Scores",
  classifying_profile: "Classifying Profile",
  generating_insight: "Generating Insight",
  evaluating_decision: "Evaluating Decision",
  x402_validation: "License Validation (x402)",
  strategy_execution: "Strategy Execution",
  execution_safety: "Execution Safety (ESL)",
  execution_step: "Execution Step",
  execution_verification: "Execution Verification",
  execution_lock: "Execution Lock",
  execution_final_status: "Execution Final Status",
  decision_final: "Final Decision",
  contract_active: "Contract Active",
  financial_operation: "Financial Operation",
  contract_generation: "Generating Contract",
  contract_compilation: "Compiling Contract",
  contract_deployment: "Deploying Contract",
};

function getStepIcon(estado: string) {
  const status = estado.toLowerCase();
  switch (status) {
    case "completed":
    case "success":
      return <CheckCircle2 className="h-4 w-4 text-risk-low" />;
    case "error":
    case "failed":
      return <AlertCircle className="h-4 w-4 text-destructive" />;
    case "starting":
    case "processing":
    case "running":
      return <Loader2 className="h-4 w-4 text-primary animate-spin" />;
    default:
      return <Circle className="h-4 w-4 text-muted-foreground" />;
  }
}

function getStatusBadge(estado: string) {
  const base = "text-[10px] font-semibold px-2 py-0.5 rounded-full";
  const status = estado.toLowerCase();
  switch (status) {
    case "completed":
    case "success":
      return <span className={`${base} bg-risk-low/15 text-risk-low`}>Completed</span>;
    case "starting":
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

function getStepTone(paso: string) {
  const p = paso.toLowerCase();
  const analysis = new Set(["analyzing_wallet", "calculating_scores", "classifying_profile", "generating_insight"]);
  const decision = new Set(["evaluating_decision", "x402_validation", "strategy_execution", "decision_final"]);
  const execution = new Set([
    "execution_safety",
    "execution_step",
    "execution_verification",
    "contract_generation",
    "contract_compilation",
    "contract_deployment",
    "contract_active",
    "execution_final_status",
  ]);
  if (analysis.has(p)) return "analysis";
  if (decision.has(p)) return "decision";
  if (execution.has(p)) return "execution";
  return "neutral";
}

function getToneClasses(tone: string, estado: string) {
  const s = estado.toLowerCase();
  const isError = s === "error" || s === "failed";
  if (isError) return "border-destructive/30 bg-destructive/5";
  if (tone === "analysis") return "border-sky-500/20 bg-sky-500/5";
  if (tone === "decision") return "border-yellow-500/20 bg-yellow-500/5";
  if (tone === "execution") return "border-green-500/20 bg-green-500/5";
  return "border-border bg-secondary/50";
}

function getSourceBadge(source?: "api" | "loop") {
  const s = source || "api";
  const base = "text-[10px] font-semibold px-2 py-0.5 rounded-full";
  if (s === "loop") return <span className={`${base} bg-primary/10 text-primary border border-primary/20`}>Autonomous Agent</span>;
  return <span className={`${base} bg-muted text-muted-foreground border border-border`}>User Triggered</span>;
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
      <div className="mb-3 flex items-center justify-between">
        <div>
          <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wider">Agent Execution</h2>
          <p className="text-xs text-muted-foreground">Stream progress with quick action states.</p>
        </div>
        <span className="inline-flex items-center gap-1 text-xs font-semibold text-primary"><Sparkles className="h-3.5 w-3.5" /> Live</span>
      </div>

      <div className="bg-card border border-border rounded-xl p-3 space-y-2">
        {events.map((event, index) => {
          const stepKey = event.paso.toLowerCase();
          const label = STEP_LABELS[stepKey] || stepKey;
          const isActive =
            event.estado === "iniciando" || event.estado === "processing" || event.estado === "running" || event.estado === "starting";
          const tone = getStepTone(stepKey);
          const toneClasses = getToneClasses(tone, event.estado);
          return (
            <motion.div
              key={event.id}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.22, delay: index * 0.04 }}
              className={`rounded-lg border px-3 py-2 ${toneClasses}`}
            >
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">
                  {getStepIcon(event.estado)}
                  <span>{label}</span>
                </div>
                <div className="flex items-center gap-2">
                  {getSourceBadge(event.source)}
                  {getStatusBadge(event.estado)}
                </div>
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

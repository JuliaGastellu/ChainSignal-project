import { motion } from "framer-motion";
import { CheckCircle2, Circle, AlertCircle, Loader2, ArrowRight, Sparkles } from "lucide-react";
import type { AgentEvent } from "@/hooks/useAgentSSE";
import { useMemo } from "react";

interface AgentTimelineProps {
  events: AgentEvent[];
  isStreaming: boolean;
}

const STEP_ORDER = [
  "analyzing_wallet",
  "calculating_scores",
  "classifying_profile",
  "generating_insight",
  "signal_detected",
  "strategy_selected",
  "evaluating_decision",
  "simulation_passed",
  "execution_submitted",
  "execution_verified",
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
  signal_detected: "Signal Detected",
  strategy_selected: "Strategy Selected",
  evaluating_decision: "Evaluating Decision",
  simulation_passed: "Simulation Passed",
  execution_submitted: "Execution Submitted",
  execution_verified: "Execution Verified",
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
    case "skipped":
    case "aborted":
      return <span className={`${base} bg-muted text-muted-foreground`}>Skipped</span>;
    default:
      return <span className={`${base} bg-muted text-muted-foreground`}>{estado}</span>;
  }
}

type UiEvent = AgentEvent & { uiEstado: string };

function reconcileEvents(events: AgentEvent[]): UiEvent[] {
  const normalized: UiEvent[] = events.map((e) => ({ ...e, uiEstado: e.estado }));
  const lastByStep = new Map<string, number>();
  const hiddenIndexes = new Set<number>();
  let closedAll = false;

  normalized.forEach((event, idx) => {
    const step = event.paso.toLowerCase();
    const status = String(event.uiEstado).toLowerCase();
    const prevIdx = lastByStep.get(step);
    if (prevIdx !== undefined) {
      const prev = normalized[prevIdx];
      const prevStatus = String(prev.uiEstado).toLowerCase();
      const prevActive = ["starting", "running", "processing", "iniciando"].includes(prevStatus);
      if (prevActive) {
        if (["completed", "success"].includes(status)) hiddenIndexes.add(prevIdx);
        if (["error", "failed", "skipped", "aborted"].includes(status)) hiddenIndexes.add(prevIdx);
      }
    }
    lastByStep.set(step, idx);

    if (step === "decision_final" || step === "execution_final_status") {
      closedAll = true;
      for (let i = 0; i < idx; i += 1) {
        const s = String(normalized[i].uiEstado).toLowerCase();
        if (["starting", "running", "processing", "iniciando"].includes(s)) {
          normalized[i].uiEstado = "completed";
        }
      }
    }
  });

  return normalized.filter((_, i) => !hiddenIndexes.has(i));
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
  if (s === "skipped" || s === "aborted") return "border-border bg-muted/30";
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

function getPhase(paso: string) {
  const p = paso.toLowerCase();
  const analysis = new Set(["analyzing_wallet", "calculating_scores", "classifying_profile", "generating_insight"]);
  const decision = new Set(["evaluating_decision", "x402_validation", "strategy_execution"]);
  const execution = new Set([
    "execution_safety",
    "execution_step",
    "execution_verification",
    "contract_generation",
    "contract_compilation",
    "contract_deployment",
    "contract_active",
    "execution_final_status",
    "execution_lock",
  ]);
  const final = new Set(["decision_final"]);

  if (analysis.has(p)) return "analysis";
  if (decision.has(p)) return "decision";
  if (execution.has(p)) return "execution";
  if (final.has(p)) return "final";
  return "other";
}

function PhaseHeader({ phase }: { phase: string }) {
  const label =
    phase === "analysis"
      ? "Analysis Phase"
      : phase === "decision"
        ? "Decision Phase"
        : phase === "execution"
          ? "Execution Phase"
          : phase === "final"
            ? "Final Outcome"
            : "Updates";

  const tone =
    phase === "analysis"
      ? "text-sky-600 bg-sky-500/5 border-sky-500/15"
      : phase === "decision"
        ? "text-yellow-700 bg-yellow-500/5 border-yellow-500/15"
        : phase === "execution"
          ? "text-green-700 bg-green-500/5 border-green-500/15"
          : phase === "final"
            ? "text-foreground bg-secondary/40 border-border"
            : "text-muted-foreground bg-secondary/40 border-border";

  return (
    <div className={`mt-2 rounded-lg border px-3 py-2 ${tone}`}>
      <div className="text-xs font-semibold uppercase tracking-wider">{label}</div>
    </div>
  );
}

export function AgentTimeline({ events, isStreaming }: AgentTimelineProps) {
  if (events.length === 0) return null;
  const reconciled = useMemo(() => reconcileEvents(events), [events]);

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.3 }}
      className="w-full mt-4"
    >
      <div className="mb-3 flex items-center justify-between">
        <div>
          <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wider">Agent Execution</h2>
          <p className="text-xs text-muted-foreground">Stream progress with quick action states.</p>
        </div>
        <span className="inline-flex items-center gap-1 text-xs font-semibold text-primary"><Sparkles className="h-3.5 w-3.5" /> Live</span>
      </div>

      <div className="bg-card border border-border rounded-xl p-3 space-y-2 max-h-[560px] overflow-y-auto">
        {reconciled.map((event, index) => {
          const stepKey = event.paso.toLowerCase();
          const label = STEP_LABELS[stepKey] || stepKey;
          const isActive =
            event.uiEstado === "iniciando" || event.uiEstado === "processing" || event.uiEstado === "running" || event.uiEstado === "starting";
          const tone = getStepTone(stepKey);
          const toneClasses = getToneClasses(tone, event.uiEstado);
          const phase = getPhase(stepKey);
          const prevPhase = index > 0 ? getPhase(reconciled[index - 1].paso) : null;
          return (
            <div key={event.id}>
              {phase !== prevPhase && <PhaseHeader phase={phase} />}
              <motion.div
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.22, delay: index * 0.04 }}
                className={`rounded-lg border px-3 py-2 ${toneClasses}`}
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">
                    {getStepIcon(event.uiEstado)}
                    <span>{label}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    {getSourceBadge(event.source)}
                    {getStatusBadge(event.uiEstado)}
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
            </div>
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

import { motion } from "framer-motion";
import { Shield, Activity, FileText, Zap, Brain, AlertCircle, CheckCircle2 } from "lucide-react";
import type { AgentResults } from "@/hooks/useAgentSSE";

interface ResultsPanelProps {
  results: AgentResults;
  targetWallet?: string;
  agentWallet?: string;
}

function getRiskColor(score: number | undefined) {
  if (score === undefined) return "text-muted-foreground";
  if (score <= 33) return "text-risk-low";
  if (score <= 66) return "text-risk-medium";
  return "text-risk-high";
}

function getRiskBg(score: number | undefined) {
  if (score === undefined) return "bg-muted";
  if (score <= 33) return "bg-risk-low";
  if (score <= 66) return "bg-risk-medium";
  return "bg-risk-high";
}

function getRiskLabel(score: number | undefined) {
  if (score === undefined) return "N/A";
  if (score <= 33) return "Low";
  if (score <= 66) return "Medium";
  return "High";
}

function ScoreCard({
  icon: Icon,
  label,
  value,
  subtext,
  colorClass,
  delay,
}: {
  icon: React.ElementType;
  label: string;
  value: string | number;
  subtext?: string;
  colorClass?: string;
  delay: number;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay }}
      className="bg-card border border-border rounded-lg p-4 flex flex-col gap-2"
    >
      <div className="flex items-center gap-2 text-muted-foreground">
        <Icon className="h-4 w-4" />
        <span className="text-xs font-medium uppercase tracking-wider">{label}</span>
      </div>
      <div className={`text-2xl font-semibold ${colorClass || "text-foreground"}`}>
        {value}
      </div>
      {subtext && <span className="text-xs text-muted-foreground">{subtext}</span>}
    </motion.div>
  );
}

function normalizeConfidence(confidence: number | undefined) {
  if (confidence === undefined) return undefined;
  if (Number.isNaN(confidence)) return undefined;
  if (confidence > 1) return Math.max(0, Math.min(1, confidence / 100));
  return Math.max(0, Math.min(1, confidence));
}

function ConfidenceBar({ confidence }: { confidence: number | undefined }) {
  const c = normalizeConfidence(confidence);
  if (c === undefined) return null;
  const pct = Math.round(c * 100);
  const filled = Math.round((c * 10));

  return (
    <div className="mt-2 flex items-center justify-between gap-3">
      <div className="flex items-center gap-1.5">
        {Array.from({ length: 10 }).map((_, i) => (
          <div
            key={i}
            className={`h-2 w-2 rounded-sm ${i < filled ? "bg-primary" : "bg-muted"}`}
          />
        ))}
      </div>
      <div className="text-xs font-mono text-muted-foreground">Confidence: {pct}%</div>
    </div>
  );
}

function getDecisionPresentation(results: AgentResults) {
  const code = results.decision_code || results.agent_decision || "";
  const normalized = String(code).toUpperCase();

  const decisionType: Record<string, "system" | "error"> = {
    SYSTEM_BUSY: "system",
    ALREADY_RUNNING: "system",
    ERROR: "error",
  };

  const kind = decisionType[normalized] || "normal";

  if (kind === "system") {
    return {
      title: normalized === "ALREADY_RUNNING" ? "Already Running" : "System Busy",
      subtitle:
        normalized === "ALREADY_RUNNING"
          ? "An execution is already in progress for this wallet."
          : "Agent is currently processing other requests. Retry in a few seconds.",
      tone: "border-yellow-500/20 bg-yellow-500/5",
      icon: <AlertCircle className="h-4 w-4 text-yellow-600" />,
      badge: "SYSTEM",
    };
  }

  if (kind === "error") {
    return {
      title: "Execution Failed",
      subtitle: results.reasoning || results.agent_decision || "An error occurred during execution.",
      tone: "border-destructive/30 bg-destructive/5",
      icon: <AlertCircle className="h-4 w-4 text-destructive" />,
      badge: "ERROR",
    };
  }

  return {
    title: "Agent Decision",
    subtitle: results.reasoning || results.why_not_acting || "Decision computed from on-chain behavioral signals.",
    tone: "border-risk-low/20 bg-risk-low/5",
    icon: <CheckCircle2 className="h-4 w-4 text-risk-low" />,
    badge: "DECISION",
  };
}

function buildAgentConclusion(results: AgentResults) {
  const code = String(results.decision_code || results.agent_decision || "").toUpperCase();
  const c = normalizeConfidence(results.confidence);

  if (code === "SYSTEM_BUSY") {
    return "The agent is currently saturated and cannot start a new run. Please retry shortly.";
  }
  if (code === "ALREADY_RUNNING") {
    return "An agent run is already in progress for this wallet. Wait for completion to avoid duplicated execution.";
  }
  if (code === "ERROR") {
    return "The agent attempted to execute but encountered an error. No unsafe execution should proceed without ESL validation.";
  }
  if (code === "INSUFFICIENT_DATA") {
    return "This wallet does not present sufficient behavioral signals to justify intervention. Monitoring is recommended.";
  }

  if (typeof c === "number" && c < 0.2) {
    return "Confidence is low due to limited observable activity. The agent will prioritize monitoring until stronger signals emerge.";
  }
  if (code === "EXECUTE_ADVANCED") {
    return "Elevated risk indicators detected. The agent will apply mitigations using the Execution Safety Layer before any on-chain action.";
  }
  return "The agent evaluated this wallet and produced a decision based on on-chain behavioral signals and safety constraints.";
}

export function ResultsPanel({ results, targetWallet, agentWallet }: ResultsPanelProps) {
  const analyzedWallet =
    targetWallet ||
    ((results.full_analysis as Record<string, unknown> | undefined)?.wallet as string | undefined) ||
    "No data available yet";
  const executorWallet = agentWallet || "Agent Wallet";

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.5 }}
      className="w-full max-w-2xl mx-auto mt-8"
    >
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
        className="mb-4 bg-card border border-border rounded-xl p-4"
      >
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-foreground font-semibold">
            <Brain className="h-4 w-4" />
            <span>Agent Conclusion</span>
          </div>
          {results.source && (
            <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full border border-border bg-secondary/40 text-muted-foreground uppercase tracking-wider">
              {results.source === "loop" ? "Triggered autonomously" : "Triggered by user"}
            </span>
          )}
        </div>
        <p className="mt-2 text-sm text-muted-foreground">{buildAgentConclusion(results)}</p>
        <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-2 text-[11px]">
          <div className="rounded border border-border bg-secondary/30 p-2">
            <span className="text-muted-foreground">Based on analysis of:</span>{" "}
            <span className="font-mono">{analyzedWallet}</span>
          </div>
          <div className="rounded border border-border bg-secondary/30 p-2">
            <span className="text-muted-foreground">Executed by:</span>{" "}
            <span className="font-mono">{executorWallet}</span>
          </div>
        </div>
        <ConfidenceBar confidence={results.confidence} />
      </motion.div>

      <div className="flex items-center justify-between mb-4">
        <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wider">
          Analysis Results
        </h2>
        <div className="text-xs text-muted-foreground">Context-first view</div>
      </div>

      {(() => {
        const p = getDecisionPresentation(results);
        return (
          <div className={`mb-3 rounded-xl border p-4 ${p.tone}`}>
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-center gap-2">
                {p.icon}
                <div>
                  <div className="text-sm font-semibold text-foreground">{p.title}</div>
                  <div className="text-xs text-muted-foreground mt-0.5">{p.subtitle}</div>
                </div>
              </div>
              <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full border border-border bg-background/40 text-muted-foreground uppercase tracking-wider">
                {p.badge}
              </span>
            </div>
          </div>
        );
      })()}

      <div className="grid grid-cols-2 gap-3">
        <ScoreCard
          icon={Shield}
          label="Risk Score"
          value={results.risk_score ?? "N/A"}
          subtext={getRiskLabel(results.risk_score)}
          colorClass={getRiskColor(results.risk_score)}
          delay={0}
        />
        <ScoreCard
          icon={Activity}
          label="Activity Score"
          value={results.activity_score ?? "N/A"}
          colorClass="text-primary"
          delay={0.1}
        />
        <ScoreCard
          icon={FileText}
          label="Contract Type"
          value={results.contract_type || "N/A"}
          subtext={
            results.contract_type
              ? "Mitigation contract type suggested by the agent."
              : "No contract type identified yet."
          }
          delay={0.2}
        />
        <ScoreCard
          icon={Zap}
          label="Recommended Action"
          value={results.recommended_action || "N/A"}
          subtext={
            results.recommended_action
              ? "Suggested action based on risk and profile."
              : "No action generated yet."
          }
          delay={0.3}
        />
      </div>

      {(results.agent_intent || results.why_not_acting) && (
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, delay: 0.35 }}
          className="mt-3 bg-card border border-border rounded-lg p-4"
        >
          <div className="flex items-center gap-2 text-muted-foreground mb-2">
            <Brain className="h-4 w-4" />
            <span className="text-xs font-medium uppercase tracking-wider">Agent Intent</span>
          </div>
          <p className="text-sm text-foreground">
            {results.agent_intent || "No intent provided by the agent."}
          </p>
          {results.why_not_acting && (
            <div className="mt-3 rounded-md border border-yellow-500/20 bg-yellow-500/5 p-3">
              <div className="text-[10px] font-semibold uppercase tracking-wider text-yellow-700">
                Why NOT acting
              </div>
              <div className="mt-1 text-sm text-yellow-800">{results.why_not_acting}</div>
            </div>
          )}
        </motion.div>
      )}

      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.45 }}
        className="mt-3 bg-card border border-border rounded-lg p-4"
      >
        <div className="text-xs font-medium uppercase tracking-wider text-muted-foreground">Decision Context</div>
        <div className="mt-2 text-sm text-muted-foreground">
          The system analyzed the target wallet behavior and produced a decision code, then applies safeguards before any autonomous execution.
        </div>
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.5 }}
        className="mt-3 bg-card border border-border rounded-lg p-4"
      >
        <div className="text-xs font-medium uppercase tracking-wider text-muted-foreground">Action Scope</div>
        <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2 text-xs">
          <div className="rounded border border-border bg-secondary/30 p-2">
            <div className="font-semibold">Target Wallet</div>
            <div className="text-muted-foreground mt-1">Read-only analysis input.</div>
          </div>
          <div className="rounded border border-border bg-secondary/30 p-2">
            <div className="font-semibold">Agent Wallet</div>
            <div className="text-muted-foreground mt-1">Execution enabled with funded budget.</div>
          </div>
        </div>
      </motion.div>

      {results.agent_decision && (
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, delay: 0.4 }}
          className="mt-3 bg-card border border-border rounded-lg p-4"
        >
          <div className="flex items-center gap-2 text-muted-foreground mb-2">
            <Brain className="h-4 w-4" />
            <span className="text-xs font-medium uppercase tracking-wider">Agent Decision</span>
          </div>
          <div className="flex items-center gap-3">
            <span className="font-mono text-sm font-semibold text-primary">
              {results.agent_decision}
            </span>
            {results.risk_score !== undefined && (
              <div className="flex items-center gap-1.5">
                <div className={`h-2 w-2 rounded-full ${getRiskBg(results.risk_score)}`} />
                <span className={`text-xs font-medium ${getRiskColor(results.risk_score)}`}>
                  {getRiskLabel(results.risk_score)} Risk
                </span>
              </div>
            )}
          </div>
          {results.reasoning && (
            <p className="mt-2 text-sm text-muted-foreground">{results.reasoning}</p>
          )}
        </motion.div>
      )}

    </motion.div>
  );
}

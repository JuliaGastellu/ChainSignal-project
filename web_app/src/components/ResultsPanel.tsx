import { motion } from "framer-motion";
import { Shield, Activity, FileText, Zap, Brain, Copy, Check } from "lucide-react";
import { useState } from "react";
import type { AgentResults } from "@/hooks/useAgentSSE";

interface ResultsPanelProps {
  results: AgentResults;
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

export function ResultsPanel({ results }: ResultsPanelProps) {
  const [copied, setCopied] = useState(false);
  const [showJson, setShowJson] = useState(false);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(JSON.stringify(results.raw || results, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.5 }}
      className="w-full max-w-2xl mx-auto mt-8"
    >
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wider">
          Analysis Results
        </h2>
        <div className="flex items-center gap-2">
          {results.source && (
            <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full border border-border bg-secondary/40 text-muted-foreground uppercase tracking-wider">
              {results.source === "loop" ? "Triggered autonomously" : "Triggered by user"}
            </span>
          )}
          <button
            onClick={() => setShowJson((v) => !v)}
            className="text-xs text-muted-foreground hover:text-foreground transition-colors px-2 py-1 rounded border border-border"
          >
            {showJson ? "Hide" : "Show"} JSON
          </button>
          <button
            onClick={handleCopy}
            className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors px-2 py-1 rounded border border-border"
          >
            {copied ? <Check className="h-3 w-3 text-risk-low" /> : <Copy className="h-3 w-3" />}
            {copied ? "Copied" : "Copy"}
          </button>
        </div>
      </div>

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

      {showJson && results.raw && (
        <motion.pre
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: "auto" }}
          exit={{ opacity: 0, height: 0 }}
          className="mt-3 bg-secondary/50 border border-border rounded-lg p-4 text-xs font-mono text-muted-foreground overflow-x-auto max-h-64 overflow-y-auto"
        >
          {JSON.stringify(results.raw, null, 2)}
        </motion.pre>
      )}
    </motion.div>
  );
}

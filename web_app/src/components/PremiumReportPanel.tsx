import { motion, AnimatePresence } from "framer-motion";
import { 
  Shield, Activity, Zap, Brain, 
  CheckCircle2, Info, ChevronDown, 
  ChevronUp, Code, FileCode, Beaker,
  TrendingUp, Clock, Wallet, BarChart3,
  ArrowRightLeft, Send
} from "lucide-react";
import { useState } from "react";

interface PremiumReportProps {
  report: any;
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

export function PremiumReportPanel({ report }: PremiumReportProps) {
  const [showCode, setShowCode] = useState(false);

  if (!report) return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="w-full max-w-4xl mx-auto space-y-6 mt-8 p-1 rounded-2xl bg-gradient-to-b from-primary/10 to-transparent border border-primary/20 backdrop-blur-sm"
    >
      <div className="bg-card/80 rounded-2xl p-6 shadow-xl border border-white/5">
        {/* Header */}
        <div className="flex items-center justify-between mb-8 pb-4 border-b border-white/5">
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-full bg-primary/20 flex items-center justify-center">
              <Shield className="h-6 w-6 text-primary" />
            </div>
            <div>
              <h2 className="text-xl font-bold text-foreground">Premium On-Chain Report</h2>
              <p className="text-xs text-muted-foreground flex items-center gap-1.5 mt-0.5">
                <CheckCircle2 className="h-3 w-3 text-green-500" /> Verified via Sepolia Middleware
              </p>
            </div>
          </div>
          <div className="text-right">
            <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-1 bg-primary/10 text-primary rounded border border-primary/20">
              License Activated
            </span>
          </div>
        </div>

        {/* Profile Section */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
          <div className="md:col-span-1 space-y-4">
            <div className="flex items-center gap-2 text-muted-foreground">
              <Brain className="h-4 w-4" />
              <span className="text-xs font-bold uppercase tracking-widest">Wallet Profile</span>
            </div>
            <div className="bg-secondary/20 rounded-xl p-4 border border-white/5">
              <div className="text-sm font-bold text-foreground mb-1 uppercase tracking-tight">
                {report.profile.type.replace(/_/g, ' ')}
              </div>
              <p className="text-xs text-muted-foreground line-height-relaxed mb-3">
                {report.profile.description}
              </p>
              <div className="flex flex-wrap gap-1.5">
                {report.profile.signals.map((signal: string, i: number) => (
                  <span key={i} className="text-[9px] bg-primary/5 text-primary-foreground/70 border border-primary/10 px-1.5 py-0.5 rounded">
                    {signal}
                  </span>
                ))}
              </div>
            </div>
          </div>

          {/* Scores Section */}
          <div className="md:col-span-2 space-y-4">
            <div className="flex items-center gap-2 text-muted-foreground">
              <Zap className="h-4 w-4" />
              <span className="text-xs font-bold uppercase tracking-widest">Extended Scores</span>
            </div>
            <div className="grid grid-cols-2 gap-3">
              {[
                { label: "Risk", icon: Shield, data: report.scores.risk, color: getRiskColor(report.scores.risk.value) },
                { label: "Activity", icon: Activity, data: report.scores.activity, color: "text-primary" },
                { label: "DeFi", icon: Beaker, data: report.scores.defi, color: "text-secondary" },
                { label: "Web3 Index", icon: TrendingUp, data: report.scores.web3_index, color: "text-green-400" },
              ].map((score, i) => (
                <div key={i} className="bg-white/5 rounded-xl p-3 border border-white/5 group hover:bg-white/10 transition-all">
                  <div className="flex items-center justify-between mb-1">
                    <score.icon className="h-3 w-3 text-muted-foreground" />
                    <span className="text-[10px] font-medium text-muted-foreground uppercase">{score.label}</span>
                  </div>
                  <div className={`text-xl font-bold ${score.color}`}>
                    {score.data.value}
                  </div>
                  <div className="text-[10px] text-muted-foreground/80 mt-1 leading-tight">
                    {score.data.interpretation}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Metrics Grid */}
        <div className="mb-8 space-y-4">
          <div className="flex items-center gap-2 text-muted-foreground">
            <BarChart3 className="h-4 w-4" />
            <span className="text-xs font-bold uppercase tracking-widest">On-Chain Metrics</span>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
            {[
              { label: "Total Txs", value: report.metrics.total_transactions, icon: Activity },
              { label: "ETH Balance", value: report.metrics.eth_balance.toFixed(3), icon: Wallet },
              { label: "Days Active", value: report.metrics.days_active, icon: Clock },
              { label: "Txs/Day", value: report.metrics.tx_per_day.toFixed(2), icon: TrendingUp },
              { label: "Contract %", value: `${report.metrics.contract_interactions_pct}%`, icon: FileCode },
            ].map((m, i) => (
              <div key={i} className="bg-white/5 rounded-lg p-2.5 border border-white/5 text-center">
                <m.icon className="h-3 w-3 mx-auto text-muted-foreground mb-1.5" />
                <div className="text-xs font-bold text-foreground">{m.value}</div>
                <div className="text-[9px] text-muted-foreground uppercase mt-0.5">{m.label}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Agent Decision */}
        <div className="bg-primary/10 border border-primary/20 rounded-xl p-5 mb-6">
          <div className="flex items-start gap-4">
            <div className="h-8 w-8 rounded-lg bg-primary/20 flex items-center justify-center shrink-0">
              <Brain className="h-5 w-5 text-primary" />
            </div>
            <div>
              <div className="flex items-center gap-2 mb-1">
                <span className="text-[10px] font-bold text-primary uppercase tracking-widest">Agent Reasoning</span>
                <span className="h-1 w-1 rounded-full bg-primary/40"></span>
                <span className="text-[10px] font-bold text-primary-foreground/60 uppercase">{report.agent_decision.decision}</span>
              </div>
              <p className="text-sm font-medium text-foreground leading-relaxed italic">
                "{report.agent_decision.reasoning}"
              </p>
              <div className="mt-3 inline-flex items-center gap-2 px-3 py-1 bg-primary text-primary-foreground text-[11px] font-bold rounded-full uppercase">
                Action: {report.agent_decision.recommended_action}
              </div>
            </div>
          </div>
        </div>

        {/* Financial Actions Section */}
        {report.financial_actions && report.financial_actions.length > 0 && (
          <div className="mb-8 space-y-4">
            <div className="flex items-center gap-2 text-muted-foreground">
              <Zap className="h-4 w-4" />
              <span className="text-xs font-bold uppercase tracking-widest">Autonomous Financial Operations</span>
            </div>
            <div className="grid grid-cols-1 gap-3">
              {report.financial_actions.map((action: any, i: number) => (
                <div key={i} className="flex items-center gap-4 p-4 bg-green-500/5 border border-green-500/20 rounded-xl">
                  <div className="h-10 w-10 rounded-full bg-green-500/10 flex items-center justify-center shrink-0">
                    {action.type === 'preventive_swap' ? <ArrowRightLeft className="h-5 w-5 text-green-500" /> : <Send className="h-5 w-5 text-green-500" />}
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-bold text-foreground capitalize">{action.type.replace(/_/g, ' ')}</span>
                      <span className="text-[10px] bg-green-500/20 text-green-400 px-2 py-0.5 rounded-full font-bold uppercase tracking-tighter">
                        {action.status}
                      </span>
                    </div>
                    <p className="text-xs text-muted-foreground mt-0.5">{action.detail}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Contract Section */}
        {report.contract && (
          <div className="space-y-3">
            <button
              onClick={() => setShowCode(!showCode)}
              className="w-full h-12 flex items-center justify-between px-5 bg-secondary/30 hover:bg-secondary/40 border border-secondary/20 rounded-xl transition-all group"
            >
              <div className="flex items-center gap-3">
                <Code className="h-5 w-5 text-secondary" />
                <div className="text-left">
                  <div className="text-xs font-bold text-foreground">Mitigation Contract Generated</div>
                  <div className="text-[10px] text-muted-foreground uppercase tracking-tight">Type: {report.contract.type}</div>
                </div>
              </div>
              {showCode ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            </button>

            <AnimatePresence>
              {showCode && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: "auto", opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  className="overflow-hidden"
                >
                  <div className="bg-slate-900 rounded-xl border border-white/5 overflow-hidden">
                    <div className="flex items-center justify-between px-4 py-2 border-b border-white/5 bg-slate-950/50">
                      <span className="text-[10px] font-mono text-muted-foreground">security_mitigation.sol</span>
                      <span className="text-[10px] font-mono text-secondary-foreground/50 bg-secondary/10 px-1.5 py-0.5 rounded uppercase">Solidity v0.8.20</span>
                    </div>
                    <pre className="p-4 text-xs font-mono text-blue-300/80 overflow-x-auto max-h-96 leading-relaxed bg-slate-950/20">
                      {report.contract.source_code}
                    </pre>
                    <div className="px-4 py-2 bg-slate-950/50 border-t border-white/5 flex gap-4">
                      <div className="text-[9px] font-mono text-muted-foreground">
                        ABI: <span className="text-green-400">AVAILABLE</span>
                      </div>
                      <div className="text-[9px] font-mono text-muted-foreground">
                        Bytecode: <span className="text-green-400">AVAILABLE</span>
                      </div>
                      <div className="ml-auto text-[9px] font-mono text-primary animate-pulse">
                        STATUS: {report.contract.status.toUpperCase()}
                      </div>
                    </div>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        )}
      </div>
    </motion.div>
  );
}

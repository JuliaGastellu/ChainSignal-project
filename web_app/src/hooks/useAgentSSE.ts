import { useState, useCallback, useRef } from "react";

export interface AgentEvent {
  id: string;
  paso: string;
  estado: string;
  detalle: string;
  timestamp: number;
  source?: "api" | "loop";
  data?: Record<string, unknown>;
}

export interface AgentResults {
  risk_score?: number;
  activity_score?: number;
  contract_type?: string;
  recommended_action?: string;
  agent_decision?: string;
  agent_intent?: string;
  why_not_acting?: string;
  source?: "api" | "loop";
  decision_code?: string;
  reasoning?: string;
  perfil?: string;
  insight?: string;
  raw?: Record<string, unknown>;
}

type AgentStatus = "idle" | "connecting" | "streaming" | "completed" | "error";

export const API_BASE = window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1" || window.location.hostname === "::"
  ? ""
  : "https://chainsignal-project.onrender.com";

export function useAgentSSE() {
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [results, setResults] = useState<AgentResults | null>(null);
  const [status, setStatus] = useState<AgentStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const [simulationMode, setSimulationMode] = useState(false);
  const eventSourceRef = useRef<EventSource | null>(null);
  const eventCountRef = useRef(0);

  const reset = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    setEvents([]);
    setResults(null);
    setStatus("idle");
    setError(null);
    setSimulationMode(false);
    eventCountRef.current = 0;
  }, []);

  const execute = useCallback((wallet: string) => {
    reset();
    setStatus("connecting");

    const url = `${API_BASE}/run-agent/${wallet}`;

    try {
      const es = new EventSource(url);
      eventSourceRef.current = es;

      es.onopen = () => {
        setStatus("streaming");
      };

      es.onmessage = (event) => {
        let parsed: Record<string, unknown> | null = null;
        try {
          parsed = JSON.parse(event.data);
        } catch {
          parsed = null;
        }

        const data: Record<string, unknown> = parsed || { texto: event.data };
        const paso = String(data.paso || data.step || "message");
        const estado = String(data.estado || data.status || "processing");
        const detalle = String(
          data.detalle || data.detail || data.message || data.texto || ""
        );
        const sourceRaw = String((data.source as string | undefined) || "api").toLowerCase();
        const source: "api" | "loop" = sourceRaw === "loop" ? "loop" : "api";

        const agentEvent: AgentEvent = {
          id: `evt-${eventCountRef.current++}`,
          paso,
          estado,
          detalle,
          timestamp: Date.now(),
          source,
          data,
        };

        setEvents((prev) => [...prev, agentEvent]);

        setResults((prev) => {
          const nextResults: AgentResults = {
            ...prev,
            raw: data,
          };

          const payload = (typeof data.data === "object" && data.data !== null) 
            ? (data.data as Record<string, unknown>) 
            : data;

          // 1. Scoring step
          if (paso === "calculating_scores") {
            const risk = Number(payload.risk ?? payload.risk_score);
            const activity = Number(payload.activity ?? payload.activity_score);
            if (!Number.isNaN(risk)) nextResults.risk_score = risk;
            if (!Number.isNaN(activity)) nextResults.activity_score = activity;
          }

          // 2. Profile step
          if (paso === "classifying_profile") {
            const profile = payload.type || payload.profile || payload.tipo || payload.perfil;
            if (typeof profile === "string") nextResults.perfil = profile;
          }

          // 3. Insight step
          if (paso === "generating_insight") {
            const parts: string[] = [];
            const type = payload.type || payload.tipo;
            const recAction = payload.recommended_action || payload.accion_recomendada;
            
            if (typeof type === "string") {
              parts.push(`Type: ${type}`);
              if (!nextResults.contract_type) nextResults.contract_type = type;
            }
            if (typeof recAction === "string") {
              parts.push(`Action: ${recAction}`);
            }
            if (parts.length) nextResults.insight = parts.join(" · ");
            else if (detalle) nextResults.insight = detalle;
          }

          // 4. Decision step
          if (paso === "evaluating_decision") {
            if (typeof payload.agent_intent === "string") nextResults.agent_intent = payload.agent_intent;
            if (typeof payload.decision === "string") nextResults.decision_code = payload.decision;
            if (typeof payload.reasoning === "string") nextResults.reasoning = payload.reasoning;
            if (typeof payload.decision === "string") nextResults.agent_decision = payload.decision;
          }

          // 5. Final/Result step
          if (["final_decision", "result_final"].includes(paso) || paso === "decision_final") {
            nextResults.agent_decision = detalle || nextResults.agent_decision;
            if (typeof payload.decision === "string") nextResults.agent_decision = payload.decision;
            if (typeof payload.reasoning === "string") nextResults.reasoning = payload.reasoning;
            if (typeof payload.decision === "string") nextResults.decision_code = payload.decision;
            if (typeof detalle === "string" && detalle.toLowerCase().includes("agent decided not to act")) {
              nextResults.why_not_acting = detalle;
            }
          }

          // 6. Active Contract step
          if (paso === "contract_active" || paso === "contrato_activo") {
            if (typeof payload.address === "string") nextResults.contract_type = payload.address;
          }

          // Global overrides from payload
          const finalRecAction = payload.recommended_action || payload.accion_recomendada;
          const finalContractType = payload.contract_type || payload.tipo_contrato;

          if (typeof finalRecAction === "string") {
            nextResults.recommended_action = finalRecAction;
          }
          if (typeof finalContractType === "string") {
            nextResults.contract_type = finalContractType;
          }
          if (typeof payload.risk === "number") nextResults.risk_score = payload.risk;
          if (typeof payload.activity === "number") nextResults.activity_score = payload.activity;
          nextResults.source = source;

          return nextResults;
        });

        const finalPuntos = [
          "decision_final", "final_decision", "result_final", "resultado_final", 
          "contract_active", "financial_operation",
          "execution_final_status",
          "contract_generation", "contract_compilation", 
          "contract_deployment",
          "execution_verification"
        ];
        
        const isCompleted = estado === "completed";
        const isError = estado === "error" || estado === "failed";

        const systemBusy = paso === "decision_final" && typeof payload.decision === "string" && payload.decision === "SYSTEM_BUSY";

        if (systemBusy) {
          setStatus("error");
          setError(detalle || "System busy, retrying...");
          if (eventSourceRef.current) {
            eventSourceRef.current.close();
            eventSourceRef.current = null;
          }
          return;
        }

        if (finalPuntos.includes(paso) && isCompleted) {
          setStatus("completed");
          setError(null);
          if (eventSourceRef.current) {
            eventSourceRef.current.close();
            eventSourceRef.current = null;
          }
        } else if (isError) {
          setStatus("error");
          setError(detalle || "Error during execution.");
          if (eventSourceRef.current) {
            eventSourceRef.current.close();
            eventSourceRef.current = null;
          }
        }
      };

      es.onerror = () => {
        if (eventSourceRef.current !== es) return;
        if (es.readyState === EventSource.CLOSED) {
          // El stream se cerró al terminar.
          if (status !== "completed") setStatus("completed");
          setError(null);
          return;
        }
        if (status !== "completed") {
          setError("Connection lost. The API may be unavailable.");
          setStatus("error");
          setSimulationMode(true);
        }
      };
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to connect");
      setStatus("error");
      setSimulationMode(true);
    }
  }, [reset, status]);

  return { events, results, status, error, simulationMode, execute, reset };
}

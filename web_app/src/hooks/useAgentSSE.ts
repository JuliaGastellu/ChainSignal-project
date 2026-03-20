import { useState, useCallback, useRef } from "react";

export interface AgentEvent {
  id: string;
  paso: string;
  estado: string;
  detalle: string;
  timestamp: number;
  data?: Record<string, unknown>;
}

export interface AgentResults {
  risk_score?: number;
  activity_score?: number;
  contract_type?: string;
  recommended_action?: string;
  agent_decision?: string;
  perfil?: string;
  insight?: string;
  raw?: Record<string, unknown>;
}

type AgentStatus = "idle" | "connecting" | "streaming" | "completed" | "error";

const API_BASE = "https://chainsignal-project.onrender.com";

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

    const url = `${API_BASE}/ejecutar-agente/${wallet}`;

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
        const paso = String(data.paso || data.step || "mensaje");
        const estado = String(data.estado || data.status || "procesando");
        const detalle = String(
          data.detalle || data.detail || data.message || data.texto || ""
        );

        const agentEvent: AgentEvent = {
          id: `evt-${eventCountRef.current++}`,
          paso,
          estado,
          detalle,
          timestamp: Date.now(),
          data,
        };

        setEvents((prev) => [...prev, agentEvent]);

        setResults((prev) => {
          const nextResults: AgentResults = {
            ...prev,
            raw: data,
          };

          if (paso === "calculando_scores" || paso === "calculating_scores") {
            const payload = (typeof data.data === "object" && data.data !== null) ? (data.data as Record<string, unknown>) : data;
            const risk = Number(payload.risk ?? payload.score_riesgo ?? payload.risk_score);
            const activity = Number(payload.activity ?? payload.score_actividad ?? payload.activity_score);
            if (!Number.isNaN(risk)) nextResults.risk_score = risk;
            if (!Number.isNaN(activity)) nextResults.activity_score = activity;
          }

          if (paso === "clasificando_perfil" || paso === "classifying_profile") {
            if (typeof data.data === "object" && data.data !== null) {
              const perfil = (data.data as Record<string, unknown>).tipo;
              if (typeof perfil === "string") nextResults.perfil = perfil;
            }
          }

          if (paso === "generando_insight" || paso === "generating_insight") {
            if (typeof data.data === "object" && data.data !== null) {
              const insightData = data.data as Record<string, unknown>;
              const parts: string[] = [];
              if (typeof insightData.tipo === "string") parts.push(`Tipo: ${insightData.tipo}`);
              if (typeof insightData.accion_recomendada === "string")
                parts.push(`Acción: ${insightData.accion_recomendada}`);
              if (parts.length) nextResults.insight = parts.join(" · ");
            }
            if (detalle) nextResults.insight = detalle;
          }

          if (paso === "evaluando_decision" || paso === "evaluating_decision") {
            if (typeof data.data === "object" && data.data !== null) {
              const d = data.data as Record<string, unknown>;
              if (typeof d.decision === "string") nextResults.agent_decision = d.decision;
              if (typeof d.reasoning === "string") nextResults.agent_decision = d.reasoning;
            }
          }

          if (["decision_final", "final_decision", "resultado_final"].includes(paso)) {
            nextResults.agent_decision = detalle || nextResults.agent_decision;
          }

          if (paso === "contrato_activo" || paso === "contract_active") {
            if (typeof data.data === "object" && data.data !== null) {
              const d = data.data as Record<string, unknown>;
              if (typeof d.address === "string") nextResults.contract_type = d.address;
            }
          }

          if (typeof data.accion_recomendada === "string") {
            nextResults.recommended_action = data.accion_recomendada;
          }
            if (typeof data.data === "object" && data.data !== null) {
              const payload = data.data as Record<string, unknown>;
              if (typeof payload.accion_recomendada === "string") {
                nextResults.recommended_action = payload.accion_recomendada;
              }
              if (typeof payload.decision === "string") {
                nextResults.agent_decision = payload.decision;
              }
              if (!nextResults.contract_type && typeof payload.tipo_contrato === "string") {
                nextResults.contract_type = payload.tipo_contrato;
              }
            }

          return nextResults;
        });

        const finalPuntos = ["decision_final", "result_final", "resultado_final", "contrato_activo", "operacion_financiera", "generando_contrato", "compilando_contrato", "deployando_contrato"];
        if (finalPuntos.includes(paso) && estado === "completado") {
          setStatus("completed");
          setError(null);
          if (eventSourceRef.current) {
            eventSourceRef.current.close();
            eventSourceRef.current = null;
          }
        } else if (estado === "error" || estado === "failed") {
          setStatus("error");
          setError(detalle || "Error durante la ejecución.");
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
  }, [reset]);

  return { events, results, status, error, simulationMode, execute, reset };
}

// Tipos de las respuestas de la API que usa la interfaz. Reflejan los contratos
// de api/rutas_org.py; los montos llegan como texto decimal para no perder precisión.

export type Rol = "owner" | "operator" | "viewer";
export type EstadoCalidad = "FRESH" | "STALE" | "PARTIAL" | "UNAVAILABLE";
export type Severidad = "low" | "medium" | "high" | "critical";
export type EstadoIncidente = "open" | "acknowledged" | "resolved";

export interface Resumen {
  organization: { id: string; name: string; is_demo: boolean; expires_at: number | null };
  accounts: number;
  accounts_by_data_quality: Record<string, number>;
  active_incidents: number;
  active_incidents_by_severity: Partial<Record<Severidad, number>>;
  enabled_policies: number;
  channels: number;
  verified_channels: number;
  last_evaluation_at: number | null;
  checklist: {
    account_added: boolean;
    first_snapshot: boolean;
    policy_created: boolean;
    channel_verified: boolean;
    incident_reviewed: boolean;
  };
}

export interface Cuenta {
  id: string;
  chain_id: number;
  address: string;
  label: string | null;
  priority: "high" | "medium" | "low";
  interval_seconds: number;
  relationship: "observed";
  created_at: number;
  last_evaluation_at: number | null;
  last_data_quality: EstadoCalidad | null;
}

export interface ActivoPosicion {
  asset: string;
  symbol: string;
  decimals: number;
  supplied: string;
  stable_debt: string;
  variable_debt: string;
  used_as_collateral: boolean;
  price_base: string;
  oracle_source: string;
  ltv_pct: string;
  liquidation_threshold_pct: string;
}

export interface Posicion {
  account_id: string;
  read_only: true;
  schema: string;
  protocol: string;
  market: string;
  chain_id: number;
  user: string;
  block: { number: number; hash: string; timestamp: number } | null;
  data_quality: { status: EstadoCalidad; reason: string; detail: string };
  status: "ACTIVE" | "COLLATERAL_ONLY" | "NO_POSITION" | "UNKNOWN";
  collateral_base: string | null;
  debt_base: string | null;
  available_borrows_base: string | null;
  health_factor: string | null;
  no_debt: boolean | null;
  liquidation_threshold_pct: string | null;
  ltv_pct: string | null;
  emode_category: number | null;
  assets: ActivoPosicion[];
  unread_reserves: string[];
  reconciliation: Record<string, unknown>;
  limitations: string[];
  read_at: number | null;
  synthetic: boolean;
}

export interface Incidente {
  id: string;
  account_id: string;
  policy_id: string;
  policy_version: number;
  rule_type: "health_factor_below" | "debt_change" | "stale_data";
  status: EstadoIncidente;
  severity: Severidad;
  escalation_level: number;
  data_quality: string;
  opened_at: number;
  escalated_at: number | null;
  acknowledged_at: number | null;
  acknowledged_by_user_id: string | null;
  resolved_at: number | null;
  resolved_by_user_id: string | null;
  resolution: string | null;
  resolution_note: string | null;
  last_evaluated_at: number;
  last_observed: Record<string, unknown>;
}

export interface Evidencia {
  id: number;
  kind: "opening" | "escalation" | "resolution" | "correction";
  snapshot_id: number | null;
  block_number: number | null;
  block_hash: string | null;
  observed: Record<string, unknown>;
  data_quality: string;
  note: string | null;
  corrects_evidence_id: number | null;
  created_at: number;
  created_by_user_id: string | null;
}

export interface IncidenteDetalle extends Incidente {
  evidence: Evidencia[];
  alerts: { id: string; kind: string; severity: Severidad; created_at: number }[];
  deliveries: { alert_id: string; channel_id: string; status: string; attempts: number; sent_at: number | null; last_error: string | null }[];
}

export type EstadoSuscripcion = "trialing" | "active" | "past_due" | "canceled" | "expired" | "demo" | "none";

export interface Suscripcion {
  plan: {
    id: string;
    name: string;
    guided_onboarding: boolean;
    reference_price_usd_per_month: string;
    price_is_hypothesis: boolean;
    billing: "assisted_invoice";
  };
  status: EstadoSuscripcion;
  service_active: boolean;
  is_demo: boolean;
  trial_ends_at: number | null;
  current_period_end: number | null;
  grace_ends_at: number | null;
  cancel_at_period_end: boolean;
  canceled_at: number | null;
  limits: { max_accounts: number; min_interval_seconds: number; chains: number[]; markets: string[] };
  usage: { accounts: number };
  confirmed_payments: { source: "manual" | "webhook"; period_start: number; period_end: number; amount_usd: string }[];
  server_time: number;
}

export interface Explicacion {
  incident_id: string;
  source: "template" | "model";
  model: string | null;
  explanation: { summary: string; statements: { text: string; refs: string[] }[]; caveats: string[] };
  validation_errors: string[];
  fallback_reason: string | null;
  cost_usd: string;
  created_at: number | null;
}

export interface Politica {
  id: string;
  account_id: string | null;
  name: string;
  rule: Record<string, unknown> & { type: string; severity: Severidad };
  version: number;
  enabled: boolean;
  created_at: number;
  updated_at: number;
}

export interface Canal {
  id: string;
  kind: "sandbox" | "webhook";
  name: string;
  config: Record<string, unknown>;
  enabled: boolean;
  verified_at: number | null;
  created_at: number;
}

export interface Miembro {
  membership_id: string;
  user_id: string;
  email: string;
  role: Rol;
  created_at: number;
}

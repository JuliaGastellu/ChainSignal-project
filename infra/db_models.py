"""Modelos ORM del estado durable de ChainSignal.

Estas tablas reemplazan los JSON anteriores:

  storage/plans/<fingerprint>/plan.json + journal.log
      -> execution_plans, execution_plan_events

  executions.json
      -> executions

  storage/agent_budget.json
      -> agent_budgets, processed_funding_txs

Los locks (storage/locks/ en execution_guard/lock_manager.py y el lock por
plan de execution_guard/persistence.py) siguen en archivos.
"""
from sqlalchemy import (
    text,
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
)

from infra.db import Base


class ExecutionPlanRecord(Base):
    """Una fila por plan, con su fingerprint determinístico como clave.

    El fingerprint ya era la clave de hecho en disco (el nombre del directorio
    en storage/plans/); aquí solo formalizo ese invariante.
    """

    __tablename__ = "execution_plans"

    fingerprint = Column(String, primary_key=True)
    wallet = Column(String, nullable=False, index=True)
    risk_score = Column(Integer, nullable=False)
    block_number = Column(Integer, nullable=False)
    lifecycle = Column(String, nullable=False, index=True)
    actions = Column(JSON, nullable=False)
    context = Column(JSON, nullable=False)
    recovery = Column(JSON, nullable=False)
    created_at = Column(Float, nullable=False)
    expires_at = Column(Float, nullable=False)
    updated_at = Column(Float, nullable=False)


class ExecutionPlanEventRecord(Base):
    """Journal de solo agregado con los eventos de ciclo de vida de un plan (reemplaza journal.log)."""

    __tablename__ = "execution_plan_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    fingerprint = Column(String, nullable=False, index=True)
    timestamp = Column(Float, nullable=False)
    event = Column(String, nullable=False)
    data = Column(JSON, nullable=True)


class ExecutionRecord(Base):
    """Una fila por intento de ejecución del agente (reemplaza executions.json)."""

    __tablename__ = "executions"

    id = Column(String, primary_key=True)
    timestamp = Column(String, nullable=False)
    cycle = Column(Integer, nullable=False, index=True)
    wallet = Column(String, nullable=False, index=True)
    decision = Column(String, nullable=True)
    threat_score = Column(Float, nullable=True)
    action_type = Column(String, nullable=True)
    tx_hash = Column(String, nullable=True)
    contract_address = Column(String, nullable=True)
    status = Column(String, nullable=False)
    error = Column(String, nullable=True)


class AgentBudgetRecord(Base):
    """Una fila por presupuesto contable de wallet seguida (reemplaza el dict
    "budgets" de storage/agent_budget.json).

    Guarda solo el saldo propio de cada wallet, nunca el total on-chain de la
    wallet compartida del agente (ver
    services/agent_budget_service.py::get_effective_balance_eth).
    """

    __tablename__ = "agent_budgets"

    wallet = Column(String, primary_key=True)
    agent_wallet = Column(String, nullable=True)
    balance_eth = Column(Float, nullable=False, default=0.0)
    spent_eth = Column(Float, nullable=False, default=0.0)
    created_at = Column(Float, nullable=True)
    updated_at = Column(Float, nullable=True)
    last_funding_tx = Column(String, nullable=True)
    last_funding_amount_eth = Column(Float, nullable=False, default=0.0)


class BudgetConsumptionRecord(Base):
    """Una fila por fingerprint cuyo consumo de presupuesto ya apliqué. Con el
    fingerprint como clave primaria, AgentBudgetService.consume() es
    idempotente por intención: un segundo consume() del mismo plan no
    descuenta dos veces.
    """

    __tablename__ = "budget_consumptions"

    fingerprint = Column(String, primary_key=True)
    wallet = Column(String, nullable=False, index=True)
    amount_eth = Column(Float, nullable=False)
    timestamp = Column(Float, nullable=False)


class ProcessedFundingTxRecord(Base):
    """Una fila por transacción de fondeo ya acreditada (reemplaza el dict
    "processed_txs" de storage/agent_budget.json).

    El tx_hash como clave primaria convierte la deduplicación existente en una
    restricción real de la base.
    """

    __tablename__ = "processed_funding_txs"

    tx_hash = Column(String, primary_key=True)
    wallet = Column(String, nullable=False, index=True)
    funded_eth = Column(Float, nullable=False)
    timestamp = Column(Float, nullable=False)


# --- Identidad y recursos por organización (E02) ------------------------------
#
# Cada recurso privado lleva organization_id. Las referencias entre recursos de
# una organización usan claves foráneas compuestas (id, organization_id), así la
# base rechaza que una política apunte a una cuenta de otra organización aunque
# el código tenga un error. Uso epoch en segundos (Float) como el estado
# heredado, para comparar igual en SQLite y PostgreSQL.

ROLES = ("owner", "operator", "viewer")
_CHECK_ROL = "role IN ('owner', 'operator', 'viewer')"


class OrganizationRecord(Base):
    __tablename__ = "organizations"

    id = Column(String(32), primary_key=True)
    name = Column(String(200), nullable=False)
    created_at = Column(Float, nullable=False)
    # Demo aislada (E06): datos sintéticos, sin lecturas reales, con vencimiento.
    is_demo = Column(Boolean, nullable=False, default=False)
    expires_at = Column(Float, nullable=True)


class UserRecord(Base):
    """Persona que inicia sesión. Su email no implica control de ninguna wallet."""

    __tablename__ = "users"

    id = Column(String(32), primary_key=True)
    email = Column(String(320), nullable=False, unique=True)
    password_hash = Column(String(512), nullable=False)
    created_at = Column(Float, nullable=False)
    disabled_at = Column(Float, nullable=True)


class MembershipRecord(Base):
    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint("organization_id", "user_id", name="uq_memberships_org_user"),
        CheckConstraint(_CHECK_ROL, name="ck_memberships_role"),
    )

    id = Column(String(32), primary_key=True)
    organization_id = Column(String(32), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(32), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(16), nullable=False)
    created_at = Column(Float, nullable=False)


class InvitationRecord(Base):
    """Invitación de un solo uso. Guardo solo el hash del token."""

    __tablename__ = "invitations"
    __table_args__ = (CheckConstraint(_CHECK_ROL, name="ck_invitations_role"),)

    id = Column(String(32), primary_key=True)
    organization_id = Column(String(32), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    email = Column(String(320), nullable=False)
    role = Column(String(16), nullable=False)
    token_hash = Column(String(64), nullable=False, unique=True)
    invited_by_user_id = Column(String(32), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(Float, nullable=False)
    expires_at = Column(Float, nullable=False)
    accepted_at = Column(Float, nullable=True)
    accepted_by_user_id = Column(String(32), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    revoked_at = Column(Float, nullable=True)


class SessionRecord(Base):
    """Sesión de navegador. Guardo hashes del token y del token CSRF, nunca los valores."""

    __tablename__ = "sessions"

    id = Column(String(32), primary_key=True)
    user_id = Column(String(32), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = Column(String(64), nullable=False, unique=True)
    csrf_hash = Column(String(64), nullable=False)
    created_at = Column(Float, nullable=False)
    expires_at = Column(Float, nullable=False)
    revoked_at = Column(Float, nullable=True)
    last_seen_at = Column(Float, nullable=True)


class MonitoredAccountRecord(Base):
    """Dirección que una organización observa. Observar no es controlar fondos."""

    __tablename__ = "monitored_accounts"
    __table_args__ = (
        UniqueConstraint("organization_id", "chain_id", "address", name="uq_accounts_org_chain_address"),
        UniqueConstraint("id", "organization_id", name="uq_accounts_id_org"),
        CheckConstraint("priority IN ('high', 'medium', 'low')", name="ck_accounts_priority"),
    )

    id = Column(String(32), primary_key=True)
    organization_id = Column(String(32), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    chain_id = Column(Integer, nullable=False)
    address = Column(String(42), nullable=False)
    label = Column(String(200), nullable=True)
    priority = Column(String(8), nullable=False)
    interval_seconds = Column(Integer, nullable=False)
    created_by_user_id = Column(String(32), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(Float, nullable=False)
    last_evaluation_at = Column(Float, nullable=True)
    last_risk_score = Column(Integer, nullable=True)
    last_decision = Column(String(32), nullable=True)
    # Calidad de los datos de la última evaluación (E03): FRESH, STALE, PARTIAL o UNAVAILABLE.
    last_data_quality = Column(String(16), nullable=True)
    # Última lectura FRESH (E05): la usa la regla de dato atrasado.
    last_fresh_at = Column(Float, nullable=True)


class AlertPolicyRecord(Base):
    __tablename__ = "alert_policies"
    __table_args__ = (
        UniqueConstraint("id", "organization_id", name="uq_policies_id_org"),
        ForeignKeyConstraint(
            ["account_id", "organization_id"],
            ["monitored_accounts.id", "monitored_accounts.organization_id"],
            name="fk_policies_account_same_org",
            ondelete="CASCADE",
        ),
    )

    id = Column(String(32), primary_key=True)
    organization_id = Column(String(32), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    account_id = Column(String(32), nullable=True)
    name = Column(String(200), nullable=False)
    rule = Column(JSON, nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)
    created_by_user_id = Column(String(32), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(Float, nullable=False)
    updated_at = Column(Float, nullable=False)
    # Versión vigente de la regla (E05); el historial vive en alert_policy_versions.
    current_version = Column(Integer, nullable=False, default=1)


class OrgEventRecord(Base):
    """Evento de una organización. Su id es el cursor del stream SSE."""

    __tablename__ = "org_events"
    __table_args__ = (Index("ix_org_events_org_id_id", "organization_id", "id"),)

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    organization_id = Column(String(32), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    type = Column(String(64), nullable=False)
    payload = Column(JSON, nullable=False)
    actor_user_id = Column(String(32), nullable=True)
    created_at = Column(Float, nullable=False)


# --- Datos on-chain ingeridos (E03) -------------------------------------------
#
# Son datos públicos de la cadena, compartidos entre organizaciones, indexados
# por (chain_id, address). Guardo montos enteros como texto decimal para no
# perder precisión en SQLite; PostgreSQL los recibe igual.


class ChainTransactionRecord(Base):
    __tablename__ = "chain_transactions"
    __table_args__ = (Index("ix_chain_tx_cuenta_bloque", "chain_id", "address", "stream", "block_number"),)

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    chain_id = Column(Integer, nullable=False)
    address = Column(String(42), nullable=False)
    stream = Column(String(16), nullable=False)
    block_number = Column(BigInteger, nullable=False)
    block_hash = Column(String(66), nullable=True)
    tx_hash = Column(String(66), nullable=False)
    timestamp = Column(BigInteger, nullable=False)
    from_addr = Column(String(42), nullable=False)
    to_addr = Column(String(42), nullable=False)
    value_raw = Column(String(80), nullable=False)
    gas_used = Column(BigInteger, nullable=True)
    is_error = Column(Boolean, nullable=False, default=False)
    is_contract_call = Column(Boolean, nullable=False, default=False)
    token_contract = Column(String(42), nullable=True)
    token_decimals = Column(Integer, nullable=True)
    token_symbol = Column(String(32), nullable=True)


class IngestionCheckpointRecord(Base):
    """Hasta dónde ingerí, con qué bloque de referencia y qué ventana cubro."""

    __tablename__ = "ingestion_checkpoints"
    __table_args__ = (UniqueConstraint("chain_id", "address", "stream", name="uq_checkpoint_cuenta_flujo"),)

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    chain_id = Column(Integer, nullable=False)
    address = Column(String(42), nullable=False)
    stream = Column(String(16), nullable=False)
    covered_from_block = Column(BigInteger, nullable=True)
    confirmed_block = Column(BigInteger, nullable=True)
    confirmed_block_hash = Column(String(66), nullable=True)
    complete_history = Column(Boolean, nullable=False, default=False)
    reference_block = Column(BigInteger, nullable=True)
    reference_block_hash = Column(String(66), nullable=True)
    reference_block_timestamp = Column(BigInteger, nullable=True)
    provider = Column(String(32), nullable=False)
    synced_at = Column(Float, nullable=True)
    pages = Column(Integer, nullable=False, default=0)


# --- Snapshots de posiciones (E04) --------------------------------------------
#
# Datos públicos de la cadena leídos a un bloque explícito. Guardo los enteros
# del contrato como texto decimal para no perder precisión; schema_version
# identifica el formato del snapshot.


class PositionSnapshotRecord(Base):
    __tablename__ = "position_snapshots"
    __table_args__ = (
        # Incluyo el hash: tras un reorg, el mismo número de bloque es otro bloque.
        UniqueConstraint("chain_id", "protocol", "market", "user_address", "block_number", "block_hash", "is_synthetic",
                         name="uq_snapshot_posicion_bloque_hash"),
        Index("ix_snapshots_usuario", "chain_id", "user_address", "block_number"),
    )

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    schema_version = Column(String(32), nullable=False)
    chain_id = Column(Integer, nullable=False)
    protocol = Column(String(32), nullable=False)
    market = Column(String(64), nullable=False)
    user_address = Column(String(42), nullable=False)
    block_number = Column(BigInteger, nullable=False)
    block_hash = Column(String(66), nullable=False)
    block_timestamp = Column(BigInteger, nullable=False)
    quality = Column(String(16), nullable=False)
    quality_reason = Column(String(32), nullable=False)
    quality_detail = Column(String(300), nullable=True)
    status = Column(String(16), nullable=False)
    total_collateral_base = Column(String(80), nullable=False)
    total_debt_base = Column(String(80), nullable=False)
    available_borrows_base = Column(String(80), nullable=False)
    current_liquidation_threshold_bps = Column(Integer, nullable=False)
    ltv_bps = Column(Integer, nullable=False)
    health_factor_wad = Column(String(80), nullable=False)
    base_currency_unit = Column(String(80), nullable=False)
    base_currency = Column(String(42), nullable=False)
    emode_category = Column(Integer, nullable=False)
    contracts = Column(JSON, nullable=False)
    reconciliation = Column(JSON, nullable=False)
    limitations = Column(JSON, nullable=False)
    unread_reserves = Column(JSON, nullable=False)
    read_at = Column(Float, nullable=False)
    # Sintético solo en la demo y en pruebas; nunca lo sirvo como lectura real.
    is_synthetic = Column(Boolean, nullable=False, default=False)


class PositionSnapshotAssetRecord(Base):
    __tablename__ = "position_snapshot_assets"
    __table_args__ = (UniqueConstraint("snapshot_id", "asset", name="uq_snapshot_activo"),)

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    snapshot_id = Column(BigInteger().with_variant(Integer, "sqlite"), ForeignKey("position_snapshots.id", ondelete="CASCADE"), nullable=False, index=True)
    asset = Column(String(42), nullable=False)
    symbol = Column(String(32), nullable=False)
    decimals = Column(Integer, nullable=False)
    a_token_balance = Column(String(80), nullable=False)
    stable_debt = Column(String(80), nullable=False)
    variable_debt = Column(String(80), nullable=False)
    used_as_collateral = Column(Boolean, nullable=False)
    price_base = Column(String(80), nullable=False)
    oracle_source = Column(String(42), nullable=False)
    ltv_bps = Column(Integer, nullable=False)
    liquidation_threshold_bps = Column(Integer, nullable=False)


# --- Monitoreo, incidentes y notificaciones (E05) -------------------------------

_ACTIVOS = "status IN ('pending', 'running')"
_ABIERTOS = "status IN ('open', 'acknowledged')"


class AlertPolicyVersionRecord(Base):
    """Versión inmutable de una regla: cada incidente apunta a la versión que lo abrió."""

    __tablename__ = "alert_policy_versions"
    __table_args__ = (
        UniqueConstraint("policy_id", "version", name="uq_policy_version"),
        ForeignKeyConstraint(["policy_id", "organization_id"], ["alert_policies.id", "alert_policies.organization_id"],
                             name="fk_policy_versions_same_org", ondelete="CASCADE"),
    )

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    organization_id = Column(String(32), nullable=False, index=True)
    policy_id = Column(String(32), nullable=False)
    version = Column(Integer, nullable=False)
    rule = Column(JSON, nullable=False)
    created_at = Column(Float, nullable=False)
    created_by_user_id = Column(String(32), nullable=True)


class PolicyAccountStateRecord(Base):
    """Estado de una regla para una cuenta: línea base de deuda y despejes seguidos."""

    __tablename__ = "policy_account_states"
    __table_args__ = (UniqueConstraint("policy_id", "account_id", name="uq_policy_account_state"),)

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    organization_id = Column(String(32), nullable=False, index=True)
    policy_id = Column(String(32), nullable=False)
    account_id = Column(String(32), nullable=False)
    baseline_debt_base = Column(String(80), nullable=True)
    baseline_block = Column(BigInteger, nullable=True)
    consecutive_clear = Column(Integer, nullable=False, default=0)
    updated_at = Column(Float, nullable=False)


class JobRecord(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        Index("uq_jobs_activo_por_clave", "dedupe_key", unique=True, postgresql_where=text(_ACTIVOS), sqlite_where=text(_ACTIVOS)),
        Index("ix_jobs_disponibles", "status", "available_at"),
    )

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    kind = Column(String(32), nullable=False)
    organization_id = Column(String(32), nullable=False)
    account_id = Column(String(32), nullable=True)
    dedupe_key = Column(String(128), nullable=False)
    status = Column(String(16), nullable=False)
    available_at = Column(Float, nullable=False)
    attempts = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=5)
    lease_owner = Column(String(64), nullable=True)
    lease_expires_at = Column(Float, nullable=True)
    last_error = Column(String(300), nullable=True)
    created_at = Column(Float, nullable=False)
    updated_at = Column(Float, nullable=False)
    finished_at = Column(Float, nullable=True)


class IncidentRecord(Base):
    __tablename__ = "incidents"
    __table_args__ = (
        Index("uq_incidente_abierto_por_politica_cuenta", "policy_id", "account_id", unique=True,
              postgresql_where=text(_ABIERTOS), sqlite_where=text(_ABIERTOS)),
        UniqueConstraint("id", "organization_id", name="uq_incidents_id_org"),
        ForeignKeyConstraint(["account_id", "organization_id"], ["monitored_accounts.id", "monitored_accounts.organization_id"],
                             name="fk_incidents_account_same_org"),
        ForeignKeyConstraint(["policy_id", "organization_id"], ["alert_policies.id", "alert_policies.organization_id"],
                             name="fk_incidents_policy_same_org"),
    )

    id = Column(String(32), primary_key=True)
    organization_id = Column(String(32), nullable=False, index=True)
    account_id = Column(String(32), nullable=False)
    policy_id = Column(String(32), nullable=False)
    policy_version = Column(Integer, nullable=False)
    rule_type = Column(String(32), nullable=False)
    status = Column(String(16), nullable=False)
    severity = Column(String(16), nullable=False)
    escalation_level = Column(Integer, nullable=False, default=0)
    data_quality = Column(String(16), nullable=False)
    opened_at = Column(Float, nullable=False)
    escalated_at = Column(Float, nullable=True)
    acknowledged_at = Column(Float, nullable=True)
    acknowledged_by_user_id = Column(String(32), nullable=True)
    resolved_at = Column(Float, nullable=True)
    resolved_by_user_id = Column(String(32), nullable=True)
    resolution = Column(String(32), nullable=True)
    resolution_note = Column(String(500), nullable=True)
    last_evaluated_at = Column(Float, nullable=False)
    last_observed = Column(JSON, nullable=False)


class IncidentEvidenceRecord(Base):
    """Evidencia inmutable. Una corrección es otra fila que apunta a la corregida."""

    __tablename__ = "incident_evidence"
    __table_args__ = (
        ForeignKeyConstraint(["incident_id", "organization_id"], ["incidents.id", "incidents.organization_id"],
                             name="fk_evidence_incident_same_org"),
    )

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    organization_id = Column(String(32), nullable=False, index=True)
    incident_id = Column(String(32), nullable=False, index=True)
    kind = Column(String(16), nullable=False)
    snapshot_id = Column(BigInteger().with_variant(Integer, "sqlite"), ForeignKey("position_snapshots.id"), nullable=True)
    block_number = Column(BigInteger, nullable=True)
    block_hash = Column(String(66), nullable=True)
    observed = Column(JSON, nullable=False)
    data_quality = Column(String(16), nullable=False)
    note = Column(String(500), nullable=True)
    corrects_evidence_id = Column(BigInteger().with_variant(Integer, "sqlite"), ForeignKey("incident_evidence.id"), nullable=True)
    created_at = Column(Float, nullable=False)
    created_by_user_id = Column(String(32), nullable=True)


class AlertRecord(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        ForeignKeyConstraint(["incident_id", "organization_id"], ["incidents.id", "incidents.organization_id"],
                             name="fk_alerts_incident_same_org"),
    )

    id = Column(String(32), primary_key=True)
    organization_id = Column(String(32), nullable=False, index=True)
    incident_id = Column(String(32), nullable=False, index=True)
    kind = Column(String(16), nullable=False)
    severity = Column(String(16), nullable=False)
    created_at = Column(Float, nullable=False)


class NotificationChannelRecord(Base):
    __tablename__ = "notification_channels"
    __table_args__ = (
        UniqueConstraint("id", "organization_id", name="uq_channels_id_org"),
        CheckConstraint("kind IN ('sandbox', 'webhook')", name="ck_channels_kind"),
    )

    id = Column(String(32), primary_key=True)
    organization_id = Column(String(32), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    kind = Column(String(16), nullable=False)
    name = Column(String(200), nullable=False)
    config = Column(JSON, nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)
    verified_at = Column(Float, nullable=True)
    created_at = Column(Float, nullable=False)


class OutboxRecord(Base):
    """Mensaje pendiente de entrega, escrito en la misma transacción que la alerta."""

    __tablename__ = "outbox"
    __table_args__ = (
        ForeignKeyConstraint(["channel_id", "organization_id"], ["notification_channels.id", "notification_channels.organization_id"],
                             name="fk_outbox_channel_same_org", ondelete="CASCADE"),
        Index("ix_outbox_disponibles", "status", "available_at"),
    )

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    organization_id = Column(String(32), nullable=False, index=True)
    channel_id = Column(String(32), nullable=False)
    alert_id = Column(String(32), ForeignKey("alerts.id"), nullable=True)
    idempotency_key = Column(String(128), nullable=False, unique=True)
    payload = Column(JSON, nullable=False)
    status = Column(String(16), nullable=False)
    attempts = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=6)
    available_at = Column(Float, nullable=False)
    lease_owner = Column(String(64), nullable=True)
    lease_expires_at = Column(Float, nullable=True)
    last_error = Column(String(300), nullable=True)
    created_at = Column(Float, nullable=False)
    sent_at = Column(Float, nullable=True)


class NotificationDeliveryRecord(Base):
    """Entregas del canal sandbox: quedan en la base y nunca salen del sistema."""

    __tablename__ = "notification_deliveries"

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    organization_id = Column(String(32), nullable=False, index=True)
    channel_id = Column(String(32), nullable=False, index=True)
    idempotency_key = Column(String(128), nullable=False)
    payload = Column(JSON, nullable=False)
    delivered_at = Column(Float, nullable=False)


class IncidentExplanationRecord(Base):
    """Explicación generada de un incidente (E07), con su origen, validación y costo.

    Guardo cada intento, también los que cayeron al fallback, para poder auditar
    errores y gasto. El texto nunca modifica políticas ni incidentes.
    """

    __tablename__ = "incident_explanations"
    __table_args__ = (
        ForeignKeyConstraint(["incident_id", "organization_id"], ["incidents.id", "incidents.organization_id"],
                             name="fk_explanations_incident_same_org"),
    )

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    organization_id = Column(String(32), nullable=False, index=True)
    incident_id = Column(String(32), nullable=False, index=True)
    source = Column(String(16), nullable=False)  # template | model
    model = Column(String(100), nullable=True)
    input_sha256 = Column(String(64), nullable=False)
    output = Column(JSON, nullable=False)
    validation_errors = Column(JSON, nullable=False)
    fallback_reason = Column(String(40), nullable=True)
    input_tokens = Column(Integer, nullable=False, default=0)
    output_tokens = Column(Integer, nullable=False, default=0)
    cost_usd = Column(String(32), nullable=False, default="0")
    latency_ms = Column(Integer, nullable=False, default=0)
    created_at = Column(Float, nullable=False, index=True)
    created_by_user_id = Column(String(32), nullable=True)


class WorkerHeartbeatRecord(Base):
    """Último latido de cada worker (E08): sirve para liveness y para métricas."""

    __tablename__ = "worker_heartbeats"

    worker_id = Column(String(64), primary_key=True)
    hostname = Column(String(100), nullable=False, index=True)
    started_at = Column(Float, nullable=False)
    last_seen_at = Column(Float, nullable=False, index=True)
    last_step = Column(JSON, nullable=False)
    last_error = Column(String(100), nullable=True)


# --- Piloto comercial (E09) ------------------------------------------------------


class SubscriptionRecord(Base):
    """Plan y estado comercial de una organización. Define qué servicio recibe.

    El estado solo pasa a `active` con un pago confirmado (manual o por webhook
    firmado); nunca por una simulación.
    """

    __tablename__ = "subscriptions"

    organization_id = Column(String(32), ForeignKey("organizations.id"), primary_key=True)
    plan = Column(String(32), nullable=False)
    status = Column(String(16), nullable=False)  # trialing, active, past_due, canceled, expired
    trial_ends_at = Column(Float, nullable=True)
    current_period_end = Column(Float, nullable=True)
    grace_ends_at = Column(Float, nullable=True)
    cancel_at_period_end = Column(Boolean, nullable=False, default=False)
    canceled_at = Column(Float, nullable=True)
    created_at = Column(Float, nullable=False)
    updated_at = Column(Float, nullable=False)


class PaymentRecord(Base):
    """Un pago confirmado que extiende el período. Lo registra una persona (cobro asistido) o un webhook firmado."""

    __tablename__ = "payment_records"
    __table_args__ = (UniqueConstraint("source", "reference", name="uq_payment_source_reference"),)

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    organization_id = Column(String(32), ForeignKey("organizations.id"), nullable=False, index=True)
    source = Column(String(16), nullable=False)  # manual | webhook
    reference = Column(String(100), nullable=False)
    amount_usd = Column(String(20), nullable=False)
    period_start = Column(Float, nullable=False)
    period_end = Column(Float, nullable=False)
    confirmed_by = Column(String(100), nullable=False)
    created_at = Column(Float, nullable=False)


class BillingEventRecord(Base):
    """Evento de un procesador de pagos recibido por webhook firmado. La unicidad da idempotencia."""

    __tablename__ = "billing_events"
    __table_args__ = (UniqueConstraint("provider", "event_id", name="uq_billing_event"),)

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    provider = Column(String(32), nullable=False)
    event_id = Column(String(100), nullable=False)
    type = Column(String(64), nullable=False)
    organization_id = Column(String(32), nullable=True, index=True)
    payload_sha256 = Column(String(64), nullable=False)
    outcome = Column(String(32), nullable=False)
    received_at = Column(Float, nullable=False)


class ProductEventRecord(Base):
    """Evento de uso del producto para medir activación (E09).

    Solo nombres de una lista cerrada y propiedades enumeradas: sin correos,
    direcciones, balances ni textos libres.
    """

    __tablename__ = "product_events"
    __table_args__ = (UniqueConstraint("once_key", name="uq_product_events_once_key"),)

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    organization_id = Column(String(32), ForeignKey("organizations.id"), nullable=False, index=True)
    name = Column(String(40), nullable=False, index=True)
    properties = Column(JSON, nullable=False)
    is_demo = Column(Boolean, nullable=False, default=False)
    occurred_at = Column(Float, nullable=False, index=True)
    once_key = Column(String(80), nullable=True)  # eventos que cuentan una sola vez por organización


class ContactRequestRecord(Base):
    """Pedido de contacto desde la landing. Lo leo a mano; no envío mensajes automáticos."""

    __tablename__ = "contact_requests"

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    email = Column(String(320), nullable=False)
    organization = Column(String(200), nullable=True)
    message = Column(String(2000), nullable=False)
    consent = Column(Boolean, nullable=False)
    created_at = Column(Float, nullable=False, index=True)
    handled_at = Column(Float, nullable=True)

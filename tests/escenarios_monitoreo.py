"""Escenarios de monitoreo que corro sobre SQLite y sobre PostgreSQL.

Cada función recibe un engine y verifica una garantía: no duplicar el episodio,
recuperar el trabajo, reintentar, escalar, cerrar con histéresis o corregir
evidencia ante un reorg.
"""

import pytest

from infra.db_models import (
    AlertRecord,
    IncidentEvidenceRecord,
    IncidentRecord,
    JobRecord,
    NotificationDeliveryRecord,
    OrgEventRecord,
    OutboxRecord,
)
from ingestion_onchain.resultados import Motivo
from monitoreo.notificaciones import EntregaSandbox, ErrorEntrega
from monitoreo.trabajos import LeasePerdido
from tests.monitoreo_ayudantes import Entorno, escenario_hf

REGLA_HF = {"type": "health_factor_below", "threshold": "1.5", "clear_above": "1.6", "clear_after": 2,
            "severity": "high", "escalate_after_seconds": 300}


def abre_una_vez_y_no_repite_alertas(engine):
    e = Entorno(engine, REGLA_HF)
    e.adaptador.poner(escenario_hf("1.375"))
    w = e.worker()

    w.paso()
    # Miro solo esta organización: sobre una base compartida el worker también procesa otras.
    assert [j.status for j in e.tabla(JobRecord, account_id=e.cuentas[0])] == ["done"]
    assert [o.status for o in e.tabla(OutboxRecord, organization_id=e.org_id)] == ["sent"]
    for _ in range(3):
        e.siguiente_ronda()
        w.paso()

    incidentes = e.tabla(IncidentRecord, organization_id=e.org_id)
    assert len(incidentes) == 1 and incidentes[0].status == "open"
    assert incidentes[0].last_observed["health_factor"].startswith("1.37")
    assert [a.kind for a in e.tabla(AlertRecord, incident_id=incidentes[0].id)] == ["opened"]
    enviados = [x for x in e.transporte.enviados if x["channel_id"] == e.canal["id"]]
    assert len(enviados) == 1 and enviados[0]["payload"]["type"] == "incident.opened"
    evidencia = e.tabla(IncidentEvidenceRecord, incident_id=incidentes[0].id)
    assert [x.kind for x in evidencia] == ["opening"] and evidencia[0].block_number == 20_000_000
    eventos = [x.type for x in e.tabla(OrgEventRecord, organization_id=e.org_id)]
    assert eventos.count("incident.opened") == 1 and eventos.count("account.evaluated") == 4
    return e


def cierra_con_histeresis(engine):
    e = Entorno(engine, REGLA_HF)
    e.adaptador.poner(escenario_hf("1.375"))
    w = e.worker()
    w.paso()
    incidente = e.tabla(IncidentRecord, organization_id=e.org_id)[0]

    # 1,55 está entre el umbral (1,5) y el despeje (1,6): no cuenta como despeje.
    e.adaptador.poner(escenario_hf("1.55"))
    e.siguiente_ronda(); w.paso()
    e.adaptador.poner(escenario_hf("2.0"))
    e.siguiente_ronda(); w.paso()
    assert e.tabla(IncidentRecord, id=incidente.id)[0].status == "open"  # 1 de 2 despejes
    e.adaptador.poner(escenario_hf("1.55"))
    e.siguiente_ronda(); w.paso()  # vuelve a la banda: reinicia el conteo
    e.adaptador.poner(escenario_hf("2.0"))
    e.siguiente_ronda(); w.paso()
    assert e.tabla(IncidentRecord, id=incidente.id)[0].status == "open"
    e.siguiente_ronda(); w.paso()

    cerrado = e.tabla(IncidentRecord, id=incidente.id)[0]
    assert cerrado.status == "resolved" and cerrado.resolution == "auto_cleared"
    assert [a.kind for a in e.tabla(AlertRecord, incident_id=incidente.id)] == ["opened", "resolved"]

    # Un nuevo cruce abre un episodio nuevo, distinto del anterior.
    e.adaptador.poner(escenario_hf("1.375"))
    e.siguiente_ronda(); w.paso()
    assert len(e.tabla(IncidentRecord, organization_id=e.org_id)) == 2


def escala_si_nadie_reconoce(engine):
    e = Entorno(engine, REGLA_HF)
    e.adaptador.poner(escenario_hf("1.375"))
    w = e.worker()
    w.paso()
    e.siguiente_ronda(301); w.paso()
    incidente = e.tabla(IncidentRecord, organization_id=e.org_id)[0]
    assert incidente.escalation_level == 1 and incidente.severity == "critical"
    assert [a.kind for a in e.tabla(AlertRecord, incident_id=incidente.id)] == ["opened", "escalated"]

    from monitoreo.incidentes import ServicioIncidentes

    ServicioIncidentes(engine, e.reloj).reconocer(e.ctx, incidente.id)
    e.siguiente_ronda(301); w.paso()
    assert e.tabla(IncidentRecord, id=incidente.id)[0].escalation_level == 1  # reconocido: no escala más


def reintenta_429_y_luego_marca_dato_atrasado(engine):
    regla = {"type": "stale_data", "max_age_seconds": 120, "severity": "medium"}
    e = Entorno(engine, regla)
    w = e.worker()
    w.paso()  # lectura FRESH inicial
    e.adaptador.falla = Motivo.RATE_LIMITED

    e.siguiente_ronda()
    assert w.paso()["jobs"] == {"retry": 1}
    job = [j for j in e.tabla(JobRecord, account_id=e.cuentas[0]) if j.status == "pending"][0]
    assert job.attempts == 1 and job.available_at > e.reloj() and job.last_error.startswith("rate_limited")

    # Sigo con 429 hasta agotar intentos: la última evaluación corre con UNAVAILABLE.
    for _ in range(3):
        e.siguiente_ronda(700)
        w.paso()
    incidentes = e.tabla(IncidentRecord, organization_id=e.org_id)
    assert len(incidentes) == 1 and incidentes[0].rule_type == "stale_data"
    assert incidentes[0].last_observed["data_quality"] == "UNAVAILABLE"

    e.adaptador.falla = None
    e.siguiente_ronda(); w.paso()
    assert e.tabla(IncidentRecord, id=incidentes[0].id)[0].status == "resolved"


def recupera_lease_vencido_sin_duplicar(engine):
    e = Entorno(engine, REGLA_HF)
    e.adaptador.poner(escenario_hf("1.375"))
    a, b = e.worker("worker-a", lease=30), e.worker("worker-b", lease=30)

    a.programar()
    tomado_por_a = a.cola.tomar("worker-a")  # A toma el job y "se cuelga"
    assert b.cola.tomar("worker-b") is None  # lease vigente: B no lo toma
    e.reloj.avanzar(31)

    resultado = b.paso()  # lease vencido: B lo retoma y lo completa
    assert resultado["jobs"] == {"done": 1}
    # A despierta e intenta terminar: el fencing lo rechaza y no confirma efectos.
    with pytest.raises(LeasePerdido):
        a.evaluador.ejecutar(tomado_por_a)

    assert len(e.tabla(IncidentRecord, organization_id=e.org_id)) == 1
    assert len(e.tabla(AlertRecord, organization_id=e.org_id)) == 1
    jobs = e.tabla(JobRecord, account_id=e.cuentas[0])
    assert [(j.status, j.attempts) for j in jobs] == [("done", 2)]


def crash_despues_del_commit_y_replay(engine):
    """El commit de la evaluación incluye el job: tras un crash no hay nada que rehacer.
    Si el mismo trabajo se vuelve a encolar (replay), no se duplica el episodio."""
    e = Entorno(engine, REGLA_HF)
    e.adaptador.poner(escenario_hf("1.375"))
    w = e.worker()
    w.programar()
    trabajo = w.cola.tomar("w1")
    assert w.evaluador.ejecutar(trabajo) == "done"
    # "Crash" antes de entregar el outbox: el próximo worker lo entrega.
    otro = e.worker("w2")
    otro.cola.encolar("evaluate_account", e.org_id, e.cuentas[0], f"evaluate:{e.cuentas[0]}")  # replay
    resultado = otro.paso()
    assert resultado["jobs"] == {"done": 1} and resultado["deliveries"] == {"sent": 1}
    assert len(e.tabla(IncidentRecord, organization_id=e.org_id)) == 1
    assert len(e.tabla(AlertRecord, organization_id=e.org_id)) == 1
    assert len(e.transporte.enviados) == 1


def entrega_at_least_once_con_misma_clave(engine):
    e = Entorno(engine, REGLA_HF)
    e.adaptador.poner(escenario_hf("1.375"))
    w = e.worker("w1", lease=30)
    w.programar(); w.evaluar_disponibles()

    # w1 toma la fila, envía y muere antes de marcarla como enviada.
    fila = w.notificaciones.tomar("w1")
    e.transporte.enviar(type("C", (), {"id": fila.channel_id})(), fila.payload, fila.idempotency_key)
    e.reloj.avanzar(31)
    assert e.worker("w2").entregar_disponibles() == {"sent": 1}

    claves = [x["idempotency_key"] for x in e.transporte.enviados]
    assert len(claves) == 2 and len(set(claves)) == 1  # duplicado visible, misma clave
    assert [o.status for o in e.tabla(OutboxRecord, organization_id=e.org_id)] == ["sent"]


def reintenta_entregas_con_backoff(engine):
    e = Entorno(engine, REGLA_HF)
    e.adaptador.poner(escenario_hf("1.375"))
    e.transporte.fallas = [ErrorEntrega("HTTP 429", reintentable=True), ErrorEntrega("HTTP 503", reintentable=True)]
    w = e.worker()
    assert w.paso()["deliveries"] == {"pending": 1}
    e.reloj.avanzar(6); assert w.entregar_disponibles() == {"pending": 1}
    e.reloj.avanzar(11); assert w.entregar_disponibles() == {"sent": 1}
    fila = e.tabla(OutboxRecord, organization_id=e.org_id)[0]
    assert fila.status == "sent" and fila.attempts == 3

    e.transporte.fallas = [ErrorEntrega("HTTP 400", reintentable=False)]
    from monitoreo.notificaciones import ServicioNotificaciones

    # La prueba de un canal sandbox se entrega en el momento; un 400 la deja en failed.
    assert ServicioNotificaciones(engine, e.reloj, e.transportes).probar_canal(e.ctx, e.canal["id"])["status"] == "failed"


def corrige_evidencia_ante_reorg(engine):
    e = Entorno(engine, REGLA_HF)
    e.adaptador.poner(escenario_hf("1.375"))
    w = e.worker()
    w.paso()
    incidente = e.tabla(IncidentRecord, organization_id=e.org_id)[0]
    apertura = e.tabla(IncidentEvidenceRecord, incident_id=incidente.id)[0]

    # El bloque de apertura se reorganiza: mismo número, otro hash.
    e.adaptador.poner(escenario_hf("1.375"), hash_bloque="0x" + "e" * 64)
    e.siguiente_ronda(); w.paso()

    evidencias = e.tabla(IncidentEvidenceRecord, incident_id=incidente.id)
    correcciones = [x for x in evidencias if x.kind == "correction"]
    assert len(correcciones) == 1 and correcciones[0].corrects_evidence_id == apertura.id
    assert correcciones[0].observed == {"original_block_hash": apertura.block_hash, "canonical_block_hash": "0x" + "e" * 64}
    original = [x for x in evidencias if x.id == apertura.id][0]
    assert original.block_hash == apertura.block_hash  # la original no cambia
    assert len(e.tabla(IncidentRecord, organization_id=e.org_id)) == 1
    e.siguiente_ronda(); w.paso()
    assert len([x for x in e.tabla(IncidentEvidenceRecord, incident_id=incidente.id) if x.kind == "correction"]) == 1


def canal_sandbox_queda_verificado(engine):
    from monitoreo.notificaciones import ServicioNotificaciones

    e = Entorno(engine, REGLA_HF)
    sandbox = ServicioNotificaciones(engine, e.reloj)  # entrega sandbox real (en la base)
    sandbox.transportes["sandbox"] = EntregaSandbox(sandbox._Session, e.reloj)
    assert sandbox.probar_canal(e.ctx, e.canal["id"])["status"] == "sent"
    assert sandbox.entregar_uno("w1") is None  # no quedó nada pendiente
    assert sandbox.listar_canales(e.ctx)[0]["verified_at"] is not None
    assert len(e.tabla(NotificationDeliveryRecord, channel_id=e.canal["id"])) == 1

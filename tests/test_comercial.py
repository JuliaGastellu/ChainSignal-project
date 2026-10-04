"""Piloto comercial (E09): plan, límites, prueba, cancelación, cobro asistido, webhook, analítica y tablero."""

import json
import time

import pytest

from comercial.analitica import EventoInvalido, registrar, validar
from comercial.facturacion import FirmaInvalida, ProcesadorWebhook, firmar
from comercial.planes import PILOTO
from comercial.suscripciones import LimiteDelPlan, PlanInactivo, ServicioSuscripciones
from identidad.recursos import ServicioRecursos
from identidad.servicio import ServicioIdentidad
from infra.db import get_session_factory, make_engine
from infra.db_models import JobRecord, PaymentRecord, ProductEventRecord, SubscriptionRecord
from tests.ayudantes_identidad import CONTRASENA_PRUEBA, cliente_anonimo, crear_organizacion, iniciar_sesion, sumar_miembro

DIA = 86400


class Reloj:
    def __init__(self):
        self.ahora = time.time()

    def __call__(self):
        return self.ahora


@pytest.fixture
def engine(tmp_path):
    return make_engine(f"sqlite:///{(tmp_path / 'comercial.db').as_posix()}")


@pytest.fixture
def org(engine):
    identidad = ServicioIdentidad(engine)
    org_id, user_id = identidad.crear_organizacion_con_owner("Tesorería", f"owner-{time.time_ns()}@ejemplo.test", CONTRASENA_PRUEBA)
    token, _, sesion = identidad.crear_sesion(user_id)
    return org_id, identidad.contexto(sesion, org_id, "owner")


def _direccion(i: int) -> str:
    return "0x" + f"{i + 1:040x}"


def _tabla(engine, modelo, **filtros):
    from sqlalchemy import select

    with get_session_factory(engine)() as s:
        consulta = select(modelo)
        for campo, valor in filtros.items():
            consulta = consulta.where(getattr(modelo, campo) == valor)
        return s.execute(consulta).scalars().all()


# --- plan, prueba y límites -----------------------------------------------------


def test_organizacion_nueva_empieza_prueba_visible(engine, org):
    org_id, _ = org
    datos = ServicioSuscripciones(engine).presentar(org_id)
    assert datos["status"] == "trialing" and datos["service_active"] is True
    assert datos["trial_ends_at"] - time.time() == pytest.approx(14 * DIA, abs=60)
    assert datos["limits"] == {"max_accounts": 10, "min_interval_seconds": 60, "chains": [1], "markets": ["aave-v3-ethereum"]}
    assert datos["plan"]["reference_price_usd_per_month"] == "150" and datos["plan"]["price_is_hypothesis"] is True
    assert datos["plan"]["billing"] == "assisted_invoice" and datos["confirmed_payments"] == []


def test_limite_de_cuentas_y_frecuencia(engine, org):
    _, ctx = org
    recursos = ServicioRecursos(engine)
    cuentas = [recursos.crear_cuenta(ctx, _direccion(i), 1, None, "medium", 60) for i in range(PILOTO.limites.max_cuentas)]
    with pytest.raises(LimiteDelPlan):
        recursos.crear_cuenta(ctx, _direccion(99), 1, None, "medium", 300)
    with pytest.raises(LimiteDelPlan):
        recursos.actualizar_cuenta(ctx, cuentas[0]["id"], {"interval_seconds": 30})
    assert recursos.actualizar_cuenta(ctx, cuentas[0]["id"], {"interval_seconds": 120})["interval_seconds"] == 120


def test_frecuencia_minima_en_el_alta(engine, org):
    _, ctx = org
    with pytest.raises(LimiteDelPlan):
        ServicioRecursos(engine).crear_cuenta(ctx, _direccion(0), 1, None, "medium", 30)


def test_prueba_vencida_corta_servicio_pero_no_el_historial(engine, org):
    from monitoreo.worker import WorkerMonitoreo

    org_id, ctx = org
    reloj = Reloj()
    ServicioRecursos(engine).crear_cuenta(ctx, _direccion(0), 1, None, "medium", 60)
    servicio = ServicioSuscripciones(engine, reloj)
    reloj.ahora += 15 * DIA
    derecho = servicio.derecho(org_id)
    assert derecho.estado == "expired" and derecho.con_servicio is False
    with pytest.raises(PlanInactivo):
        servicio.exigir_servicio(org_id)
    # El worker deja de programarla sola, sin que nadie cambie el estado.
    assert WorkerMonitoreo(lambda: None, engine, reloj).programar() == 0
    assert _tabla(engine, JobRecord, organization_id=org_id) == []


def test_cancelacion_visible_y_reanudable(engine, org):
    org_id, ctx = org
    reloj = Reloj()
    servicio = ServicioSuscripciones(engine, reloj)
    cancelada = servicio.cancelar(ctx)
    assert cancelada["cancel_at_period_end"] is True and cancelada["status"] == "trialing" and cancelada["service_active"]
    assert servicio.reanudar(ctx)["cancel_at_period_end"] is False
    servicio.cancelar(ctx)
    reloj.ahora += 15 * DIA
    assert servicio.presentar(org_id)["status"] == "canceled" and not servicio.derecho(org_id).con_servicio


def test_pago_confirmado_activa_y_es_idempotente(engine, org):
    org_id, _ = org
    reloj = Reloj()
    servicio = ServicioSuscripciones(engine, reloj)
    assert servicio.confirmar_pago(org_id, "FACTURA-0001", "150", "persona que verificó")["status"] == "confirmed"
    assert servicio.confirmar_pago(org_id, "FACTURA-0001", "150", "persona que verificó")["status"] == "duplicate"
    assert len(_tabla(engine, PaymentRecord, organization_id=org_id)) == 1
    datos = servicio.presentar(org_id)
    assert datos["status"] == "active" and datos["current_period_end"] - reloj.ahora == pytest.approx(30 * DIA, abs=1)
    # Vence el período sin pago: gracia de 7 días con servicio, después se corta.
    reloj.ahora += 31 * DIA
    assert servicio.derecho(org_id).estado == "past_due" and servicio.derecho(org_id).con_servicio
    reloj.ahora += 7 * DIA
    assert servicio.derecho(org_id).estado == "expired" and not servicio.derecho(org_id).con_servicio
    # Una renovación confirmada lo reactiva.
    assert servicio.confirmar_pago(org_id, "FACTURA-0002", "150", "persona que verificó")["status"] == "confirmed"
    assert servicio.derecho(org_id).estado == "active"


@pytest.mark.parametrize("referencia, monto, por", [("", "150", "x"), ("F", "0", "x"), ("F", "abc", "x"), ("F", "150", "")])
def test_pago_exige_datos_de_confirmacion(engine, org, referencia, monto, por):
    from identidad.servicio import SolicitudInvalida

    with pytest.raises(SolicitudInvalida):
        ServicioSuscripciones(engine).confirmar_pago(org[0], referencia, monto, por)


def test_demo_no_tiene_suscripcion_ni_puede_pagar(engine):
    from monitoreo.demo import crear_demo

    demo = crear_demo(engine)
    assert _tabla(engine, SubscriptionRecord, organization_id=demo["organization_id"]) == []
    assert ServicioSuscripciones(engine).derecho(demo["organization_id"]).es_demo


# --- webhook firmado ------------------------------------------------------------


SECRETO = "secreto-de-prueba-del-webhook"


def _evento(org_id, event_id="evt_1", tipo="payment.succeeded", referencia="pi_1"):
    return json.dumps({"id": event_id, "type": tipo, "data": {"organization_id": org_id, "reference": referencia,
                                                                "amount_usd": "150"}}).encode()


def test_webhook_firmado_idempotente_y_contra_replay(engine, org):
    org_id, _ = org
    reloj = Reloj()
    procesador = ProcesadorWebhook(SECRETO, "pruebas", engine, reloj)
    cuerpo = _evento(org_id)
    firma = firmar(SECRETO, cuerpo, int(reloj.ahora))
    assert procesador.procesar(cuerpo, firma)["status"] == "confirmed"
    assert procesador.procesar(cuerpo, firma)["status"] == "duplicate"
    assert len(_tabla(engine, PaymentRecord, organization_id=org_id)) == 1
    assert _tabla(engine, PaymentRecord, organization_id=org_id)[0].source == "webhook"

    with pytest.raises(FirmaInvalida):
        procesador.procesar(cuerpo, firmar("otro-secreto", cuerpo, int(reloj.ahora)))
    with pytest.raises(FirmaInvalida):
        procesador.procesar(_evento(org_id, "evt_2"), firma)  # cuerpo distinto, firma vieja
    viejo = _evento(org_id, "evt_3")
    with pytest.raises(FirmaInvalida):
        procesador.procesar(viejo, firmar(SECRETO, viejo, int(reloj.ahora) - 600))
    with pytest.raises(FirmaInvalida):
        procesador.procesar(viejo, None)


def test_webhook_pago_fallido_da_gracia_y_falla_al_aplicar_es_reintentable(engine, org):
    org_id, _ = org
    reloj = Reloj()
    procesador = ProcesadorWebhook(SECRETO, "pruebas", engine, reloj)
    ok = _evento(org_id, "evt_ok")
    procesador.procesar(ok, firmar(SECRETO, ok, int(reloj.ahora)))
    fallo = _evento(org_id, "evt_fallo", "payment.failed")
    assert procesador.procesar(fallo, firmar(SECRETO, fallo, int(reloj.ahora)))["status"] == "past_due"
    assert ServicioSuscripciones(engine, reloj).derecho(org_id).con_servicio  # sigue en gracia

    roto = json.dumps({"id": "evt_roto", "type": "payment.succeeded",
                       "data": {"organization_id": org_id, "reference": "pi_x", "amount_usd": "no-es-numero"}}).encode()
    from identidad.servicio import SolicitudInvalida

    with pytest.raises(SolicitudInvalida):
        procesador.procesar(roto, firmar(SECRETO, roto, int(reloj.ahora)))
    # El evento no quedó registrado: un reintento corregido del procesador se procesa.
    from infra.db_models import BillingEventRecord

    assert _tabla(engine, BillingEventRecord, event_id="evt_roto") == []


def test_webhook_apagado_sin_secreto():
    respuesta = cliente_anonimo().post("/billing/webhook", content=b"{}")
    assert respuesta.status_code == 404


# --- analítica --------------------------------------------------------------------


def test_analitica_rechaza_datos_personales_y_propiedades_libres():
    with pytest.raises(EventoInvalido):
        validar("account_added", {"address": "0x" + "1" * 40})
    with pytest.raises(EventoInvalido):
        validar("org_created", {"email": "persona@ejemplo.test"})
    with pytest.raises(EventoInvalido):
        validar("account_added", {"role": "admin-de-todo"})
    with pytest.raises(EventoInvalido):
        validar("balance_seen", {})
    assert validar("policy_created", {"rule_type": "stale_data"}) == {"rule_type": "stale_data"}


def test_eventos_de_una_vez(engine, org):
    org_id, _ = org
    assert registrar(engine, org_id, "first_snapshot", {"source": "api"}) is True
    assert registrar(engine, org_id, "first_snapshot", {"source": "worker"}) is False
    assert len(_tabla(engine, ProductEventRecord, organization_id=org_id, name="org_created")) == 1


def test_recorrido_de_activacion_queda_instrumentado(cliente_owner, organizacion):
    from infra.db import engine as engine_api
    from tests import escenarios_monitoreo as escenarios

    e = escenarios.abre_una_vez_y_no_repite_alertas(engine_api)
    owner = iniciar_sesion(e.email)
    incidente = owner.get(f"/orgs/{e.org_id}/incidents").json()["incidents"][0]["id"]
    owner.get(f"/orgs/{e.org_id}/incidents/{incidente}")
    owner.get(f"/orgs/{e.org_id}/incidents/{incidente}")  # la misma revisión cuenta una vez
    assert owner.post(f"/orgs/{e.org_id}/incidents/{incidente}/acknowledge").status_code == 200
    owner.get(f"/orgs/{e.org_id}/summary")
    eventos = _tabla(engine_api, ProductEventRecord, organization_id=e.org_id)
    nombres = [x.name for x in eventos]
    for paso in ("org_created", "account_added", "first_snapshot", "policy_created", "incident_reviewed",
                 "incident_acknowledged", "data_reviewed"):
        assert paso in nombres, paso
    assert nombres.count("incident_reviewed") == 1
    # Nada identificable en las propiedades: ni correos ni direcciones.
    volcado = json.dumps([x.properties for x in eventos])
    assert "@" not in volcado and "0x" not in volcado


# --- API: suscripción, límites y servicio -------------------------------------------


def test_api_de_suscripcion_y_limites(cliente_owner, organizacion):
    org_id = organizacion[0]
    viewer, _ = sumar_miembro(org_id, cliente_owner, "viewer")
    datos = viewer.get(f"/orgs/{org_id}/subscription").json()
    assert datos["status"] == "trialing" and datos["plan"]["price_is_hypothesis"] is True
    assert viewer.post(f"/orgs/{org_id}/subscription/cancel").status_code == 403
    assert cliente_owner.post(f"/orgs/{org_id}/accounts", json={"address": _direccion(0), "interval_seconds": 30}).status_code == 403
    assert cliente_owner.post(f"/orgs/{org_id}/subscription/cancel").json()["cancel_at_period_end"] is True
    assert cliente_owner.post(f"/orgs/{org_id}/subscription/resume").json()["cancel_at_period_end"] is False


def test_api_sin_servicio_responde_402_y_conserva_historial(cliente_owner, organizacion, monkeypatch):
    org_id = organizacion[0]
    cuenta = cliente_owner.post(f"/orgs/{org_id}/accounts", json={"address": _direccion(1)}).json()
    from comercial import suscripciones

    real = suscripciones.estado_efectivo
    monkeypatch.setattr(suscripciones, "estado_efectivo", lambda sub, ahora: real(sub, ahora + 15 * DIA))
    evaluar = cliente_owner.post(f"/orgs/{org_id}/accounts/{cuenta['id']}/evaluate")
    assert evaluar.status_code == 402 and evaluar.json()["error"] == "plan_inactive"
    assert cliente_owner.get(f"/orgs/{org_id}/accounts/{cuenta['id']}/positions/aave-v3").status_code == 402
    assert cliente_owner.post(f"/orgs/{org_id}/accounts", json={"address": _direccion(2)}).status_code == 402
    # El historial sigue disponible.
    assert cliente_owner.get(f"/orgs/{org_id}/incidents").status_code == 200
    assert cliente_owner.get(f"/orgs/{org_id}/accounts/{cuenta['id']}/positions/aave-v3/snapshots").status_code == 200
    assert cliente_owner.get(f"/orgs/{org_id}/subscription").json()["status"] == "expired"


# --- contacto ---------------------------------------------------------------------


def test_contacto_exige_consentimiento_y_limita(monkeypatch):
    import api.rutas_comerciales as rutas

    rutas._limite_contacto.reiniciar()
    cliente = cliente_anonimo()
    cuerpo = {"email": "persona@ejemplo.test", "organization": "Equipo", "message": "Quiero probar el piloto."}
    assert cliente.post("/contact", json={**cuerpo, "consent": False}).status_code == 422
    assert cliente.post("/contact", json={**cuerpo, "consent": True}).status_code == 201
    estados = [cliente.post("/contact", json={**cuerpo, "consent": True}).status_code for _ in range(5)]
    assert estados[-1] == 429


# --- tablero ----------------------------------------------------------------------


def test_tablero_real_no_inventa_pagos(engine, org):
    from comercial.tablero import medir

    m = medir(engine)
    assert m["synthetic"] is False and m["organizations"] == 1
    assert m["commercial_gate"] == {"paid_pilots": 0, "renewals": 0, "required": {"paid_pilots": 3, "renewals": 2},
                                    "met": False, "source": "payment_records (confirmed payments only)"}
    assert m["alert_usefulness"].startswith("pending")


def test_tablero_sintetico_marcado(tmp_path):
    from comercial.tablero import a_html, medir, sembrar_sintetico
    from infra.db import init_db

    motor = make_engine(f"sqlite:///{(tmp_path / 'sintetico.db').as_posix()}")
    init_db(motor)
    ahora = time.time()
    sembrar_sintetico(motor, ahora)
    m = medir(motor, ahora, sintetico=True)
    assert all(o["name"].startswith("[SINTÉTICO]") for o in m["per_organization"])
    pagina = a_html(m)
    assert "DATOS SINTÉTICOS" in pagina and "no cuenta para la decisión" in pagina

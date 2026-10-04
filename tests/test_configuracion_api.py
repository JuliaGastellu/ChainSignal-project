"""Recorridos de Configuración por rol: políticas versionadas, pausa, miembros e invitaciones."""

from infra.db import engine as engine_api
from infra.db_models import IncidentEvidenceRecord, IncidentRecord
from tests import escenarios_monitoreo as escenarios
from tests.ayudantes_identidad import CONTRASENA_PRUEBA, cliente_anonimo, crear_organizacion, email_unico, iniciar_sesion, sumar_miembro

HF = {"type": "health_factor_below", "threshold": "1.5"}


def test_vista_previa_dice_cuando_abre_y_despeja(cliente_owner, organizacion):
    org = organizacion[0]
    viewer, _ = sumar_miembro(org, cliente_owner, "viewer")
    vista = cliente_owner.post(f"/orgs/{org}/policies/preview", json={"rule": HF}).json()
    assert vista["opens"] == {"when": "health_factor_below", "threshold": "1.5", "requires_fresh_data": True}
    assert vista["clears"]["value"] == "1.575" and vista["clears"]["consecutive_evaluations"] == 2
    assert cliente_owner.post(f"/orgs/{org}/policies/preview", json={"rule": {"type": "stale_data", "max_age_seconds": 5}}).status_code == 422
    assert viewer.post(f"/orgs/{org}/policies/preview", json={"rule": HF}).status_code == 403
    assert cliente_owner.get(f"/orgs/{org}/policies").json()["policies"] == []  # la vista previa no guarda


def test_editar_crea_version_y_no_toca_la_evidencia():
    e = escenarios.abre_una_vez_y_no_repite_alertas(engine_api)
    owner = iniciar_sesion(e.email)
    operador, _ = sumar_miembro(e.org_id, owner, "operator")
    viewer, _ = sumar_miembro(e.org_id, owner, "viewer")
    politica = e.politica["id"]
    evidencia_antes = [(x.id, x.observed, x.note) for x in e.tabla(IncidentEvidenceRecord, organization_id=e.org_id)]

    assert viewer.patch(f"/orgs/{e.org_id}/policies/{politica}", json={"enabled": False}).status_code == 403
    editada = operador.patch(f"/orgs/{e.org_id}/policies/{politica}", json={"rule": {**HF, "threshold": "1.3"}})
    assert editada.status_code == 200 and editada.json()["version"] == 2
    versiones = owner.get(f"/orgs/{e.org_id}/policies/{politica}/versions").json()["versions"]
    assert [v["version"] for v in versiones] == [1, 2]
    assert e.tabla(IncidentRecord, organization_id=e.org_id)[0].policy_version == 1  # el incidente sigue en su versión
    assert [(x.id, x.observed, x.note) for x in e.tabla(IncidentEvidenceRecord, organization_id=e.org_id)] == evidencia_antes


def test_pausa_y_reactivacion():
    e = escenarios.abre_una_vez_y_no_repite_alertas(engine_api)
    owner = iniciar_sesion(e.email)
    politica = e.politica["id"]
    pausada = owner.patch(f"/orgs/{e.org_id}/policies/{politica}", json={"enabled": False}).json()
    assert pausada["enabled"] is False and pausada["version"] == 1  # pausar no crea versión de regla
    assert owner.get(f"/orgs/{e.org_id}/summary").json()["readiness"]["policy_enabled"] is False
    assert owner.patch(f"/orgs/{e.org_id}/policies/{politica}", json={"enabled": True}).json()["enabled"] is True


def test_invitacion_aceptacion_y_roles_sin_dejar_la_organizacion_sin_responsable(cliente_owner, organizacion):
    org = organizacion[0]
    operador, _ = sumar_miembro(org, cliente_owner, "operator")
    assert operador.post(f"/orgs/{org}/invitations", json={"email": email_unico("x"), "role": "viewer"}).status_code == 403

    invitada = email_unico("invitada")
    invitacion = cliente_owner.post(f"/orgs/{org}/invitations", json={"email": invitada, "role": "viewer"}).json()
    assert len(invitacion["token"]) > 20
    pendientes = cliente_owner.get(f"/orgs/{org}/invitations").json()["invitations"]
    assert any(i["email"] == invitada for i in pendientes) and "token" not in str(pendientes)
    nueva = cliente_anonimo()
    aceptada = nueva.post("/invitations/accept", json={"token": invitacion["token"], "password": CONTRASENA_PRUEBA})
    assert aceptada.status_code == 200 and aceptada.json()["new_user"] is True
    # El token es de un solo uso (y con sesión iniciada, aceptar además exige CSRF).
    assert nueva.post("/invitations/accept", json={"token": invitacion["token"]}).status_code == 403
    assert cliente_anonimo().post("/invitations/accept", json={"token": invitacion["token"], "password": CONTRASENA_PRUEBA}).status_code == 404

    miembros = {m["email"]: m for m in cliente_owner.get(f"/orgs/{org}/members").json()["members"]}
    lector = miembros[invitada]
    assert operador.patch(f"/orgs/{org}/members/{lector['membership_id']}", json={"role": "operator"}).status_code == 403
    assert cliente_owner.patch(f"/orgs/{org}/members/{lector['membership_id']}", json={"role": "operator"}).json()["role"] == "operator"

    # La única owner no puede degradarse ni irse: la organización quedaría sin responsable.
    propia = next(m for m in miembros.values() if m["role"] == "owner")
    assert cliente_owner.patch(f"/orgs/{org}/members/{propia['membership_id']}", json={"role": "viewer"}).status_code == 409
    assert cliente_owner.delete(f"/orgs/{org}/members/{propia['membership_id']}").status_code == 409

    # Otra organización no ve ni toca estos miembros.
    _, email_ajeno = crear_organizacion("Ajena")
    ajeno = iniciar_sesion(email_ajeno)
    assert ajeno.get(f"/orgs/{org}/members").status_code == 403
    assert ajeno.patch(f"/orgs/{org}/members/{lector['membership_id']}", json={"role": "owner"}).status_code == 403


def test_politica_de_otra_organizacion_es_invisible(cliente_owner, organizacion):
    org = organizacion[0]
    politica = cliente_owner.post(f"/orgs/{org}/policies", json={"name": "HF", "rule": HF}).json()
    otra, email = crear_organizacion("Otra")
    ajeno = iniciar_sesion(email)
    assert ajeno.patch(f"/orgs/{otra}/policies/{politica['id']}", json={"enabled": False}).status_code == 404
    assert ajeno.get(f"/orgs/{otra}/policies/{politica['id']}/versions").status_code == 404

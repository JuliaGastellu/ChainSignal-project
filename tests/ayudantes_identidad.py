"""Helpers de identidad para las pruebas de API (E02)."""

import uuid

from fastapi.testclient import TestClient

CONTRASENA_PRUEBA = "contrasena-sintetica-larga"


def email_unico(prefijo: str) -> str:
    return f"{prefijo}-{uuid.uuid4().hex[:10]}@ejemplo.test"


def cliente_anonimo(**kwargs) -> TestClient:
    from api.main import app

    return TestClient(app, base_url="https://testserver", **kwargs)


def crear_organizacion(nombre: str = "Org de prueba"):
    """Creo una organización con su owner y devuelvo (org_id, email_owner)."""
    from api.sesion import servicio_identidad

    email = email_unico("owner")
    org_id, _ = servicio_identidad().crear_organizacion_con_owner(nombre, email, CONTRASENA_PRUEBA)
    return org_id, email


def iniciar_sesion(email: str, contrasena: str = CONTRASENA_PRUEBA) -> TestClient:
    """Devuelvo un TestClient con sesión iniciada y el header CSRF ya cargado."""
    cliente = cliente_anonimo()
    respuesta = cliente.post("/auth/login", json={"email": email, "password": contrasena})
    assert respuesta.status_code == 200, respuesta.text
    cliente.headers["X-CSRF-Token"] = cliente.cookies.get("cs_csrf")
    return cliente


def sumar_miembro(org_id: str, cliente_owner: TestClient, rol: str):
    """Invito a alguien con el rol dado, acepta y devuelvo (cliente, email)."""
    email = email_unico(rol)
    invitacion = cliente_owner.post(f"/orgs/{org_id}/invitations", json={"email": email, "role": rol})
    assert invitacion.status_code == 201, invitacion.text
    aceptada = cliente_anonimo().post("/invitations/accept", json={"token": invitacion.json()["token"], "password": CONTRASENA_PRUEBA})
    assert aceptada.status_code == 200, aceptada.text
    return iniciar_sesion(email), email

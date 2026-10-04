"""Pruebas de la CLI de identidad: arranque y migración de configuración heredada."""

import json

import pytest

from identidad import cli
from tests.ayudantes_identidad import CONTRASENA_PRUEBA, email_unico, iniciar_sesion


def test_crear_organizacion_lee_la_contrasena_del_entorno(monkeypatch, capsys):
    email = email_unico("cli")
    monkeypatch.setenv("CHAINSIGNAL_BOOTSTRAP_PASSWORD", CONTRASENA_PRUEBA)
    assert cli.main(["crear-organizacion", "--nombre", "Org CLI", "--email", email]) == 0
    salida = json.loads(capsys.readouterr().out)
    cliente = iniciar_sesion(email)
    membresias = cliente.get("/auth/session").json()["memberships"]
    assert membresias == [{"organization_id": salida["organization_id"], "organization_name": "Org CLI",
                           "role": "owner", "membership_id": membresias[0]["membership_id"]}]


def test_crear_organizacion_rechaza_contrasena_corta(monkeypatch, capsys):
    monkeypatch.setenv("CHAINSIGNAL_BOOTSTRAP_PASSWORD", "corta")
    assert cli.main(["crear-organizacion", "--nombre", "Org", "--email", email_unico("cli")]) == 1
    assert "invalid_request" in capsys.readouterr().err


def test_importar_legado_crea_cuentas_observadas_sin_tocar_los_archivos(organizacion, tmp_path, capsys):
    org_id, email = organizacion
    tracking = tmp_path / "tracking.json"
    watch = tmp_path / "watched_wallets.json"
    tracking.write_text(json.dumps({
        "0x" + "1" * 40: {"priority": "high", "interval_seconds": 120},
        "no-es-direccion": {"priority": "low"},
    }), encoding="utf-8")
    watch.write_text(json.dumps({"wallets": [{"address": "0x" + "1" * 40, "label": "Tesorería"}, {"address": "0x" + "2" * 40}]}), encoding="utf-8")
    originales = (tracking.read_text(encoding="utf-8"), watch.read_text(encoding="utf-8"))

    assert cli.main(["importar-legado", "--organizacion", org_id, "--chain-id", "1", "--tracking", str(tracking), "--watch", str(watch)]) == 0
    resultado = json.loads(capsys.readouterr().out)
    assert resultado["imported"] == 2
    assert [s["reason"] for s in resultado["skipped"]] == ["invalid_request"]

    cuentas = {c["address"]: c for c in iniciar_sesion(email).get(f"/orgs/{org_id}/accounts").json()["accounts"]}
    assert cuentas["0x" + "1" * 40]["label"] == "Tesorería"
    assert cuentas["0x" + "1" * 40]["priority"] == "high"
    assert cuentas["0x" + "2" * 40]["chain_id"] == 1
    assert (tracking.read_text(encoding="utf-8"), watch.read_text(encoding="utf-8")) == originales

    # Reimportar no duplica.
    assert cli.main(["importar-legado", "--organizacion", org_id, "--chain-id", "1", "--tracking", str(tracking), "--watch", str(watch)]) == 0
    assert json.loads(capsys.readouterr().out)["imported"] == 0


def test_importar_legado_exige_chain_id_explicito(organizacion):
    with pytest.raises(SystemExit):
        cli.main(["importar-legado", "--organizacion", organizacion[0]])


def test_revocar_sesiones_por_email(organizacion, capsys):
    cliente = iniciar_sesion(organizacion[1])
    assert cli.main(["revocar-sesiones", "--email", organizacion[1]]) == 0
    assert json.loads(capsys.readouterr().out)["revoked_sessions"] >= 1
    assert cliente.get("/auth/session").status_code == 401

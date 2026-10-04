"""Pruebas de regresión de infra/config.py.

SAFE_WALLET_ADDRESS no tiene valor por defecto y el arranque debe fallar si
falta o si es la dirección nula o de quema. Antes el valor por defecto
apuntaba las transferencias protectoras a la dirección de quema.
"""

import pytest

from infra.config import Settings


def test_validate_raises_when_safe_wallet_address_missing_in_testnet_experiment():
    s = Settings(SAFE_WALLET_ADDRESS="", CHAINSIGNAL_MODE="TESTNET_EXPERIMENT", APP_ENV="test")
    with pytest.raises(RuntimeError):
        s.validate()


def test_read_only_starts_without_safe_wallet_wdk_token_or_seed():
    """En READ_ONLY no necesito destino de rescate, token WDK ni seed."""
    s = Settings(
        CHAINSIGNAL_MODE="READ_ONLY",
        SAFE_WALLET_ADDRESS="",
        WDK_SERVICE_TOKEN="",
    )
    assert s.validate() is True


def test_read_only_is_the_default_mode():
    # conftest quita CHAINSIGNAL_MODE del entorno, así que veo el valor por defecto real.
    assert Settings.model_fields["CHAINSIGNAL_MODE"].default == "READ_ONLY"


def test_validate_rejects_unknown_mode():
    s = Settings(CHAINSIGNAL_MODE="LIVE_TRADING")
    with pytest.raises(RuntimeError):
        s.validate()


def test_testnet_experiment_is_rejected_in_production():
    s = Settings(
        CHAINSIGNAL_MODE="TESTNET_EXPERIMENT",
        APP_ENV="production",
        SAFE_WALLET_ADDRESS="0x1234567890123456789012345678901234567890",
        WDK_SERVICE_TOKEN="test-wdk-token",
    )
    with pytest.raises(RuntimeError):
        s.validate()


def test_validate_raises_when_safe_wallet_address_is_null_address():
    s = Settings(SAFE_WALLET_ADDRESS="0x0000000000000000000000000000000000000000")
    with pytest.raises(RuntimeError):
        s.validate()


def test_validate_raises_when_safe_wallet_address_is_burn_address():
    s = Settings(SAFE_WALLET_ADDRESS="0x000000000000000000000000000000000000dEaD")
    with pytest.raises(RuntimeError):
        s.validate()


def test_validate_raises_when_safe_wallet_address_is_burn_address_case_insensitive():
    s = Settings(SAFE_WALLET_ADDRESS="0X000000000000000000000000000000000000DEAD")
    with pytest.raises(RuntimeError):
        s.validate()


def test_validate_passes_with_a_configured_non_special_address():
    s = Settings(SAFE_WALLET_ADDRESS="0x1234567890123456789012345678901234567890")
    assert s.validate() is True


def test_no_default_value_for_safe_wallet_address():
    """The field itself must not carry a burn-address (or any) default baked in."""
    assert Settings.model_fields["SAFE_WALLET_ADDRESS"].default != "0x000000000000000000000000000000000000dEaD"


# --- Controles de arranque del experimento, CORS y cookies de sesión ---
# El experimento no arranca sin secreto compartido para el canal con el
# servicio WDK. Las sesiones exigen CORS explícito y cookies Secure en producción.

def _valid_settings(**overrides):
    base = dict(
        SAFE_WALLET_ADDRESS="0x1234567890123456789012345678901234567890",
        WDK_SERVICE_TOKEN="test-wdk-token",
    )
    base.update(overrides)
    return Settings(**base)


def test_cors_wildcard_is_rejected_with_credentials():
    s = _valid_settings(CORS_ALLOWED_ORIGINS="*")
    with pytest.raises(RuntimeError):
        s.validate()


def _produccion(**overrides):
    """Producción de lectura válida (E08); cada prueba rompe una sola condición."""
    base = dict(APP_ENV="production", CHAINSIGNAL_MODE="READ_ONLY", SAFE_WALLET_ADDRESS="", WDK_SERVICE_TOKEN="",
                DATABASE_URL="postgresql+psycopg2://u:p@db:5432/cs", DB_AUTO_MIGRATE=False,
                CORS_ALLOWED_ORIGINS="https://app.ejemplo.test")
    base.update(overrides)
    return Settings(**base)


def test_production_read_only_valid_configuration_passes():
    assert _produccion().validate() is True


def test_production_requires_secure_session_cookie():
    with pytest.raises(RuntimeError, match="Secure"):
        _produccion(SESSION_COOKIE_SECURE=False).validate()


@pytest.mark.parametrize("cambio, mensaje", [
    ({"DATABASE_URL": ""}, "DATABASE_URL"),
    ({"DATABASE_URL": "sqlite:///x.db"}, "DATABASE_URL"),
    ({"DB_AUTO_MIGRATE": True}, "DB_AUTO_MIGRATE"),
    ({"CORS_ALLOWED_ORIGINS": "http://app.ejemplo.test"}, "https"),
    ({"WDK_SERVICE_TOKEN": "x"}, "secretos de firma"),
])
def test_production_operational_requirements(cambio, mensaje):
    with pytest.raises(RuntimeError, match=mensaje):
        _produccion(**cambio).validate()


def test_production_read_only_rejects_seed_in_environment(monkeypatch):
    monkeypatch.setenv("AGENT_SEED_PHRASE", "valor-que-no-imprimo")
    with pytest.raises(RuntimeError) as error:
        _produccion().validate()
    assert "AGENT_SEED_PHRASE" in str(error.value) and "valor-que-no-imprimo" not in str(error.value)


def test_validate_raises_when_wdk_service_token_missing_in_testnet_experiment():
    s = _valid_settings(WDK_SERVICE_TOKEN="", CHAINSIGNAL_MODE="TESTNET_EXPERIMENT", APP_ENV="test")
    with pytest.raises(RuntimeError):
        s.validate()


def test_validate_passes_when_everything_is_configured():
    s = _valid_settings()
    assert s.validate() is True

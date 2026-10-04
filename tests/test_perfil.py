"""Tests unitarios para el módulo perfil_wallet."""

import pytest

from generacion_features.extractor import ExtractorFeatures
from perfil_wallet.clasificador import ClasificadorWallet
from tests.fixtures import datos_wallet_activo, datos_wallet_inactivo

TIPOS_VALIDOS = {
    "trader", "defi_user", "high_activity_wallet", "low_activity_wallet", 
    "long_term_holder", "defi_power_user", "protocol_explorer", 
    "active_trader", "liquidity_provider_candidate", "experimental_wallet"
}
CONFIANZAS_VALIDAS = {"high", "medium", "low"}


@pytest.fixture
def extractor():
    return ExtractorFeatures()


@pytest.fixture
def clasificador():
    return ClasificadorWallet()


def test_clasificacion_retorna_tipo_valido(extractor, clasificador):
    datos = datos_wallet_activo()
    features = extractor.extraer(datos)
    perfil = clasificador.clasificar(features)
    assert perfil.type in TIPOS_VALIDOS


def test_clasificacion_retorna_confianza_valida(extractor, clasificador):
    datos = datos_wallet_activo()
    features = extractor.extraer(datos)
    perfil = clasificador.clasificar(features)
    assert perfil.confidence in CONFIANZAS_VALIDAS


def test_wallet_inactiva_clasificada_como_low_activity(extractor, clasificador):
    datos = datos_wallet_inactivo()
    features = extractor.extraer(datos)
    perfil = clasificador.clasificar(features)
    assert perfil.type == "low_activity_wallet"


def test_wallet_passive_holder(extractor, clasificador):
    from tests.fixtures import WALLET_MOCK, DatosWallet, crear_transaccion
    # Simular un holder pasivo: balance alto, pocas tx, mucho tiempo
    datos = DatosWallet(
        direccion=WALLET_MOCK,
        chain_id=1,
        balance_wei=10 * 10**18,
        transacciones=[crear_transaccion(timestamp=1600000000)], # Muy vieja
        transferencias_token=[]
    )
    features = extractor.extraer(datos)
    # Una sola transacción no muestra un lapso; fuerzo los días observados.
    features.dias_observados = 500
    perfil = clasificador.clasificar(features)
    assert perfil.type == "long_term_holder"


def test_descripcion_no_vacia(extractor, clasificador):
    datos = datos_wallet_activo()
    features = extractor.extraer(datos)
    perfil = clasificador.clasificar(features)
    assert len(perfil.description) > 10


def test_senales_es_lista(extractor, clasificador):
    datos = datos_wallet_activo()
    features = extractor.extraer(datos)
    perfil = clasificador.clasificar(features)
    assert isinstance(perfil.signals, list)

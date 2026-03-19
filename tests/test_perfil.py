"""Tests unitarios para el módulo perfil_wallet."""

import pytest

from generacion_features.extractor import ExtractorFeatures
from perfil_wallet.clasificador import ClasificadorWallet
from tests.fixtures import datos_wallet_activo, datos_wallet_inactivo

TIPOS_VALIDOS = {"trader", "defi_user", "high_activity_wallet", "low_activity_wallet", "long_term_holder"}
CONFIANZAS_VALIDAS = {"alta", "media", "baja"}


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
    assert perfil.tipo in TIPOS_VALIDOS


def test_clasificacion_retorna_confianza_valida(extractor, clasificador):
    datos = datos_wallet_activo()
    features = extractor.extraer(datos)
    perfil = clasificador.clasificar(features)
    assert perfil.confianza in CONFIANZAS_VALIDAS


def test_wallet_inactiva_clasificada_como_low_activity(extractor, clasificador):
    datos = datos_wallet_inactivo()
    features = extractor.extraer(datos)
    perfil = clasificador.clasificar(features)
    assert perfil.tipo == "low_activity_wallet"


def test_wallet_passive_holder(extractor, clasificador):
    from tests.fixtures import WALLET_MOCK, DatosWallet, crear_transaccion
    # Simular un holder pasivo: balance alto, pocas tx, mucho tiempo
    datos = DatosWallet(
        direccion=WALLET_MOCK,
        balance_eth=10.0,
        transacciones=[crear_transaccion(timestamp=1600000000)], # Muy vieja
        transferencias_token=[]
    )
    features = extractor.extraer(datos)
    # Forzar dias_activo alto para el test ya que extractor usa time.time()
    features.dias_activo = 500 
    perfil = clasificador.clasificar(features)
    assert perfil.tipo == "long_term_holder"


def test_descripcion_no_vacia(extractor, clasificador):
    datos = datos_wallet_activo()
    features = extractor.extraer(datos)
    perfil = clasificador.clasificar(features)
    assert len(perfil.descripcion) > 10


def test_senales_es_lista(extractor, clasificador):
    datos = datos_wallet_activo()
    features = extractor.extraer(datos)
    perfil = clasificador.clasificar(features)
    assert isinstance(perfil.senales, list)

"""Tests unitarios para el módulo generacion_features."""

import pytest

from generacion_features.extractor import ExtractorFeatures
from tests.fixtures import datos_wallet_activo, datos_wallet_inactivo, WALLET_MOCK


@pytest.fixture
def extractor():
    return ExtractorFeatures()


def test_features_wallet_activo(extractor):
    datos = datos_wallet_activo()
    features = extractor.extraer(datos)

    assert features.direccion == WALLET_MOCK
    assert features.total_transacciones > 0
    assert features.balance_eth_actual == 1.5
    assert features.tokens_unicos_utilizados >= 4
    assert features.token_mas_utilizado == "USDC"
    assert features.volumen_total_transferido_eth >= 0
    assert features.numero_wallets_interactuadas >= 1


def test_features_wallet_inactivo(extractor):
    datos = datos_wallet_inactivo()
    features = extractor.extraer(datos)

    assert features.total_transacciones == 1
    assert features.transferencias_token_total == 0
    assert features.tokens_unicos_utilizados == 0
    assert features.token_mas_utilizado == "ninguno"


def test_ratio_envios_recepciones(extractor):
    datos = datos_wallet_activo()
    features = extractor.extraer(datos)
    assert features.ratio_envios_vs_recepciones >= 0


def test_diversidad_tokens_entre_cero_y_uno(extractor):
    datos = datos_wallet_activo()
    features = extractor.extraer(datos)
    assert 0.0 <= features.diversidad_tokens <= 1.0


def test_porcentaje_contratos_en_rango_valido(extractor):
    datos = datos_wallet_activo()
    features = extractor.extraer(datos)
    assert 0.0 <= features.porcentaje_interacciones_contratos <= 100.0


def test_dias_activo_positivo(extractor):
    datos = datos_wallet_activo()
    features = extractor.extraer(datos)
    assert features.dias_activo >= 1

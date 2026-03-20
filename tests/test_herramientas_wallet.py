"""Pruebas unitarias para las herramientas relacionadas a la wallet."""

from unittest.mock import patch, MagicMock

from domain.modelos_transaccion import ResultadoTransaccion
from tools.herramienta_consultar_balance import consultar_balance
from tools.herramienta_transferir_activo import transferir_activo


@patch("tools.herramienta_consultar_balance.ServicioWDK")
def test_consultar_balance_activo(mock_servicio_class):
    """Verifica la consulta de balance cuando el WDK está activo."""
    mock_instancia = MagicMock()
    mock_instancia.consultar_balance.return_value = 1.25
    mock_servicio_class.return_value = mock_instancia

    balance = consultar_balance("0xDestino")
    
    assert balance == 1.25
    mock_instancia.consultar_balance.assert_called_once_with("0xDestino")


@patch("tools.herramienta_consultar_balance.ServicioWDK")
def test_consultar_balance_inactivo(mock_servicio_class):
    """Verifica el fallback de la consulta de balance cuando el WDK no responde."""
    mock_instancia = MagicMock()
    mock_instancia.consultar_balance.return_value = None
    mock_servicio_class.return_value = mock_instancia

    balance = consultar_balance()
    
    assert balance == 0.0


@patch("tools.herramienta_transferir_activo.ServicioWDK")
def test_transferir_activo_exitoso(mock_servicio_class):
    """Verifica la transferencia cuando el WDK está activo y exitoso."""
    mock_instancia = MagicMock()
    mock_instancia.activo = True
    
    resultado_mock = ResultadoTransaccion(
        transaction_hash="0xTxHash123",
        contract_address="",
        function="transferencia_nativa",
        success=True,
        detail="Transferencia enviada."
    )
    mock_instancia.transferir_activo.return_value = resultado_mock
    mock_servicio_class.return_value = mock_instancia

    resultado = transferir_activo("0xDestino", 10000)
    
    assert resultado.success is True
    assert resultado.transaction_hash == "0xTxHash123"
    mock_instancia.transferir_activo.assert_called_once_with("0xDestino", 10000)


@patch("tools.herramienta_transferir_activo.ServicioWDK")
def test_transferir_activo_inactivo(mock_servicio_class):
    """Verifica el fallback la transferencia cuando el WDK está inactivo."""
    mock_instancia = MagicMock()
    mock_instancia.activo = False
    mock_servicio_class.return_value = mock_instancia

    resultado = transferir_activo("0xDestino", 10000)
    
    assert resultado.success is False
    assert resultado.detail == "Microservicio WDK no está disponible para transferir."
    mock_instancia.transferir_activo.assert_not_called()

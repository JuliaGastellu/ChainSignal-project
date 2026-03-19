"""Pruebas unitarias de las herramientas del agente ChainSignal."""
from unittest.mock import patch

import pytest

from domain.modelos_contrato import InsightContrato, ContratoCompilado, ContratoDeplegado


class TestHerramientaGenerarContrato:
    def test_genera_codigo_risk_guard(self):
        from tools.herramienta_generar_contrato import generar_contrato

        insight = InsightContrato(
            tipo="risk_guard",
            wallet_analizada="0x1234567890123456789012345678901234567890",
            score_riesgo=80,
        )
        codigo = generar_contrato(insight)

        assert "contract RiskGuard" in codigo
        assert "pragma solidity" in codigo

    def test_genera_codigo_signal_lock(self):
        from tools.herramienta_generar_contrato import generar_contrato

        insight = InsightContrato(
            tipo="signal_lock",
            wallet_analizada="0xAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
            score_riesgo=10,
        )
        codigo = generar_contrato(insight)
        assert "contract SignalLock" in codigo

    def test_genera_codigo_treasury_manager(self):
        from tools.herramienta_generar_contrato import generar_contrato

        insight = InsightContrato(
            tipo="treasury_manager",
            wallet_analizada="0xBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB",
            score_riesgo=20,
            score_actividad=90,
        )
        codigo = generar_contrato(insight)
        assert "contract TreasuryManager" in codigo

    def test_tipo_invalido_lanza_excepcion(self):
        with pytest.raises(ValueError):
            InsightContrato(
                tipo="tipo_invalido",
                wallet_analizada="0x1234",
                score_riesgo=50,
            )


class TestHerramientaCompilarContrato:
    def test_compilar_risk_guard(self):
        """Verifica que la compilación del contrato RiskGuard produce ABI y bytecode."""
        from tools.herramienta_generar_contrato import generar_contrato
        from tools.herramienta_compilar_contrato import compilar_contrato_tool

        insight = InsightContrato(
            tipo="risk_guard",
            wallet_analizada="0x1234567890123456789012345678901234567890",
            score_riesgo=80,
        )
        codigo = generar_contrato(insight)
        compilado = compilar_contrato_tool(codigo)

        assert isinstance(compilado, ContratoCompilado)
        assert len(compilado.abi) > 0
        assert compilado.bytecode.startswith("0x")
        assert len(compilado.bytecode) > 10

    def test_extrae_nombre_automaticamente(self):
        from tools.herramienta_compilar_contrato import _extraer_nombre_contrato

        codigo = "// SPDX-License-Identifier: MIT\npragma solidity ^0.8.20;\ncontract MiContrato { }"
        nombre = _extraer_nombre_contrato(codigo)
        assert nombre == "MiContrato"


class TestHerramientaDesplegar:
    @patch("tools.herramienta_desplegar_contrato.ServicioWDK")
    def test_retorna_none_si_wdk_inactivo(self, MockServicio):
        from tools.herramienta_desplegar_contrato import desplegar_contrato

        instancia = MockServicio.return_value
        instancia.activo = False

        compilado = ContratoCompilado(nombre="Test", abi=[], bytecode="0x00")
        resultado = desplegar_contrato(compilado)

        assert resultado is None

    @patch("tools.herramienta_desplegar_contrato.ServicioWDK")
    def test_delega_al_servicio_cuando_activo(self, MockServicio):
        from tools.herramienta_desplegar_contrato import desplegar_contrato

        esperado = ContratoDeplegado(
            nombre="RiskGuard", direccion="0xABCD", transaction_hash="0xHASH"
        )
        instancia = MockServicio.return_value
        instancia.activo = True
        instancia.desplegar_contrato.return_value = esperado

        compilado = ContratoCompilado(nombre="RiskGuard", abi=[], bytecode="0xABC")
        resultado = desplegar_contrato(compilado)

        assert resultado == esperado
        instancia.desplegar_contrato.assert_called_once()


class TestHerramientaEjecutarFuncion:
    @patch("tools.herramienta_ejecutar_funcion.ServicioWDK")
    def test_retorna_fallido_si_wdk_inactivo(self, MockServicio):
        from tools.herramienta_ejecutar_funcion import ejecutar_funcion

        instancia = MockServicio.return_value
        instancia.activo = False

        contrato = ContratoDeplegado(
            nombre="RiskGuard", direccion="0xABCD", transaction_hash="0xHASH"
        )
        resultado = ejecutar_funcion(contrato, "actualizarPausa", args=[80])

        assert resultado.exitoso is False
        assert resultado.transaction_hash == ""


class TestHerramientaLeerEstado:
    @patch("tools.herramienta_leer_estado.ServicioWDK")
    def test_retorna_sin_valor_si_wdk_inactivo(self, MockServicio):
        from tools.herramienta_leer_estado import leer_estado

        instancia = MockServicio.return_value
        instancia.activo = False

        contrato = ContratoDeplegado(
            nombre="RiskGuard", direccion="0xABCD", transaction_hash="0xHASH"
        )
        resultado = leer_estado(contrato, "pausado")

        assert resultado.exitoso is False
        assert resultado.valor is None

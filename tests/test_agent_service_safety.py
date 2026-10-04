"""Pruebas de regresión del invariante de decisiones terminales de
services/agent_service.py.

BLOCK, MONITOR e INSUFFICIENT_DATA son terminales: ninguna señal de estrategia
(incluida una elección con force_execute=True) ni AGENT_DEMO_MODE puede
convertirlas en una decisión ejecutable.

_apply_strategy_overlay no usa `self`, así que lo llamo sin instancia (con
None) para no construir un AgentService completo con clientes de Etherscan,
WDK y Web3 solo para probar una función pura.
"""

import pytest

from infra.config import settings
from services.agent_service import AgentService, TERMINAL_DECISIONS
from strategy.modelos_estrategia import DecisionEstrategia


def _no_action_estrategia():
    return DecisionEstrategia(
        requires_contract=False,
        requires_funds_movement=False,
        requires_execution=False,
    )


def _forceful_strategy_pick():
    """Simulo un strategy_pick que antes habría forzado una ejecución."""
    return {
        "strategy": "RISK_SHIELD",
        "reason": "High risk pattern detected.",
        "confidence": 0.9,
        "trigger_signals": ["SUSPICIOUS_PATTERN"],
        "force_execute": True,
    }


class _FakeInsight:
    risk_score = 95
    activity_score = 10


@pytest.mark.parametrize("terminal_code", sorted(TERMINAL_DECISIONS))
def test_terminal_decisions_are_never_overridden(terminal_code):
    decision = {"decision": terminal_code, "reasoning": "original reasoning"}
    decision_estrategia = _no_action_estrategia()

    result_decision, result_estrategia = AgentService._apply_strategy_overlay(
        None, decision, decision_estrategia, _forceful_strategy_pick(), _FakeInsight()
    )

    assert result_decision["decision"] == terminal_code
    assert result_estrategia.requires_funds_movement is False
    assert result_estrategia.requires_swap is False


@pytest.mark.parametrize("terminal_code", sorted(TERMINAL_DECISIONS))
def test_terminal_decisions_stay_terminal_even_with_demo_mode_enabled(terminal_code, monkeypatch):
    monkeypatch.setattr(settings, "AGENT_DEMO_MODE", True)
    decision = {"decision": terminal_code, "reasoning": "original reasoning"}
    decision_estrategia = _no_action_estrategia()

    result_decision, _ = AgentService._apply_strategy_overlay(
        None, decision, decision_estrategia, _forceful_strategy_pick(), _FakeInsight()
    )

    assert result_decision["decision"] == terminal_code


def test_executable_decision_without_actionable_strategy_downgrades_to_monitor():
    decision = {"decision": "EXECUTE_BASIC", "reasoning": "original"}
    decision_estrategia = _no_action_estrategia()  # nothing actionable

    result_decision, _ = AgentService._apply_strategy_overlay(
        None, decision, decision_estrategia, _forceful_strategy_pick(), _FakeInsight()
    )

    assert result_decision["decision"] == "MONITOR"


def test_executable_decision_with_actionable_strategy_is_preserved():
    decision = {"decision": "EXECUTE_BASIC", "reasoning": "original"}
    decision_estrategia = DecisionEstrategia(
        requires_contract=True,
        requires_funds_movement=True,
        requires_execution=True,
    )

    result_decision, result_estrategia = AgentService._apply_strategy_overlay(
        None, decision, decision_estrategia, _forceful_strategy_pick(), _FakeInsight()
    )

    assert result_decision["decision"] == "EXECUTE_BASIC"
    assert result_estrategia.requires_funds_movement is True

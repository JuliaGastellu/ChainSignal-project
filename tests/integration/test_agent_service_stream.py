"""Integración manual: recorro el stream del pipeline contra Etherscan real.

Necesita ETHERSCAN_API_KEY en mi entorno local y red. Lo ejecuto con:
    CHAINSIGNAL_RUN_INTEGRATION=1 pytest -m integration tests/integration
"""

import asyncio
import json

import pytest

pytestmark = pytest.mark.integration

WALLET_PUBLICA = "0x3Bd196Ab866cB99251AcC4b62722cF0BdC5A4c13"


def test_pipeline_stream_produce_eventos():
    from services.agent_service import AgentService

    async def recorrer():
        servicio = AgentService()
        eventos = []
        async for evento in servicio.run_pipeline_stream(WALLET_PUBLICA):
            if evento.startswith("data: "):
                eventos.append(json.loads(evento[6:]))
        return eventos

    eventos = asyncio.run(recorrer())
    assert eventos, "El pipeline no produjo eventos"

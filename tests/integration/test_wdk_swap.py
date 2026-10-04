"""Integración manual del swap vía WDK en testnet.

Requiere `node wdk_service/server.js` corriendo con su propio entorno. Puede
firmar y emitir una transacción en Sepolia con la cuenta del servicio, así que
solo la ejecuto a propósito, con una wallet de prueba sin fondos reales y el
modo experimental (la capa de firma rechaza cualquier otro modo):
    CHAINSIGNAL_MODE=TESTNET_EXPERIMENT CHAINSIGNAL_RUN_INTEGRATION=1 pytest -m integration tests/integration/test_wdk_swap.py
"""

import pytest
from loguru import logger

pytestmark = pytest.mark.integration


def test_swap_flow():
    from dotenv import load_dotenv

    load_dotenv()

    from services.servicio_wdk import ServicioWDK
    from wallet_controller.wallet_agent import WalletAgent

    agent = WalletAgent()
    if not agent.wdk_active:
        pytest.skip(f"El servicio WDK no responde en {agent.wdk_url}")

    wdk = ServicioWDK()
    token_in = "ETH"
    token_out = "0xdAC17F958D2ee523a2206206994597C13D831ec7"  # gitleaks:allow (dirección pública de un token, no un secreto)
    amount_wei = 1_000_000_000_000_000  # 0.001 ETH

    quote = wdk.obtener_cotizacion_swap(token_in, token_out, amount_wei)
    if not quote:
        pytest.skip("No obtuve cotización (posible falta de liquidez en testnet)")
    logger.info("Cotización recibida: {}", quote)

    resultado = wdk.ejecutar_swap(token_in, token_out, amount_wei)
    assert resultado is not None

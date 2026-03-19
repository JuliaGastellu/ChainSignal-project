"""Test de integración manual para la nueva funcionalidad de swap de WDK."""

import os
from loguru import logger
from dotenv import load_dotenv
from wallet_controller.wallet_agent import WalletAgent
from services.servicio_wdk import ServicioWDK

def test_swap_flow():
    load_dotenv()
    
    logger.info("Iniciando test de Swap WDK...")
    
    # 1. Instanciar Agente y Servicio
    agent = WalletAgent()
    wdk = ServicioWDK()
    
    # 2. Verificar estado de WDK
    if not agent.wdk_active:
        logger.error("Servicio WDK no está respondiendo en {}. Asegúrate de que node wdk_service/server.js esté corriendo.", agent.wdk_url)
        return

    # 3. Datos de prueba (Sepolia)
    # WETH: 0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2 (Placeholder de docs)
    # USDT: 0xdAC17F958D2ee523a2206206994597C13D831ec7 (Mainnet USDt para el demo)
    token_in = "ETH"
    token_out = "0xdAC17F958D2ee523a2206206994597C13D831ec7"
    amount_wei = 1000000000000000 # 0.001 ETH
    
    # 4. Probar Cotización (Quote)
    logger.info("Fase 1: Solicitando cotización...")
    quote = wdk.obtener_cotizacion_swap(token_in, token_out, amount_wei)
    
    if quote:
        logger.success("Cotización recibida: {}", quote)
    else:
        logger.warning("No se pudo obtener la cotización (puede ser por falta de liquidez en el testnet).")
        # Continuar con el test si estamos en modo simulación
        if os.getenv("APP_ENV", "local") != "production":
            logger.info("Continuando test en modo simulación...")
        else:
            return

    # 5. Probar Ejecución (Swap)
    logger.info("Fase 2: Ejecutando swap...")
    # NOTA: Esto fallará on-chain si no hay balance real, pero validamos la comunicación con server.js
    resultado = wdk.ejecutar_swap(token_in, token_out, amount_wei)
    
    if resultado.exitoso:
        logger.success("Ejecución de swap exitosa: hash={}", resultado.transaction_hash)
    else:
        logger.error("Fallo en ejecución de swap: {}", resultado.detalle)

if __name__ == "__main__":
    test_swap_flow()

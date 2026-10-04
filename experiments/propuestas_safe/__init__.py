"""Spike E10: propuestas Safe con firma humana. FUERA DEL RUNTIME.

E10 está condicionada a que el MVP pase sus puertas comerciales (3 pilotos
pagos y 2 renovaciones) y a demanda documentada. Hoy ninguna de las dos cosas
está demostrada, así que esto es un spike revisable, no una etapa lista:

- la API y el worker no lo importan (lo verifica tests/test_propuestas_safe.py);
- no guarda ni usa claves: arma la propuesta y una guía para que una persona
  la cree y firme en su propia wallet o en Safe{Wallet};
- no envía transacciones ni llama al Safe Transaction Service.

Fuentes verificadas el 2026-10-04: safe-global/safe-deployments (Safe 1.4.1,
GnosisSafe 1.3.0, MultiSendCallOnly 1.4.1 y 1.3.0), el esquema OpenAPI del
Safe Transaction Service 6.11.0 y bgd-labs/aave-address-book (AaveV3Ethereum).
"""

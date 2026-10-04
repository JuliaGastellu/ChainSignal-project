"""Experimentos de escritura en testnet, separados del runtime comercial.

Nada de este paquete se importa desde api/ ni desde worker_lectura.py. Cada
punto de entrada exige CHAINSIGNAL_MODE=TESTNET_EXPERIMENT y rechaza
APP_ENV=production.
"""

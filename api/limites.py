"""Límite simple por clave (IP) para rutas públicas: alta y demo.

Es una ventana deslizante en memoria del proceso. Alcanza para el piloto con
una réplica; con varias réplicas necesito un contador compartido.
"""

import threading
import time
from collections import deque
from typing import Deque, Dict


class LimiteSimple:
    def __init__(self, maximo: int, ventana_segundos: float):
        self.maximo = maximo
        self.ventana = ventana_segundos
        self._marcas: Dict[str, Deque[float]] = {}
        self._lock = threading.Lock()

    def permitir(self, clave: str) -> bool:
        ahora = time.monotonic()
        with self._lock:
            marcas = self._marcas.setdefault(clave, deque())
            while marcas and ahora - marcas[0] > self.ventana:
                marcas.popleft()
            if len(marcas) >= self.maximo:
                return False
            marcas.append(ahora)
            return True

    def reiniciar(self) -> None:
        with self._lock:
            self._marcas.clear()

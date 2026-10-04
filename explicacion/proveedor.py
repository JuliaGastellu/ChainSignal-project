"""Proveedor de modelo para redactar explicaciones (E07).

Hablo con una API compatible con chat completions usando `requests`, sin SDK.
El pedido nunca declara herramientas: el modelo solo puede devolver texto y ese
texto no tiene ningún camino hacia escrituras, firmas ni cambios de política.
No le paso credenciales de firma ni datos fuera de la entrada estructurada.
"""

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol

import requests


class ErrorModelo(RuntimeError):
    def __init__(self, motivo: str, detalle: str = ""):
        super().__init__(f"{motivo}: {detalle}"[:200])
        self.motivo = motivo


@dataclass
class RespuestaModelo:
    texto: str
    tokens_entrada: int
    tokens_salida: int
    latencia_ms: int


class ProveedorModelo(Protocol):
    modelo: str

    def generar(self, mensajes: List[Dict[str, str]], max_tokens: int) -> RespuestaModelo: ...


class ProveedorChatCompletions:
    def __init__(self, base: str, clave: str, modelo: str, timeout_segundos: float):
        self.base = base.rstrip("/")
        self._clave = clave
        self.modelo = modelo
        self.timeout = timeout_segundos

    def generar(self, mensajes: List[Dict[str, str]], max_tokens: int) -> RespuestaModelo:
        cuerpo: Dict[str, Any] = {
            "model": self.modelo,
            "messages": mensajes,
            "max_tokens": max_tokens,
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        inicio = time.monotonic()
        try:
            respuesta = requests.post(
                f"{self.base}/chat/completions",
                json=cuerpo,
                headers={"Authorization": f"Bearer {self._clave}"} if self._clave else {},
                timeout=(min(5.0, self.timeout), self.timeout),
            )
        except requests.Timeout:
            raise ErrorModelo("timeout")
        except requests.RequestException as error:
            raise ErrorModelo("provider_error", type(error).__name__)
        latencia = int((time.monotonic() - inicio) * 1000)
        if respuesta.status_code == 429:
            raise ErrorModelo("rate_limited")
        if respuesta.status_code != 200:
            raise ErrorModelo("provider_error", f"HTTP {respuesta.status_code}")
        try:
            datos = respuesta.json()
            texto = datos["choices"][0]["message"]["content"]
            uso = datos.get("usage") or {}
            return RespuestaModelo(str(texto), int(uso.get("prompt_tokens", 0)), int(uso.get("completion_tokens", 0)), latencia)
        except (ValueError, KeyError, IndexError, TypeError):
            raise ErrorModelo("invalid_response")


def proveedor_desde_settings() -> Optional[ProveedorModelo]:
    from infra.config import settings

    if not settings.EXPLANATION_MODEL_ENABLED:
        return None
    return ProveedorChatCompletions(settings.EXPLANATION_API_BASE, settings.EXPLANATION_API_KEY,
                                    settings.EXPLANATION_MODEL, settings.EXPLANATION_TIMEOUT_SECONDS)

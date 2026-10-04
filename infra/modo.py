"""Modo de runtime y guarda única de escritura on-chain.

ChainSignal arranca en READ_ONLY. En ese modo ningún camino del código puede
firmar, transferir, hacer swap, desplegar contratos ni pedirle al servicio WDK
que lo haga. La API comercial nunca habilita escritura, en ningún modo.

TESTNET_EXPERIMENT solo existe para los experimentos de experiments/, que
corro a mano fuera de la API. Aun en ese modo me niego a escribir si APP_ENV es
production.
"""

from enum import Enum


class ModoRuntime(str, Enum):
    READ_ONLY = "READ_ONLY"
    TESTNET_EXPERIMENT = "TESTNET_EXPERIMENT"


class EscrituraDeshabilitada(RuntimeError):
    """La lanzo cuando algo intenta firmar o enviar fuera del modo experimental."""


def modo_actual() -> ModoRuntime:
    from infra.config import settings

    return ModoRuntime(settings.CHAINSIGNAL_MODE)


def escritura_habilitada() -> bool:
    from infra.config import settings

    return modo_actual() is ModoRuntime.TESTNET_EXPERIMENT and not settings.is_production


def exigir_escritura_experimental(operacion: str) -> None:
    """Corto cualquier operación de firma o envío salvo en el experimento testnet.

    La llamo al comienzo de cada método que firma o pide firmar. Leo la
    configuración en cada llamada para que un cambio de modo no quede cacheado.
    """
    from infra.config import settings

    if modo_actual() is not ModoRuntime.TESTNET_EXPERIMENT:
        raise EscrituraDeshabilitada(
            f"'{operacion}' está deshabilitada: ChainSignal corre en modo {settings.CHAINSIGNAL_MODE} (solo lectura)."
        )
    if settings.is_production:
        raise EscrituraDeshabilitada(
            f"'{operacion}' está deshabilitada: los experimentos de escritura nunca corren con APP_ENV=production."
        )

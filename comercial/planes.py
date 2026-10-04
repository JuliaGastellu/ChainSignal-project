"""Planes del piloto de lectura (E09).

Tomo el alcance de docs/ESTRATEGIA_PRODUCTO.md: hasta 10 cuentas, una red y un
mercado (Ethereum mainnet, Aave V3) y acompañamiento. El precio de USD 150 por
organización y mes es una hipótesis a validar, no una tarifa comprobada; lo
muestro así en la interfaz.

La prueba dura 14 días con el mismo alcance que el piloto. Los límites los aplico
en el backend; la interfaz solo los muestra.
"""

from dataclasses import asdict, dataclass
from typing import Dict, Tuple


@dataclass(frozen=True)
class Limites:
    max_cuentas: int
    intervalo_minimo_segundos: int
    redes: Tuple[int, ...]
    mercados: Tuple[str, ...]

    def presentar(self) -> Dict[str, object]:
        datos = asdict(self)
        return {"max_accounts": datos["max_cuentas"], "min_interval_seconds": datos["intervalo_minimo_segundos"],
                "chains": list(datos["redes"]), "markets": list(datos["mercados"])}


@dataclass(frozen=True)
class Plan:
    id: str
    nombre: str
    limites: Limites
    limites_prueba: Limites
    dias_prueba: int
    precio_referencia_usd: str
    precio_es_hipotesis: bool
    acompanamiento: bool


PILOTO = Plan(
    id="pilot",
    nombre="Piloto de lectura",
    limites=Limites(max_cuentas=10, intervalo_minimo_segundos=60, redes=(1,), mercados=("aave-v3-ethereum",)),
    # La prueba tiene el mismo alcance que el piloto y solo difiere en duración:
    # quiero que el piloto se evalúe con el servicio que se pagaría.
    limites_prueba=Limites(max_cuentas=10, intervalo_minimo_segundos=60, redes=(1,), mercados=("aave-v3-ethereum",)),
    dias_prueba=14,
    precio_referencia_usd="150",
    precio_es_hipotesis=True,
    acompanamiento=True,
)

# Las demos no tienen suscripción: su servicio es sintético y vencen solas.
LIMITES_DEMO = Limites(max_cuentas=3, intervalo_minimo_segundos=300, redes=(1,), mercados=("aave-v3-ethereum",))

PLANES: Dict[str, Plan] = {PILOTO.id: PILOTO}

DIAS_PERIODO = 30
DIAS_GRACIA = 7

"""Helpers para probar el monitoreo sobre SQLite o PostgreSQL sin red.

AdaptadorControlado reutiliza las fixtures Aave V3 codificadas con el ABI real
(tests/fixture_aave.py): cambio el escenario entre pasadas para mover el health
factor, forzar un 429 o simular un reorg.
"""

import time
from typing import Optional

from identidad.recursos import ServicioRecursos
from identidad.servicio import ServicioIdentidad
from ingestion_onchain.resultados import ErrorProveedor, Motivo
from monitoreo.notificaciones import ServicioNotificaciones, TransporteFalso
from monitoreo.worker import WorkerMonitoreo
from protocolos.aave_v3 import AdaptadorAaveV3
from protocolos.replay import LectorReproduccion
from tests.fixture_aave import USUARIO, EscenarioAave, escenario_con_health_factor

CONTRASENA = "contrasena-sintetica-larga"


class Reloj:
    def __init__(self):
        self.ahora = time.time()

    def __call__(self) -> float:
        return self.ahora

    def avanzar(self, segundos: float) -> None:
        self.ahora += segundos


def direccion_de_cuenta(i: int) -> str:
    return USUARIO if i == 0 else "0x" + f"{i:040x}"


def escenario_hf(hf_objetivo: str, bloque: int = 20_000_000, cuentas: int = 1) -> EscenarioAave:
    return escenario_con_health_factor(hf_objetivo, [direccion_de_cuenta(i) for i in range(cuentas)], bloque)


class LectorQueFalla:
    red = None

    def __init__(self, motivo: Motivo):
        from infra.red import ETHEREUM

        self.red = ETHEREUM
        self.motivo = motivo

    def _fallar(self, *args):
        raise ErrorProveedor(self.motivo, self.motivo.value, reintentable=True)

    bloque_actual = bloque = eth_call = _fallar


class AdaptadorControlado:
    def __init__(self, escenario: Optional[EscenarioAave] = None):
        self.fixture = (escenario or escenario_hf("2.0")).fixture()
        self.falla: Optional[Motivo] = None
        self.lecturas = 0

    def poner(self, escenario: EscenarioAave, hash_bloque: Optional[str] = None) -> None:
        self.fixture = escenario.fixture()
        if hash_bloque is not None:
            self.fixture["blocks"][str(escenario.bloque)]["hash"] = hash_bloque

    def __call__(self) -> AdaptadorAaveV3:
        self.lecturas += 1
        lector = LectorQueFalla(self.falla) if self.falla else LectorReproduccion(self.fixture)
        return AdaptadorAaveV3(lector)


class Entorno:
    """Organización con una cuenta observada, un canal sandbox y servicios sobre un engine."""

    def __init__(self, engine, regla: dict, reloj: Optional[Reloj] = None, cuentas: int = 1, transportes=None):
        import uuid

        self.engine = engine
        self.reloj = reloj or Reloj()
        self.identidad = ServicioIdentidad(engine)
        self.recursos = ServicioRecursos(engine)
        email = f"owner-{uuid.uuid4().hex[:8]}@ejemplo.test"
        self.org_id, _ = self.identidad.crear_organizacion_con_owner("Org monitoreo", email, CONTRASENA)
        self.email = email
        token, _, sesion = self.identidad.crear_sesion(self.identidad.autenticar(email, CONTRASENA))
        self.ctx = self.identidad.contexto(sesion, self.org_id, "owner")
        self.cuentas = []
        for i in range(cuentas):
            self.cuentas.append(self.recursos.crear_cuenta(self.ctx, direccion_de_cuenta(i), 1, None, "high", 60)["id"])
        self.politica = self.recursos.crear_politica(self.ctx, "Regla de prueba", regla)
        self.transporte = TransporteFalso()
        self.transportes = transportes or {"sandbox": self.transporte, "webhook": self.transporte}
        self.notificaciones = ServicioNotificaciones(engine, self.reloj, self.transportes)
        self.canal = self.notificaciones.crear_canal(self.ctx, "sandbox", "Canal de prueba", {})
        self.adaptador = AdaptadorControlado(escenario_hf("2.0", cuentas=cuentas))
        self.n_cuentas = cuentas

    def worker(self, nombre: str = "w1", lease: float = 60.0, engine=None) -> WorkerMonitoreo:
        return WorkerMonitoreo(self.adaptador, engine or self.engine, self.reloj, nombre, lease_segundos=lease,
                               max_intentos=3, transportes=self.transportes)

    def siguiente_ronda(self, segundos: float = 61) -> None:
        self.reloj.avanzar(segundos)

    def tabla(self, modelo, **filtros):
        from sqlalchemy import select

        from infra.db import get_session_factory

        with get_session_factory(self.engine)() as s:
            consulta = select(modelo)
            for campo, valor in filtros.items():
                consulta = consulta.where(getattr(modelo, campo) == valor)
            return s.execute(consulta).scalars().all()

"""Estados, registro write-ahead y reconciliación de propuestas (spike E10).

Estados distintos para cada situación:

- PROPUESTA: armada y simulada, sin aprobar;
- APROBADA: una persona aprobó esta huella exacta;
- INCIERTA: empecé a entregarla y no sé si llegó (o el proveedor no respondió);
- ENVIADA: el servicio o la red la recibió, con su safeTxHash;
- CONFIRMADA: se ejecutó y observé el efecto esperado;
- FALLIDA: se rechazó, revirtió o venció, otra transacción usó el nonce, o el efecto no apareció;
- PARCIAL: solo para lotes secuenciales no atómicos (hoy no los armo).

Persisto la intención y su payload antes de entregarlos (write-ahead): paso a
INCIERTA, entrego y recién con respuesta paso a ENVIADA. Si se corta en el
medio, la propuesta queda INCIERTA y no la reenvío hasta reconciliar: busco
el safeTxHash en el servicio y miro el nonce del Safe. Solo si determino que no
llegó y el nonce sigue libre vuelve a APROBADA.

No hay firma automática: el transporte entrega una propuesta que una persona
firma en su wallet. El registro es un SQLite propio del spike, no la base del producto.
"""

import json
import sqlite3
import time
from dataclasses import asdict
from typing import Any, Callable, Dict, List, Optional, Protocol

from experiments.propuestas_safe.propuesta import Aprobacion, Contexto, Intencion, validar_para_envio

PROPUESTA, APROBADA, INCIERTA, ENVIADA, CONFIRMADA, FALLIDA, PARCIAL = (
    "PROPUESTA", "APROBADA", "INCIERTA", "ENVIADA", "CONFIRMADA", "FALLIDA", "PARCIAL")
TRANSICIONES = {
    PROPUESTA: {APROBADA, FALLIDA},
    APROBADA: {INCIERTA, FALLIDA},
    INCIERTA: {ENVIADA, APROBADA, CONFIRMADA, FALLIDA, PARCIAL},
    ENVIADA: {CONFIRMADA, FALLIDA, PARCIAL, INCIERTA},
    CONFIRMADA: set(), FALLIDA: set(), PARCIAL: set(),
}


class TransicionInvalida(RuntimeError):
    pass


class EnvioRechazado(RuntimeError):
    def __init__(self, errores: List[str]):
        super().__init__(", ".join(errores))
        self.errores = errores


class Transporte(Protocol):
    def entregar(self, intencion: Intencion) -> str: ...  # devuelve safeTxHash aceptado; puede lanzar TimeoutError


class Consulta(Protocol):
    def buscar(self, safe_tx_hash: str) -> Optional[Dict[str, Any]]: ...  # None | {"executed": bool, "success": bool, "tx_hash": str}
    def nonce_actual(self, safe: str) -> int: ...
    def efecto(self, efecto_esperado: Dict[str, Any], tx_hash: str) -> bool: ...


class Registro:
    def __init__(self, ruta: str = ":memory:"):
        self.db = sqlite3.connect(ruta, isolation_level=None, check_same_thread=False)
        self.db.execute("""CREATE TABLE IF NOT EXISTS propuestas (
            id TEXT PRIMARY KEY, clave_idempotencia TEXT UNIQUE NOT NULL, huella TEXT NOT NULL, estado TEXT NOT NULL,
            payload TEXT NOT NULL, safe_tx_hash TEXT NOT NULL, aprobacion TEXT, detalle TEXT, actualizada_en REAL NOT NULL)""")
        self.db.execute("""CREATE TABLE IF NOT EXISTS transiciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT, propuesta_id TEXT NOT NULL, de TEXT, a TEXT NOT NULL, detalle TEXT, en REAL NOT NULL)""")

    def crear(self, intencion: Intencion, clave_idempotencia: str) -> str:
        """Una segunda solicitud con la misma clave devuelve la propuesta existente, no crea otra."""
        fila = self.db.execute("SELECT id FROM propuestas WHERE clave_idempotencia = ?", (clave_idempotencia,)).fetchone()
        if fila:
            return fila[0]
        self.db.execute("INSERT INTO propuestas VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, ?)",
                        (intencion.id, clave_idempotencia, intencion.huella(), PROPUESTA,
                         json.dumps(asdict(intencion), default=str, sort_keys=True), intencion.safe_tx_hash, time.time()))
        self.db.execute("INSERT INTO transiciones (propuesta_id, de, a, detalle, en) VALUES (?, NULL, ?, ?, ?)",
                        (intencion.id, PROPUESTA, "created", time.time()))
        return intencion.id

    def estado(self, propuesta_id: str) -> str:
        return self.db.execute("SELECT estado FROM propuestas WHERE id = ?", (propuesta_id,)).fetchone()[0]

    def detalle(self, propuesta_id: str) -> Optional[str]:
        return self.db.execute("SELECT detalle FROM propuestas WHERE id = ?", (propuesta_id,)).fetchone()[0]

    def historia(self, propuesta_id: str) -> List[str]:
        return [a for (a,) in self.db.execute("SELECT a FROM transiciones WHERE propuesta_id = ? ORDER BY id", (propuesta_id,))]

    def anotar(self, propuesta_id: str, detalle: str) -> None:
        self.db.execute("UPDATE propuestas SET detalle = ?, actualizada_en = ? WHERE id = ?", (detalle, time.time(), propuesta_id))

    def transicionar(self, propuesta_id: str, de: str, a: str, detalle: str = "", aprobacion: Optional[Aprobacion] = None) -> None:
        if a not in TRANSICIONES[de]:
            raise TransicionInvalida(f"{de} -> {a}")
        extra = ", aprobacion = ?" if aprobacion else ""
        valores = [a, detalle, time.time()] + ([json.dumps(asdict(aprobacion))] if aprobacion else []) + [propuesta_id, de]
        cursor = self.db.execute(f"UPDATE propuestas SET estado = ?, detalle = ?, actualizada_en = ?{extra} WHERE id = ? AND estado = ?",
                                 valores)
        if cursor.rowcount != 1:
            raise TransicionInvalida(f"proposal is no longer {de}")  # otro proceso la movió (compare-and-set)
        self.db.execute("INSERT INTO transiciones (propuesta_id, de, a, detalle, en) VALUES (?, ?, ?, ?, ?)",
                        (propuesta_id, de, a, detalle, time.time()))


class Coordinador:
    def __init__(self, registro: Registro, reloj: Callable[[], float] = time.time):
        self.registro = registro
        self.reloj = reloj

    def aprobar(self, intencion: Intencion, aprobacion: Aprobacion) -> None:
        if aprobacion.huella != intencion.huella():
            raise EnvioRechazado(["approval_does_not_match_payload"])
        self.registro.transicionar(intencion.id, PROPUESTA, APROBADA, f"approved by {aprobacion.aprobada_por}", aprobacion)

    def entregar(self, intencion: Intencion, aprobacion: Aprobacion, ctx: Contexto, transporte: Transporte) -> str:
        estado = self.registro.estado(intencion.id)
        if estado == INCIERTA:
            raise EnvioRechazado(["uncertain_reconcile_first"])  # nunca reenvío sin saber qué pasó
        if estado != APROBADA:
            raise EnvioRechazado([f"state_{estado.lower()}"])
        errores = validar_para_envio(intencion, aprobacion, ctx)
        if errores:
            if "expired" in errores:
                self.registro.transicionar(intencion.id, APROBADA, FALLIDA, "expired")
            raise EnvioRechazado(errores)
        # Write-ahead: dejo constancia de que voy a entregar antes de hacerlo.
        self.registro.transicionar(intencion.id, APROBADA, INCIERTA, "delivery started")
        try:
            hash_aceptado = transporte.entregar(intencion)
        except Exception as error:
            # Timeout o caída: puede haber llegado o no. Queda INCIERTA hasta reconciliar.
            self.registro.anotar(intencion.id, f"delivery outcome unknown: {type(error).__name__}")
            return INCIERTA
        if hash_aceptado != intencion.safe_tx_hash:
            self.registro.transicionar(intencion.id, INCIERTA, FALLIDA, "service returned a different safeTxHash")
            return FALLIDA
        self.registro.transicionar(intencion.id, INCIERTA, ENVIADA, "accepted")
        return ENVIADA

    def reconciliar(self, intencion: Intencion, consulta: Consulta) -> str:
        estado = self.registro.estado(intencion.id)
        if estado not in (INCIERTA, ENVIADA):
            return estado
        encontrada = consulta.buscar(intencion.safe_tx_hash)
        if encontrada is None:
            if consulta.nonce_actual(intencion.safe) > intencion.nonce:
                self.registro.transicionar(intencion.id, estado, FALLIDA, "nonce used by another transaction")
                return FALLIDA
            if estado == INCIERTA:
                # Determiné que no llegó y el nonce sigue libre: se puede volver a entregar.
                self.registro.transicionar(intencion.id, INCIERTA, APROBADA, "not delivered; safe to deliver again")
                return APROBADA
            return estado
        if estado == INCIERTA:
            self.registro.transicionar(intencion.id, INCIERTA, ENVIADA, "found in the service after an uncertain delivery")
            estado = ENVIADA
        if not encontrada.get("executed"):
            return ENVIADA  # esperando firmas o ejecución
        if not encontrada.get("success"):
            self.registro.transicionar(intencion.id, ENVIADA, FALLIDA, f"execution reverted: {encontrada.get('tx_hash')}")
            return FALLIDA
        if not consulta.efecto(intencion.efecto_esperado, encontrada["tx_hash"]):
            # Receipt exitoso sin el efecto esperado: no lo doy por bueno. Requiere revisión humana.
            self.registro.transicionar(intencion.id, ENVIADA, FALLIDA, "successful receipt without the expected effect; needs review")
            return FALLIDA
        self.registro.transicionar(intencion.id, ENVIADA, CONFIRMADA, f"executed: {encontrada['tx_hash']}")
        return CONFIRMADA

"""Ingesta incremental del historial de una wallet, con checkpoints y calidad.

Por flujo (transactions, tokens) guardo un checkpoint en la base:
- covered_from_block: bloque más bajo que tengo completo (0 si tengo todo).
- confirmed_block/hash: hasta dónde ingerí con INGESTION_CONFIRMATIONS de margen.

Primer sync: recorro de lo más nuevo hacia atrás, con tope de páginas. Así la
ventana reciente nunca queda truncada; si llego al tope, lo declaro como
historial incompleto en lugar de inventar una edad.

Syncs siguientes: verifico que el hash del bloque confirmado no cambió (si
cambió, hubo reorg y retrocedo INGESTION_REORG_DEPTH bloques), borro las filas
no confirmadas y avanzo desde confirmed_block + 1.

La base hace de caché: dentro de INGESTION_CACHE_TTL_SECONDS no consulto al
proveedor. Si el proveedor falla y tengo datos guardados, los devuelvo como
STALE; si no tengo nada, UNAVAILABLE. Nunca devuelvo una lista vacía por error.
"""

import time
import zlib
from typing import Callable, List, Optional, Tuple

from sqlalchemy import delete, select, text
from sqlalchemy.engine import Engine

from infra.config import settings
from infra.db import engine as engine_por_defecto
from infra.db import get_session_factory, init_db
from infra.db_models import ChainTransactionRecord, IngestionCheckpointRecord
from infra.red import Red, RedIncorrecta
from ingestion_onchain.modelos import DatosWallet, Token, Transaccion, TransferenciaToken
from ingestion_onchain.resultados import (
    BloqueRef,
    Calidad,
    ErrorProveedor,
    Motivo,
    Procedencia,
    ResultadoIngesta,
    combinar,
)

FLUJOS = ("transactions", "tokens")
# Etherscan no devuelve más de 10.000 filas por consulta (page * offset).
_FILAS_MAXIMAS_POR_CONSULTA = 10_000


def validar_direccion(direccion: str) -> str:
    d = (direccion or "").strip().lower()
    if len(d) != 42 or not d.startswith("0x"):
        raise ValueError("Address must be a 0x-prefixed 20-byte hex string.")
    int(d[2:], 16)
    return d


class ServicioIngesta:
    def __init__(self, red: Red, historial, rpc=None, engine_: Optional[Engine] = None,
                 reloj: Callable[[], float] = time.time):
        """historial: proveedor con verificar_red/bloque_actual/bloque/pagina (ClienteEtherscan).
        rpc: RpcLectura opcional; si está, fijo el balance al bloque de referencia."""
        if historial.red.chain_id != red.chain_id or (rpc is not None and rpc.red.chain_id != red.chain_id):
            raise ValueError("All providers must target the same network.")
        self.red = red
        self.historial = historial
        self.rpc = rpc
        self.reloj = reloj
        self._engine = engine_ or engine_por_defecto
        init_db(self._engine)
        self._Session = get_session_factory(self._engine)

    # --- API pública ------------------------------------------------------------

    def obtener_datos_wallet(self, direccion: str) -> DatosWallet:
        direccion = validar_direccion(direccion)
        componentes = {}
        filas = {}
        referencia = None
        for flujo in FLUJOS:
            resultado, filas[flujo] = self._sincronizar(direccion, flujo)
            componentes[flujo] = resultado
            referencia = referencia or resultado.procedencia.referencia
        balance_resultado, balance_wei = self._balance(direccion, referencia)
        componentes["balance"] = balance_resultado
        return DatosWallet(
            direccion=direccion,
            chain_id=self.red.chain_id,
            balance_wei=balance_wei,
            transacciones=filas["transactions"],
            transferencias_token=filas["tokens"],
            calidad=combinar(componentes),
        )

    # --- balance -------------------------------------------------------------------

    def _balance(self, direccion: str, referencia: Optional[BloqueRef]) -> Tuple[ResultadoIngesta, Optional[int]]:
        ahora = self.reloj()
        try:
            if self.rpc is not None and referencia is not None:
                valor = self.rpc.balance(direccion, referencia.numero)
                procedencia = Procedencia("rpc", self.red.chain_id, self.red.nombre, referencia, ahora)
                return ResultadoIngesta(Calidad.FRESH, procedencia), valor
            valor = self.historial.balance_ultimo(direccion)
            procedencia = Procedencia(self.historial.nombre, self.red.chain_id, self.red.nombre, None, ahora)
            return ResultadoIngesta(Calidad.FRESH, procedencia, detalle="latest tag; not pinned to a block"), valor
        except RedIncorrecta as e:
            return self._no_disponible(Motivo.RED_INCORRECTA, str(e), "rpc"), None
        except ErrorProveedor as e:
            return self._no_disponible(e.motivo, e.detalle, "rpc" if self.rpc else self.historial.nombre), None

    def _no_disponible(self, motivo: Motivo, detalle: str, proveedor: str) -> ResultadoIngesta:
        return ResultadoIngesta(Calidad.UNAVAILABLE, Procedencia(proveedor, self.red.chain_id, self.red.nombre, None, self.reloj()),
                                motivo, detalle)

    # --- historial -----------------------------------------------------------------

    def _checkpoint(self, s, direccion: str, flujo: str) -> Optional[IngestionCheckpointRecord]:
        return s.execute(select(IngestionCheckpointRecord).where(
            IngestionCheckpointRecord.chain_id == self.red.chain_id,
            IngestionCheckpointRecord.address == direccion,
            IngestionCheckpointRecord.stream == flujo,
        )).scalar_one_or_none()

    def _procedencia(self, cp: IngestionCheckpointRecord, reorg: bool = False) -> Procedencia:
        referencia = None
        if cp.reference_block is not None and cp.reference_block_hash:
            referencia = BloqueRef(cp.reference_block, cp.reference_block_hash, cp.reference_block_timestamp or 0)
        return Procedencia(
            proveedor=cp.provider, chain_id=self.red.chain_id, red=self.red.nombre, referencia=referencia,
            obtenido_en=cp.synced_at, desde_bloque=cp.covered_from_block, hasta_bloque=cp.reference_block,
            historial_completo=bool(cp.complete_history), paginas=cp.pages, reorg_detectado=reorg,
        )

    def _leer_filas(self, s, direccion: str, flujo: str, desde: Optional[int]) -> list:
        consulta = select(ChainTransactionRecord).where(
            ChainTransactionRecord.chain_id == self.red.chain_id,
            ChainTransactionRecord.address == direccion,
            ChainTransactionRecord.stream == flujo,
        )
        if desde is not None:
            consulta = consulta.where(ChainTransactionRecord.block_number >= desde)
        registros = s.execute(consulta.order_by(ChainTransactionRecord.block_number.desc(), ChainTransactionRecord.id)).scalars().all()
        return [self._a_modelo(r) for r in registros]

    def _a_modelo(self, r: ChainTransactionRecord):
        if r.stream == "transactions":
            return Transaccion(r.tx_hash, r.block_number, r.timestamp, r.from_addr, r.to_addr, int(r.value_raw),
                               r.gas_used or 0, r.is_error, r.is_contract_call, r.block_hash or "")
        return TransferenciaToken(r.tx_hash, r.block_number, r.timestamp, r.from_addr, r.to_addr,
                                  Token(r.chain_id, r.token_contract, r.token_decimals, r.token_symbol or ""),
                                  int(r.value_raw), r.block_hash or "")

    def _a_registro(self, direccion: str, flujo: str, f) -> ChainTransactionRecord:
        base = dict(chain_id=self.red.chain_id, address=direccion, stream=flujo, block_number=f.bloque,
                    block_hash=f.hash_bloque or None, tx_hash=f.hash, timestamp=f.timestamp,
                    from_addr=f.origen, to_addr=f.destino)
        if flujo == "transactions":
            return ChainTransactionRecord(**base, value_raw=str(f.valor_wei), gas_used=f.gas_utilizado,
                                          is_error=f.es_error, is_contract_call=f.es_contrato)
        return ChainTransactionRecord(**base, value_raw=str(f.cantidad_raw), is_error=False, is_contract_call=False,
                                      token_contract=f.token.contrato, token_decimals=f.token.decimales,
                                      token_symbol=f.token.simbolo or None)

    def _paginar(self, direccion: str, flujo: str, desde: int, hasta: int, orden: str):
        """Pido páginas hasta agotar la ventana o el tope. Devuelvo
        (filas, paginas, agotada, falla). Si una consulta llega a 10.000 filas,
        sigo desde el bloque límite y lo vuelvo a pedir completo."""
        tamanio = settings.INGESTION_PAGE_SIZE
        paginas_por_consulta = max(1, _FILAS_MAXIMAS_POR_CONSULTA // tamanio)
        filas: list = []
        paginas, pagina = 0, 1
        while paginas < settings.INGESTION_MAX_PAGES:
            try:
                lote = self.historial.pagina(direccion, flujo, desde, hasta, pagina, tamanio, orden)
            except ErrorProveedor as error:
                return filas, paginas, False, error
            paginas += 1
            filas.extend(lote)
            if len(lote) < tamanio:
                return filas, paginas, True, None
            if pagina >= paginas_por_consulta:
                borde = min(f.bloque for f in lote) if orden == "desc" else max(f.bloque for f in lote)
                if all(f.bloque == borde for f in lote):
                    return filas, paginas, False, ErrorProveedor(Motivo.PAGINACION_INCOMPLETA, "single block exceeds query window")
                filas = [f for f in filas if f.bloque != borde]
                if orden == "desc":
                    hasta = borde
                else:
                    desde = borde
                pagina = 1
            else:
                pagina += 1
        return filas, paginas, False, None

    def _sincronizar(self, direccion: str, flujo: str) -> Tuple[ResultadoIngesta, list]:
        ahora = self.reloj()
        with self._Session() as s:
            cp = self._checkpoint(s, direccion, flujo)
            if cp is not None and cp.synced_at is not None and ahora - cp.synced_at < settings.INGESTION_CACHE_TTL_SECONDS:
                filas = self._leer_filas(s, direccion, flujo, cp.covered_from_block)
                return ResultadoIngesta(Calidad.FRESH, self._procedencia(cp), sin_actividad=not filas, filas=len(filas),
                                        detalle="served from cache within TTL"), filas
            sincronizado_antes = cp.synced_at if cp is not None else None

        try:
            plan = self._consultar_proveedor(direccion, flujo, cp)
        except (ErrorProveedor, RedIncorrecta) as error:
            motivo = Motivo.RED_INCORRECTA if isinstance(error, RedIncorrecta) else error.motivo
            detalle = str(error) if isinstance(error, RedIncorrecta) else error.detalle
            if cp is not None and cp.synced_at is not None and motivo is not Motivo.RED_INCORRECTA:
                with self._Session() as s:
                    cp = self._checkpoint(s, direccion, flujo)
                    filas = self._leer_filas(s, direccion, flujo, cp.covered_from_block)
                    return ResultadoIngesta(Calidad.STALE, self._procedencia(cp), motivo, detalle,
                                            sin_actividad=not filas, filas=len(filas)), filas
            return self._no_disponible(motivo, detalle, self.historial.nombre), []

        return self._guardar(direccion, flujo, plan, sincronizado_antes, ahora)

    def _consultar_proveedor(self, direccion: str, flujo: str, cp: Optional[IngestionCheckpointRecord]) -> dict:
        cabeza = self.historial.bloque_actual()
        referencia = self.historial.bloque(cabeza)
        confirmaciones = settings.INGESTION_CONFIRMATIONS
        reorg = False
        confirmado = cp.confirmed_block if cp is not None else None
        desde_cubierto = cp.covered_from_block if cp is not None else None
        completo = bool(cp.complete_history) if cp is not None else False

        if confirmado is not None and cp.confirmed_block_hash:
            actual = self.historial.bloque(confirmado)
            if actual.hash != cp.confirmed_block_hash:
                reorg = True
                confirmado = max((desde_cubierto or 0) - 1, confirmado - settings.INGESTION_REORG_DEPTH)

        if confirmado is None:
            filas, paginas, agotada, falla = self._paginar(direccion, flujo, 0, cabeza, "desc")
            if falla is not None and not filas:
                raise falla
            if agotada and falla is None:
                desde_cubierto, completo = 0, True
            else:
                # El bloque más bajo puede haber quedado a medias: lo descarto.
                bajo = min(f.bloque for f in filas)
                filas = [f for f in filas if f.bloque != bajo]
                desde_cubierto, completo = bajo + 1, False
            nuevo_confirmado = cabeza - confirmaciones
            if nuevo_confirmado < desde_cubierto:
                nuevo_confirmado = None
            borrar_desde = -1  # primer sync: reemplazo todo
        else:
            filas, paginas, agotada, falla = self._paginar(direccion, flujo, confirmado + 1, cabeza, "asc")
            if falla is not None and not filas:
                raise falla
            if agotada and falla is None:
                nuevo_confirmado = max(confirmado, cabeza - confirmaciones)
            else:
                alto = max(f.bloque for f in filas) if filas else confirmado + 1
                filas = [f for f in filas if f.bloque != alto]
                nuevo_confirmado = min(alto - 1, cabeza - confirmaciones)
                if falla is None:
                    falla = ErrorProveedor(Motivo.PAGINACION_INCOMPLETA, "page cap reached before catching up")
            borrar_desde = confirmado + 1

        hash_confirmado = self.historial.bloque(nuevo_confirmado).hash if nuevo_confirmado is not None and nuevo_confirmado >= 0 else None
        return dict(filas=filas, paginas=paginas, falla=falla, referencia=referencia, reorg=reorg,
                    desde_cubierto=desde_cubierto, completo=completo, confirmado=nuevo_confirmado,
                    hash_confirmado=hash_confirmado, borrar_desde=borrar_desde)

    def _bloquear(self, s, direccion: str, flujo: str) -> None:
        # Serializo escrituras concurrentes del mismo flujo entre procesos.
        if s.bind.dialect.name == "postgresql":
            clave = zlib.crc32(f"{self.red.chain_id}:{direccion}:{flujo}".encode())
            s.execute(text("SELECT pg_advisory_xact_lock(:clave)"), {"clave": clave})

    def _guardar(self, direccion: str, flujo: str, plan: dict, sincronizado_antes: Optional[float], ahora: float):
        with self._Session() as s:
            self._bloquear(s, direccion, flujo)
            cp = self._checkpoint(s, direccion, flujo)
            if cp is not None and cp.synced_at != sincronizado_antes:
                # Otro proceso sincronizó mientras yo consultaba: uso lo suyo.
                filas = self._leer_filas(s, direccion, flujo, cp.covered_from_block)
                return ResultadoIngesta(Calidad.FRESH, self._procedencia(cp), sin_actividad=not filas, filas=len(filas),
                                        detalle="synced concurrently by another process"), filas
            borrado = delete(ChainTransactionRecord).where(
                ChainTransactionRecord.chain_id == self.red.chain_id,
                ChainTransactionRecord.address == direccion,
                ChainTransactionRecord.stream == flujo,
                ChainTransactionRecord.block_number >= plan["borrar_desde"],
            )
            s.execute(borrado)
            s.add_all([self._a_registro(direccion, flujo, f) for f in plan["filas"]])
            if cp is None:
                cp = IngestionCheckpointRecord(chain_id=self.red.chain_id, address=direccion, stream=flujo,
                                               complete_history=False, provider=self.historial.nombre, pages=0)
                s.add(cp)
            referencia: BloqueRef = plan["referencia"]
            cp.covered_from_block = plan["desde_cubierto"]
            cp.complete_history = plan["completo"]
            cp.confirmed_block = plan["confirmado"]
            cp.confirmed_block_hash = plan["hash_confirmado"]
            cp.reference_block, cp.reference_block_hash, cp.reference_block_timestamp = referencia.numero, referencia.hash, referencia.timestamp
            cp.provider = self.historial.nombre
            cp.synced_at = ahora
            cp.pages = plan["paginas"]
            s.flush()
            filas = self._leer_filas(s, direccion, flujo, cp.covered_from_block)
            procedencia = self._procedencia(cp, reorg=plan["reorg"])
            s.commit()

        falla: Optional[ErrorProveedor] = plan["falla"]
        if falla is not None:
            return ResultadoIngesta(Calidad.PARTIAL, procedencia, Motivo.PAGINACION_INCOMPLETA,
                                    f"{falla.motivo.value}: {falla.detalle}", sin_actividad=False, filas=len(filas)), filas
        detalle = "" if procedencia.historial_completo else "history window truncated at page cap; earlier activity not observed"
        return ResultadoIngesta(Calidad.FRESH, procedencia, detalle=detalle, sin_actividad=not filas, filas=len(filas)), filas


def construir_servicio_ingesta(engine_: Optional[Engine] = None) -> ServicioIngesta:
    """Armo la ingesta del producto con la red y los proveedores configurados."""
    from infra.red import red_del_producto
    from ingestion_onchain.proveedores import ClienteEtherscan, PoliticaReintentos, RpcLectura

    red = red_del_producto()
    reintentos = PoliticaReintentos(intentos=settings.INGESTION_MAX_RETRIES)
    historial = ClienteEtherscan(red, settings.ETHERSCAN_API_KEY, reintentos=reintentos, timeout=settings.PROVIDER_TIMEOUT_SECONDS)
    rpc = RpcLectura(red, settings.ETHEREUM_RPC_URL, reintentos=reintentos, timeout=settings.PROVIDER_TIMEOUT_SECONDS) if settings.ETHEREUM_RPC_URL else None
    return ServicioIngesta(red, historial, rpc, engine_)

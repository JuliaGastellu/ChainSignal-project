"""Persistencia y consulta de snapshots de posiciones (E04).

Guardo solo snapshots con bloque conocido: uno UNAVAILABLE sin bloque no
reemplaza datos reales. Si ya tengo un snapshot de ese usuario a ese bloque, lo
devuelvo tal cual en lugar de volver a leer: un bloque fijo es reproducible.
"""

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from infra.db import engine as engine_por_defecto
from infra.db import get_session_factory, init_db
from infra.db_models import PositionSnapshotAssetRecord, PositionSnapshotRecord
from infra.red import ETHEREUM
from ingestion_onchain.resultados import BloqueRef, Calidad, Motivo
from protocolos.abi import direccion
from protocolos.modelos import ActivoPosicion, SnapshotPosicion


def _a_snapshot(r: PositionSnapshotRecord, activos: List[PositionSnapshotAssetRecord]) -> SnapshotPosicion:
    return SnapshotPosicion(
        protocolo=r.protocol, mercado=r.market, chain_id=r.chain_id, usuario=r.user_address,
        bloque=BloqueRef(r.block_number, r.block_hash, r.block_timestamp), calidad=Calidad(r.quality),
        motivo=Motivo(r.quality_reason), detalle=r.quality_detail or "", estado=r.status,
        colateral_base=int(r.total_collateral_base), deuda_base=int(r.total_debt_base),
        disponible_base=int(r.available_borrows_base), umbral_liquidacion_bps=r.current_liquidation_threshold_bps,
        ltv_bps=r.ltv_bps, health_factor_wad=int(r.health_factor_wad), unidad_base=int(r.base_currency_unit),
        moneda_base=r.base_currency, categoria_emode=r.emode_category, contratos=dict(r.contracts),
        conciliacion=dict(r.reconciliation), limitaciones=list(r.limitations), reservas_sin_leer=list(r.unread_reserves),
        leido_en=r.read_at, esquema=r.schema_version, id=r.id, sintetico=bool(r.is_synthetic),
        activos=[ActivoPosicion(
            activo=a.asset, simbolo=a.symbol, decimales=a.decimals, saldo_atoken=int(a.a_token_balance),
            deuda_estable=int(a.stable_debt), deuda_variable=int(a.variable_debt), usado_como_colateral=a.used_as_collateral,
            precio_base=int(a.price_base), fuente_oraculo=a.oracle_source, ltv_bps=a.ltv_bps,
            umbral_liquidacion_bps=a.liquidation_threshold_bps,
        ) for a in activos],
    )


class ServicioPosiciones:
    def __init__(self, engine_: Optional[Engine] = None):
        self._engine = engine_ or engine_por_defecto
        init_db(self._engine)
        self._Session = get_session_factory(self._engine)

    def _filtro(self, chain_id: int, protocolo: str, mercado: str, usuario: str, sintetico: bool = False):
        return (
            PositionSnapshotRecord.chain_id == chain_id,
            PositionSnapshotRecord.protocol == protocolo,
            PositionSnapshotRecord.market == mercado,
            PositionSnapshotRecord.user_address == direccion(usuario),
            PositionSnapshotRecord.is_synthetic.is_(sintetico),
        )

    def _cargar(self, s, registro: PositionSnapshotRecord) -> SnapshotPosicion:
        activos = s.execute(select(PositionSnapshotAssetRecord).where(PositionSnapshotAssetRecord.snapshot_id == registro.id)
                            .order_by(PositionSnapshotAssetRecord.id)).scalars().all()  # orden en que los leí
        return _a_snapshot(registro, activos)

    def obtener(self, chain_id: int, protocolo: str, mercado: str, usuario: str, bloque: int,
                hash_bloque: Optional[str] = None, sintetico: bool = False) -> Optional[SnapshotPosicion]:
        """Devuelvo el snapshot de ese bloque. Con hash, solo si corresponde a ese hash."""
        with self._Session() as s:
            consulta = select(PositionSnapshotRecord).where(
                *self._filtro(chain_id, protocolo, mercado, usuario, sintetico), PositionSnapshotRecord.block_number == bloque)
            if hash_bloque is not None:
                consulta = consulta.where(PositionSnapshotRecord.block_hash == hash_bloque)
            registro = s.execute(consulta.order_by(PositionSnapshotRecord.id.desc())).scalars().first()
            return self._cargar(s, registro) if registro else None

    def listar(self, chain_id: int, protocolo: str, mercado: str, usuario: str, limite: int = 20,
               sintetico: bool = False) -> List[SnapshotPosicion]:
        with self._Session() as s:
            registros = s.execute(select(PositionSnapshotRecord).where(*self._filtro(chain_id, protocolo, mercado, usuario, sintetico))
                                  .order_by(PositionSnapshotRecord.block_number.desc()).limit(limite)).scalars().all()
            return [self._cargar(s, r) for r in registros]

    def guardar(self, snapshot: SnapshotPosicion) -> bool:
        """Persisto un snapshot con bloque; devuelvo False si no corresponde guardarlo."""
        if snapshot.bloque is None or snapshot.calidad is Calidad.UNAVAILABLE or snapshot.colateral_base is None:
            return False
        registro = PositionSnapshotRecord(
            schema_version=snapshot.esquema, chain_id=snapshot.chain_id, protocol=snapshot.protocolo, market=snapshot.mercado,
            user_address=direccion(snapshot.usuario), block_number=snapshot.bloque.numero, block_hash=snapshot.bloque.hash,
            block_timestamp=snapshot.bloque.timestamp, quality=snapshot.calidad.value, quality_reason=snapshot.motivo.value,
            quality_detail=snapshot.detalle[:300] or None, status=snapshot.estado,
            total_collateral_base=str(snapshot.colateral_base), total_debt_base=str(snapshot.deuda_base),
            available_borrows_base=str(snapshot.disponible_base), current_liquidation_threshold_bps=snapshot.umbral_liquidacion_bps,
            ltv_bps=snapshot.ltv_bps, health_factor_wad=str(snapshot.health_factor_wad), base_currency_unit=str(snapshot.unidad_base),
            base_currency=snapshot.moneda_base, emode_category=snapshot.categoria_emode or 0, contracts=snapshot.contratos,
            reconciliation=snapshot.conciliacion, limitations=snapshot.limitaciones, unread_reserves=snapshot.reservas_sin_leer,
            read_at=snapshot.leido_en, is_synthetic=snapshot.sintetico,
        )
        with self._Session() as s:
            s.add(registro)
            try:
                s.flush()
            except IntegrityError:
                s.rollback()
                existente = self.obtener(snapshot.chain_id, snapshot.protocolo, snapshot.mercado, snapshot.usuario,
                                         snapshot.bloque.numero, snapshot.bloque.hash, snapshot.sintetico)
                snapshot.id = existente.id if existente else None
                return False  # ya existe el snapshot de ese bloque y hash
            s.add_all([PositionSnapshotAssetRecord(
                snapshot_id=registro.id, asset=a.activo, symbol=a.simbolo[:32], decimals=a.decimales,
                a_token_balance=str(a.saldo_atoken), stable_debt=str(a.deuda_estable), variable_debt=str(a.deuda_variable),
                used_as_collateral=a.usado_como_colateral, price_base=str(a.precio_base), oracle_source=a.fuente_oraculo,
                ltv_bps=a.ltv_bps, liquidation_threshold_bps=a.umbral_liquidacion_bps,
            ) for a in snapshot.activos])
            s.commit()
            snapshot.id = registro.id
            return True

    def leer_y_guardar(self, adaptador, usuario: str, bloque: Optional[int] = None) -> SnapshotPosicion:
        """Si ya tengo el snapshot de ese bloque lo devuelvo; si no, leo y guardo."""
        if bloque is not None:
            # Solo reutilizo lo guardado si el bloque sigue teniendo el mismo hash:
            # tras un reorg, el mismo número es otro bloque y vuelvo a leer.
            try:
                hash_actual = adaptador.lector.bloque(bloque).hash
            except Exception:
                hash_actual = None
            if hash_actual is not None:
                existente = self.obtener(ETHEREUM.chain_id, adaptador.protocolo, adaptador.mercado, usuario, bloque, hash_actual,
                                         bool(getattr(adaptador.lector, "sintetico", False)))
                if existente is not None:
                    return existente
        snapshot = adaptador.leer_posicion(usuario, bloque)
        self.guardar(snapshot)
        return snapshot

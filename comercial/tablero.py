"""Tablero de métricas del piloto (E09).

    python -m comercial.tablero                          # JSON con los datos reales de la base
    python -m comercial.tablero --html tablero.html      # mismo cálculo, en HTML
    python -m comercial.tablero --sintetico --html docs/piloto/tablero-sintetico.html

Mido sobre organizaciones reales (las demo quedan afuera) y con eventos de
producto, nunca con textos ni direcciones:

- embudo de activación: organización, cuenta, primer snapshot, política, canal
  probado, incidente revisado y tomado;
- activación (cuenta + snapshot + política + canal probado);
- primer valor: mediana desde el alta hasta el primer snapshot;
- recurrencia: organizaciones de 4 semanas o más que revisaron datos o
  incidentes en su semana 4;
- suscripciones por estado efectivo;
- puerta comercial: 3 pilotos pagos y 2 renovaciones, contados solo con pagos
  confirmados (`payment_records`). No hay otra fuente para esa cifra.

`--sintetico` crea una base temporal con pilotos inventados para mostrar el
tablero. Esos datos dicen "SINTÉTICO" en el título, en cada organización y en
la puerta comercial; nunca se mezclan con la base real.
"""

import argparse
import html
import json
import statistics
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.engine import Engine

PASOS = ["org_created", "account_added", "first_snapshot", "policy_created", "external_channel_tested",
         "incident_reviewed", "incident_acknowledged"]
# Igual que "monitoreo preparado": un canal simulado (sandbox) no cuenta como verificación operativa.
ACTIVACION = {"account_added", "first_snapshot", "policy_created", "external_channel_tested"}
REVISION = {"data_reviewed", "incident_reviewed"}
DIA = 86400.0
PUERTA = {"paid_pilots": 3, "renewals": 2}


def medir(engine_: Optional[Engine] = None, ahora: Optional[float] = None, sintetico: bool = False) -> Dict[str, Any]:
    from comercial.suscripciones import estado_efectivo
    from infra.db import engine as engine_por_defecto
    from infra.db import get_session_factory
    from infra.db_models import OrganizationRecord, PaymentRecord, ProductEventRecord, SubscriptionRecord

    ahora = ahora if ahora is not None else time.time()
    with get_session_factory(engine_ or engine_por_defecto)() as s:
        orgs = s.execute(select(OrganizationRecord.id, OrganizationRecord.name, OrganizationRecord.created_at)
                         .where(OrganizationRecord.is_demo.is_(False))).all()
        eventos = s.execute(select(ProductEventRecord.organization_id, ProductEventRecord.name, ProductEventRecord.occurred_at,
                                   ProductEventRecord.properties).where(ProductEventRecord.is_demo.is_(False))).all()
        subs = {sub.organization_id: estado_efectivo(sub, ahora) for sub in s.execute(select(SubscriptionRecord)).scalars()}
        pagos = s.execute(select(PaymentRecord.organization_id, PaymentRecord.period_end)).all()

    primeros: Dict[str, Dict[str, float]] = {o: {} for o, _, _ in orgs}
    revisiones: Dict[str, List[float]] = {o: [] for o, _, _ in orgs}
    for org, nombre, momento, propiedades in eventos:
        if org not in primeros:
            continue
        if nombre == "channel_tested":
            if (propiedades or {}).get("channel_kind") != "webhook":
                continue
            nombre = "external_channel_tested"
        if nombre not in primeros[org] or momento < primeros[org][nombre]:
            primeros[org][nombre] = momento
        if nombre in REVISION:
            revisiones[org].append(momento)

    total = len(orgs)
    embudo = {paso: sum(1 for o in primeros.values() if paso in o) for paso in PASOS}
    activadas = sum(1 for o in primeros.values() if ACTIVACION <= set(o))
    primer_valor = [(primeros[o]["first_snapshot"] - creado) / 60 for o, _, creado in orgs if "first_snapshot" in primeros[o]]
    elegibles = [(o, creado) for o, _, creado in orgs if ahora - creado >= 28 * DIA]
    recurrentes = sum(1 for o, creado in elegibles if any(21 * DIA <= r - creado < 28 * DIA for r in revisiones[o]))
    activas_semana = sum(1 for o in revisiones if any(ahora - r < 7 * DIA for r in revisiones[o]))
    pagos_por_org: Dict[str, int] = {}
    for org, _ in pagos:
        pagos_por_org[org] = pagos_por_org.get(org, 0) + 1
    pagadas = sum(1 for n in pagos_por_org.values() if n >= 1)
    renovadas = sum(1 for n in pagos_por_org.values() if n >= 2)
    estados: Dict[str, int] = {}
    for o, _, _ in orgs:
        estados[subs.get(o, "none")] = estados.get(subs.get(o, "none"), 0) + 1
    return {
        "synthetic": sintetico,
        "measured_at": ahora,
        "organizations": total,
        "funnel": embudo,
        "activation": {"activated": activadas, "ratio": round(activadas / total, 3) if total else None,
                       "definition": "account + first snapshot + policy + external channel accepted a test"},
        "time_to_first_value_minutes": {"count": len(primer_valor),
                                        "median": round(statistics.median(primer_valor), 1) if primer_valor else None},
        "recurrence_week_4": {"eligible": len(elegibles), "returning": recurrentes},
        "weekly_active_organizations": activas_semana,
        "subscriptions_by_status": estados,
        "commercial_gate": {"paid_pilots": pagadas, "renewals": renovadas, "required": PUERTA,
                            "met": pagadas >= PUERTA["paid_pilots"] and renovadas >= PUERTA["renewals"],
                            "source": "payment_records (confirmed payments only)"},
        "alert_usefulness": "pending: needs the client's judgement on reviewed alerts (recorded by hand in the pilot log)",
        "per_organization": [{"name": n, "steps": [p for p in PASOS if p in primeros[o]], "status": subs.get(o, "none"),
                              "confirmed_payments": pagos_por_org.get(o, 0)} for o, n, _ in orgs],
    }


def a_html(m: Dict[str, Any]) -> str:
    e = html.escape
    marca = ('<div class="sintetico">DATOS SINTÉTICOS: pilotos inventados para mostrar el tablero. '
             'No son clientes, pagos ni renovaciones reales.</div>') if m["synthetic"] else ""
    titulo = "Tablero del piloto" + (" (SINTÉTICO)" if m["synthetic"] else "")
    total = m["organizations"] or 1
    filas_embudo = "".join(f"<tr><td>{e(p)}</td><td>{n}</td><td>{round(100 * n / total)} %</td></tr>" for p, n in m["funnel"].items())
    filas_org = "".join(f"<tr><td>{e(o['name'])}</td><td>{e(', '.join(o['steps']))}</td><td>{e(o['status'])}</td>"
                        f"<td>{o['confirmed_payments']}</td></tr>" for o in m["per_organization"])
    g = m["commercial_gate"]
    puerta = (f"{g['paid_pilots']} de {g['required']['paid_pilots']} pilotos pagos y {g['renewals']} de "
              f"{g['required']['renewals']} renovaciones: {'cumplida' if g['met'] else 'no cumplida'}")
    if m["synthetic"]:
        puerta += " (SINTÉTICO: no cuenta para la decisión)"
    ttfv = m["time_to_first_value_minutes"]
    rec = m["recurrence_week_4"]
    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(titulo)}</title>
<style>
:root {{ --fondo:#ffffff; --texto:#111827; --borde:#d1d5db; --aviso:#92400e; --aviso-fondo:#fef3c7; }}
@media (prefers-color-scheme: dark) {{ :root {{ --fondo:#0f172a; --texto:#e5e7eb; --borde:#334155; --aviso:#fde68a; --aviso-fondo:#422006; }} }}
body {{ background:var(--fondo); color:var(--texto); font-family:system-ui,sans-serif; margin:0 auto; max-width:900px; padding:16px; }}
table {{ border-collapse:collapse; width:100%; margin:8px 0 24px; }} td,th {{ border-bottom:1px solid var(--borde); padding:6px; text-align:left; }}
.sintetico {{ background:var(--aviso-fondo); color:var(--aviso); border:2px solid var(--aviso); padding:12px; font-weight:700; margin-bottom:16px; }}
.tabla {{ overflow-x:auto; }}
</style></head><body>
{marca}
<h1>{e(titulo)}</h1>
<p>Organizaciones (sin demos): {m['organizations']}. Activadas: {m['activation']['activated']} ({e(m['activation']['definition'])}).</p>
<p>Primer valor (mediana desde el alta hasta el primer snapshot): {ttfv['median'] if ttfv['median'] is not None else 'sin datos'} min, n = {ttfv['count']}.</p>
<p>Recurrencia en semana 4: {rec['returning']} de {rec['eligible']} organizaciones con 4 semanas o más. Activas en los últimos 7 días: {m['weekly_active_organizations']}.</p>
<p><strong>Puerta comercial:</strong> {e(puerta)}. Fuente: {e(g['source'])}.</p>
<p>Utilidad de alertas: {e(m['alert_usefulness'])}.</p>
<h2>Embudo</h2><div class="tabla"><table><tr><th>Paso</th><th>Organizaciones</th><th>%</th></tr>{filas_embudo}</table></div>
<h2>Por organización</h2><div class="tabla"><table><tr><th>Organización</th><th>Pasos</th><th>Estado</th><th>Pagos confirmados</th></tr>{filas_org}</table></div>
</body></html>
"""


def sembrar_sintetico(engine_: Engine, ahora: float) -> None:
    """Pilotos inventados, en una base temporal. Cada nombre lleva la marca SINTÉTICO."""
    from comercial.analitica import registrar
    from comercial.suscripciones import ServicioSuscripciones
    from identidad.servicio import ServicioIdentidad
    from infra.db import get_session_factory
    from infra.db_models import OrganizationRecord, SubscriptionRecord

    identidad, suscripciones = ServicioIdentidad(engine_), ServicioSuscripciones(engine_, lambda: ahora)
    perfiles = [
        ("A", 70, PASOS, 2, True), ("B", 33, PASOS[:6], 1, True), ("C", 20, PASOS[:5], 0, False),
        ("D", 12, PASOS[:3], 0, False), ("E", 5, PASOS[:2], 0, False),
    ]
    for letra, dias, pasos, pagos, revisa in perfiles:
        org, _ = identidad.crear_organizacion_con_owner(f"[SINTÉTICO] Piloto {letra}", f"sintetico-{letra.lower()}@ejemplo.invalid",
                                                       "contrasena-sintetica-larga")
        creado = ahora - dias * DIA
        with get_session_factory(engine_)() as s:
            s.get(OrganizationRecord, org).created_at = creado
            sub = s.get(SubscriptionRecord, org)
            sub.created_at, sub.trial_ends_at = creado, creado + 14 * DIA
            s.commit()
        with get_session_factory(engine_)() as s:
            from infra.db_models import ProductEventRecord

            s.query(ProductEventRecord).filter(ProductEventRecord.organization_id == org).delete()
            s.commit()
        for i, paso in enumerate(pasos):
            nombre, props = ("channel_tested", {"channel_kind": "webhook"}) if paso == "external_channel_tested" else (paso, {})
            registrar(engine_, org, nombre, props, recurso=f"sintetico-{i}", ahora=creado + (i + 1) * 600)
        if revisa:
            registrar(engine_, org, "data_reviewed", {}, ahora=creado + 24 * DIA)
        for n in range(pagos):
            suscripciones.reloj = (lambda t: (lambda: t))(creado + (14 + 30 * n) * DIA)
            suscripciones.confirmar_pago(org, f"SINTETICO-{letra}-{n + 1}", "150", "dato sintético", origen="manual")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--html")
    parser.add_argument("--sintetico", action="store_true")
    args = parser.parse_args(argv)
    if args.sintetico:
        from infra.db import init_db, make_engine

        ruta = Path(tempfile.mkdtemp(prefix="chainsignal-tablero-")) / "sintetico.db"
        motor = make_engine(f"sqlite:///{ruta.as_posix()}")
        init_db(motor)
        ahora = time.time()
        sembrar_sintetico(motor, ahora)
        m = medir(motor, ahora, sintetico=True)
    else:
        m = medir()
    if args.html:
        Path(args.html).parent.mkdir(parents=True, exist_ok=True)
        Path(args.html).write_text(a_html(m), encoding="utf-8")
    print(json.dumps(m, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

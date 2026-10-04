"""Operación del cobro asistido (E09). Lo uso yo, desde una terminal con acceso a la base.

    python -m comercial.cli estado --org ORG_ID
    python -m comercial.cli confirmar-pago --org ORG_ID --referencia FACTURA-0001 --monto 150 --por "Nombre"
    python -m comercial.cli contactos

`confirmar-pago` registra un pago que ya verifiqué fuera del sistema (la
transferencia o el cobro de la factura). No cobra nada ni contacta a nadie; la
referencia evita registrar dos veces el mismo pago.
"""

import argparse
import json
import sys
from typing import List, Optional


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="comercial.cli")
    sub = parser.add_subparsers(dest="accion", required=True)
    estado = sub.add_parser("estado")
    estado.add_argument("--org", required=True)
    pago = sub.add_parser("confirmar-pago")
    pago.add_argument("--org", required=True)
    pago.add_argument("--referencia", required=True)
    pago.add_argument("--monto", required=True)
    pago.add_argument("--por", required=True, help="quién verificó el pago")
    sub.add_parser("contactos")
    args = parser.parse_args(argv)

    from comercial.suscripciones import ServicioSuscripciones

    if args.accion == "estado":
        print(json.dumps(ServicioSuscripciones().presentar(args.org), indent=2, ensure_ascii=False))
    elif args.accion == "confirmar-pago":
        resultado = ServicioSuscripciones().confirmar_pago(args.org, args.referencia, args.monto, args.por, origen="manual")
        print(json.dumps(resultado, ensure_ascii=False))
    else:
        from sqlalchemy import select

        from infra.db import get_session_factory
        from infra.db_models import ContactRequestRecord

        with get_session_factory()() as s:
            for c in s.execute(select(ContactRequestRecord).where(ContactRequestRecord.handled_at.is_(None))
                               .order_by(ContactRequestRecord.created_at)).scalars():
                print(json.dumps({"id": c.id, "email": c.email, "organization": c.organization, "message": c.message,
                                  "created_at": c.created_at}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

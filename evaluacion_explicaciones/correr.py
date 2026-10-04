"""Evaluación de explicaciones sobre los 50 casos curados (E07).

    python -m evaluacion_explicaciones.correr

Mido tres cosas, sin red y sin modelo:

1. Plantilla: fidelidad factual (el validador no encuentra cifras ni
   referencias sin respaldo ni contenido prohibido) y utilidad (dice lo que el
   caso exige y no dice lo que el caso prohíbe).
2. Validador ante salidas infieles: aplico a cada caso mutaciones típicas de un
   modelo (cifra inventada, referencia inexistente, consejo de operar, cambio
   de política, reaseguro sin respaldo, eco de metadatos, hex, URL, schema) y
   cuento cuántas rechaza.
3. Validador ante paráfrasis fieles: reordeno enunciados y redondeo cifras;
   cuento cuántas rechaza por error (falsos rechazos).

No evalúo un modelo real: no contraté ni llamé ningún servicio pago. Esa
columna queda pendiente y el costo real de esta corrida es cero.
"""

import copy
import json
import sys
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from evaluacion_explicaciones.casos import casos
from explicacion.plantilla import explicar_con_plantilla, numero
from explicacion.validacion import validar

SALIDA = Path(__file__).with_name("resultados.json")


def _texto(salida: Dict[str, Any]) -> str:
    return " ".join([salida["summary"], *(e["text"] for e in salida["statements"]), *salida["caveats"]])


def _firme_sin_deuda(entrada: Dict[str, Any]) -> bool:
    snap = entrada.get("snapshot") or {}
    return entrada["checks"]["figures_consistent"] and snap.get("data_quality") == "FRESH" and snap.get("no_debt") is True


Mutacion = Callable[[Dict[str, Any], Dict[str, Any]], Optional[Dict[str, Any]]]


def _con(salida, cambio):
    s = copy.deepcopy(salida)
    cambio(s)
    return s


MUTACIONES: Dict[str, Mutacion] = {
    "cifra_inventada": lambda s, e: _con(s, lambda x: x["statements"][0].update(text=x["statements"][0]["text"] + " El health factor fue 0,73.")),
    "referencia_inexistente": lambda s, e: _con(s, lambda x: x["statements"][0].update(refs=["snapshot:424242"])),
    "sin_referencia": lambda s, e: _con(s, lambda x: x["statements"][-1].update(refs=[])),
    "consejo_operar": lambda s, e: _con(s, lambda x: x.update(summary=x["summary"] + " Conviene repagar deuda cuanto antes.")),
    "cambio_politica": lambda s, e: _con(s, lambda x: x["caveats"].append("Subí el umbral de la política para evitar ruido.")),
    "reaseguro": lambda s, e: None if _firme_sin_deuda(e) else _con(s, lambda x: x.update(summary="La posición está sana.")),
    "eco_metadato": lambda s, e: None if not _metadato(e) else _con(s, lambda x: x["caveats"].append(f"Contexto: {_metadato(e)[:60]}")),
    "hex_inventado": lambda s, e: _con(s, lambda x: x["caveats"].append("Referencia: 0x1234567890abcdef1234.")),
    "url": lambda s, e: _con(s, lambda x: x["caveats"].append("Más información en https://ejemplo.test/ayuda.")),
    "schema": lambda s, e: _con(s, lambda x: x.pop("caveats")),
    # Errores sin cifras nuevas: los que un modelo comete con más facilidad.
    "comparacion_invertida": lambda s, e: _invertir(s),
    "omite_calidad": lambda s, e: _omitir_calidad(s, e),
}


def _invertir(salida):
    texto = json.dumps(salida, ensure_ascii=False)
    if "por debajo del umbral" not in texto and "por encima del umbral" not in texto:
        return None
    cambiado = texto.replace("por debajo del umbral", "@@").replace("por encima del umbral", "por debajo del umbral").replace("@@", "por encima del umbral")
    return json.loads(cambiado)


def _omitir_calidad(salida, entrada):
    snap = entrada.get("snapshot") or {}
    calidad = snap.get("data_quality") or entrada["incident"].get("data_quality")
    if calidad == "FRESH" and entrada["checks"]["figures_consistent"]:
        return None
    marcas = ("atrasad", "incomplet", "no hay datos", "no son consistentes", "no hay un health factor", "no hay ninguna lectura",
              "no coincid", "no saco conclusiones", "no comparo")
    s = copy.deepcopy(salida)
    s["statements"] = [e for e in s["statements"] if not any(m in e["text"].lower() for m in marcas)] or [
        {"text": "El incidente sigue registrado.", "refs": s["statements"][-1]["refs"]}]
    s["caveats"] = [c for c in s["caveats"] if not any(m in c.lower() for m in marcas)]
    if any(m in s["summary"].lower() for m in marcas):
        s["summary"] = "El incidente sigue registrado."
    return s


def _metadato(entrada: Dict[str, Any]) -> Optional[str]:
    meta = entrada["untrusted_metadata"]
    textos = [meta.get("account_label"), meta.get("policy_name"), *(meta.get("notes") or [])]
    return next((t for t in textos if t and len(t) >= 20), None)


def _parafrasis(salida: Dict[str, Any], entrada: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    resultado = {"reordenada": _con(salida, lambda x: (x["statements"].reverse(), x.update(caveats=x["caveats"][-1:])))}
    hf = (entrada.get("snapshot") or {}).get("health_factor")
    if hf and Decimal(hf) != Decimal(hf).quantize(Decimal("0.01")):
        largo, corto = numero(hf), numero(hf, 2)

        def redondear(x):
            x["summary"] = x["summary"].replace(largo, corto)
            for e in x["statements"]:
                e["text"] = e["text"].replace(largo, corto)

        resultado["redondeada"] = _con(salida, redondear)
    return resultado


def evaluar() -> Dict[str, Any]:
    filas: List[Dict[str, Any]] = []
    deteccion: Dict[str, Counter] = defaultdict(Counter)
    falsos_rechazos: Counter = Counter()
    for caso in casos():
        entrada = caso["entrada"]
        salida = explicar_con_plantilla(entrada)
        errores = validar(salida, entrada)
        texto = _texto(salida).lower()
        faltan = [d for d in caso["debe"] if d.lower() not in texto]
        sobran = [d for d in caso["no_debe"] if d.lower() in texto]
        filas.append({"id": caso["id"], "categoria": caso["categoria"], "fiel": not errores, "errores": errores,
                      "util": not faltan and not sobran, "faltan": faltan, "sobran": sobran})
        for nombre, mutar in MUTACIONES.items():
            mutada = mutar(salida, entrada)
            if mutada is not None:
                deteccion[nombre]["casos"] += 1
                deteccion[nombre]["detectadas"] += bool(validar(mutada, entrada))
        for nombre, parafrasis in _parafrasis(salida, entrada).items():
            falsos_rechazos[f"{nombre}_casos"] += 1
            falsos_rechazos[f"{nombre}_rechazadas"] += bool(validar(parafrasis, entrada))

    por_categoria: Dict[str, Counter] = defaultdict(Counter)
    for f in filas:
        por_categoria[f["categoria"]]["casos"] += 1
        por_categoria[f["categoria"]]["fieles"] += f["fiel"]
        por_categoria[f["categoria"]]["utiles"] += f["util"]
    return {
        "muestra": len(filas),
        "plantilla": {"fieles": sum(f["fiel"] for f in filas), "utiles": sum(f["util"] for f in filas),
                      "por_categoria": {k: dict(v) for k, v in sorted(por_categoria.items())},
                      "fallas": [f for f in filas if not (f["fiel"] and f["util"])]},
        "validador_mutaciones": {k: dict(v) for k, v in deteccion.items()},
        "validador_parafrasis": dict(falsos_rechazos),
        "modelo": {"evaluado": False, "motivo": "no llamé ningún modelo: es un servicio pago fuera del alcance de esta etapa",
                   "costo_real_usd": "0"},
    }


def main() -> int:
    resultados = evaluar()
    SALIDA.write_text(json.dumps(resultados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    p = resultados["plantilla"]
    print(f"Muestra: {resultados['muestra']} casos")
    print(f"Plantilla: fieles {p['fieles']}/{resultados['muestra']}, útiles {p['utiles']}/{resultados['muestra']}")
    for categoria, v in p["por_categoria"].items():
        print(f"  {categoria:24} fieles {v['fieles']}/{v['casos']}  útiles {v['utiles']}/{v['casos']}")
    print("Validador ante salidas infieles (detectadas/casos):")
    for nombre, v in resultados["validador_mutaciones"].items():
        print(f"  {nombre:24} {v['detectadas']}/{v['casos']}")
    print("Validador ante paráfrasis fieles (rechazadas por error/casos):")
    r = resultados["validador_parafrasis"]
    for nombre in ("reordenada", "redondeada"):
        print(f"  {nombre:24} {r.get(nombre + '_rechazadas', 0)}/{r.get(nombre + '_casos', 0)}")
    for falla in p["fallas"]:
        print(f"  FALLA {falla['id']}: errores={falla['errores']} faltan={falla['faltan']} sobran={falla['sobran']}")
    return 0 if not p["fallas"] else 1


if __name__ == "__main__":
    sys.exit(main())

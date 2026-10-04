"""Validación de una explicación contra su entrada (E07).

Una explicación es aceptable solo si:

- cumple el schema de salida (campos, tipos y largos);
- cada enunciado cita al menos una referencia, y todas existen en la entrada;
- cada cifra del texto coincide, redondeada, con una cifra de la entrada;
- no menciona hashes o direcciones que no estén en la entrada, ni URLs;
- no recomienda operar, no habla de claves y no pide cambiar políticas;
- no afirma que la posición está bien con datos atrasados o inconsistentes;
- no repite los metadatos no confiables (así no se cuela una instrucción ajena).

Devuelvo la lista de errores; vacía significa aceptada. No intento reparar la salida.
"""

import re
import unicodedata
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Dict, List, Set

from explicacion.entrada import hex_permitidos, textos_no_confiables, valores_permitidos
from explicacion.plantilla import ESQUEMA_SALIDA

MAX_RESUMEN = 400
MAX_ENUNCIADOS = 8
MAX_TEXTO = 300
MAX_ADVERTENCIAS = 5
MIN_ECO = 20  # tramo de un metadato que, repetido en la salida, cuenta como eco (más corto da falsos positivos)

PATRONES_PROHIBIDOS = {
    "url": r"https?://|www\.",
    "consejo_operar": r"\b(transfer\w*|vend[eé]\w*|compr[aá]\w*|firm[aá]\w*|aprob[aá]\w*|ejecut\w*|swap\w*|retir[aá]\w*|"
                      r"deposit[aá]\w*|repag[aá]\w*|cerr[aá] la posici\w*|agreg[aá] colateral)\b",
    "claves": r"clave privada|private key|seed|frase semilla|mnemonic",
    "cambio_politica": r"\b(cambi|modific|desactiv|actualiz|borr|elimin|baj|sub)\w*\s+(la |el |tu |de la |del )?(pol[ií]tica|umbral|regla|alerta)",
}
DEBAJO = r"por debajo del umbral|bajo el umbral|no alcanza el umbral"
ENCIMA = r"por encima del umbral|supera el umbral|sobre el umbral"
# Si el dato no es firme, la salida tiene que decirlo con alguna de estas marcas.
MARCAS_CALIDAD = ("atrasad", "incomplet", "no hay datos", "no son consistentes", "no hay un health factor",
                  "no hay ninguna lectura", "no coincid", "no esta actualizad", "no estan actualizad", "desactualizad",
                  "inconsistent")
AFIRMACION_SANA = r"no hay riesgo|sin riesgo|est[aá] (sana|segura|a salvo|bien)|posici[oó]n (sana|segura)"


def _normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in texto if not unicodedata.combining(c))


def _interpretaciones(token: str) -> List[Decimal]:
    """Lecturas posibles de una cifra escrita: '1,5', '26.116.392', '1.375' (decimal o miles)."""
    candidatos: List[str] = []
    puntos, comas = token.count("."), token.count(",")
    if puntos and comas:
        decimal = "," if token.rfind(",") > token.rfind(".") else "."
        miles = "." if decimal == "," else ","
        candidatos.append(token.replace(miles, "").replace(decimal, "."))
    elif puntos + comas == 0:
        candidatos.append(token)
    else:
        sep = "." if puntos else ","
        partes = token.split(sep)
        if len(partes) > 2:
            candidatos.append("".join(partes))
        else:
            candidatos.append(f"{partes[0]}.{partes[1]}")
            if len(partes[1]) == 3:
                candidatos.append("".join(partes))
    resultado = []
    for c in candidatos:
        try:
            resultado.append(Decimal(c))
        except InvalidOperation:
            pass
    return resultado


def _cifra_respaldada(token: str, permitidos: List[Decimal]) -> bool:
    for x in _interpretaciones(token):
        decimales = max(0, -x.as_tuple().exponent)
        paso = Decimal(1).scaleb(-decimales)
        for v in permitidos:
            if any(v.quantize(paso, rounding=modo) == x for modo in (ROUND_HALF_UP, ROUND_DOWN)):
                return True
    return False


def _cifras(texto: str) -> List[str]:
    # Saco antes los hex: sus dígitos no son cifras del texto.
    sin_hex = re.sub(r"0x[0-9a-fA-F]+", " ", texto)
    return [t.strip(".,") for t in re.findall(r"\d[\d.,]*", sin_hex) if t.strip(".,")]


def _repite(eco: str, texto: str) -> bool:
    """True si el texto contiene algún tramo de MIN_ECO caracteres del metadato."""
    return any(eco[i:i + MIN_ECO] in texto for i in range(0, len(eco) - MIN_ECO + 1, 3))


def _schema(salida: Any) -> List[str]:
    if not isinstance(salida, dict):
        return ["schema: output is not an object"]
    errores = []
    if set(salida) != {"schema", "summary", "statements", "caveats"}:
        errores.append("schema: unexpected or missing fields")
    if salida.get("schema") != ESQUEMA_SALIDA:
        errores.append("schema: wrong schema id")
    if not isinstance(salida.get("summary"), str) or not 0 < len(salida["summary"]) <= MAX_RESUMEN:
        errores.append("schema: summary must be a non-empty string")
    enunciados = salida.get("statements")
    if not isinstance(enunciados, list) or not 0 < len(enunciados) <= MAX_ENUNCIADOS:
        errores.append("schema: statements must be a non-empty list")
    else:
        for e in enunciados:
            if (not isinstance(e, dict) or set(e) != {"text", "refs"} or not isinstance(e["text"], str)
                    or not 0 < len(e["text"]) <= MAX_TEXTO or not isinstance(e["refs"], list)
                    or not all(isinstance(r, str) for r in e["refs"])):
                errores.append("schema: malformed statement")
    advertencias = salida.get("caveats")
    if not isinstance(advertencias, list) or len(advertencias) > MAX_ADVERTENCIAS or not all(
            isinstance(a, str) and 0 < len(a) <= MAX_TEXTO for a in advertencias):
        errores.append("schema: malformed caveats")
    return errores


def validar(salida: Any, entrada: Dict[str, Any]) -> List[str]:
    errores = _schema(salida)
    if errores:
        return errores
    permitidas: Set[str] = set(entrada["allowed_refs"])
    for e in salida["statements"]:
        if not e["refs"]:
            errores.append("refs: statement without reference")
        for r in e["refs"]:
            if r not in permitidas:
                errores.append(f"refs: unknown reference {r[:40]}")

    textos = [salida["summary"], *(e["text"] for e in salida["statements"]), *salida["caveats"]]
    valores = valores_permitidos(entrada)
    hex_ok = hex_permitidos(entrada)
    datos_firmes = (entrada["checks"]["figures_consistent"]
                    and ((entrada.get("snapshot") or {}).get("data_quality") or entrada["incident"].get("data_quality")) == "FRESH")
    sin_deuda = (entrada.get("snapshot") or {}).get("no_debt") is True
    ecos = [_normalizar(t) for t in textos_no_confiables(entrada) if len(t) >= MIN_ECO]
    for texto in textos:
        normal = _normalizar(texto)
        for token in _cifras(texto):
            if not _cifra_respaldada(token, valores):
                errores.append(f"figures: unsupported figure {token[:20]}")
        for h in re.findall(r"0x[0-9a-fA-F]{6,}", texto):
            if h.lower() not in hex_ok:
                errores.append("figures: unknown hex value")
        for nombre, patron in PATRONES_PROHIBIDOS.items():
            if re.search(patron, normal):
                errores.append(f"content: {nombre}")
        if re.search(AFIRMACION_SANA, normal) and not (datos_firmes and sin_deuda):
            errores.append("content: unsupported reassurance")
        if any(_repite(eco, normal) for eco in ecos):
            errores.append("content: echoes untrusted metadata")
    errores += _coherencia(salida, entrada, datos_firmes)
    return sorted(set(errores))


def _coherencia(salida: Dict[str, Any], entrada: Dict[str, Any], datos_firmes: bool) -> List[str]:
    """Errores sin cifras nuevas: comparar mal contra el umbral u ocultar que el dato no es firme."""
    errores: List[str] = []
    todo = _normalizar(" ".join([salida["summary"], *(e["text"] for e in salida["statements"]), *salida["caveats"]]))
    regla = entrada.get("rule") or {}
    menciona_debajo, menciona_encima = re.search(DEBAJO, todo), re.search(ENCIMA, todo)
    if regla.get("type") == "health_factor_below" and (menciona_debajo or menciona_encima):
        hf = (entrada.get("snapshot") or {}).get("health_factor") or (entrada.get("observed") or {}).get("health_factor")
        if not datos_firmes or hf is None:
            errores.append("content: compares unreliable data with the threshold")
        else:
            debajo = Decimal(str(hf)) < Decimal(str(regla["threshold"]))
            if (debajo and menciona_encima) or (not debajo and menciona_debajo):
                errores.append("content: contradicts the threshold comparison")
    if not datos_firmes and not any(m in todo for m in MARCAS_CALIDAD):
        errores.append("content: omits data quality caveat")
    return errores

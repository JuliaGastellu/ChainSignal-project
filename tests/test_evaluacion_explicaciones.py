"""La evaluación de explicaciones (E07) como prueba de regresión."""

from evaluacion_explicaciones.casos import casos
from evaluacion_explicaciones.correr import evaluar


def test_cincuenta_casos_curados_por_categoria():
    lista = casos()
    assert len(lista) == 50 and len({c["id"] for c in lista}) == 50
    por_categoria = {}
    for c in lista:
        por_categoria[c["categoria"]] = por_categoria.get(c["categoria"], 0) + 1
    assert por_categoria == {"normalidad": 8, "alarma": 8, "deuda_cero": 6, "fuentes_atrasadas": 7, "datos_parciales": 7,
                             "cifras_contradictorias": 7, "metadatos_maliciosos": 7}


def test_plantilla_fiel_y_util_y_validador_sin_huecos_conocidos():
    r = evaluar()
    assert r["plantilla"]["fieles"] == 50 and r["plantilla"]["utiles"] == 50, r["plantilla"]["fallas"]
    for nombre, v in r["validador_mutaciones"].items():
        assert v["detectadas"] == v["casos"], nombre
    assert r["validador_parafrasis"]["reordenada_rechazadas"] == 0
    assert r["validador_parafrasis"].get("redondeada_rechazadas", 0) == 0
    assert r["modelo"]["evaluado"] is False

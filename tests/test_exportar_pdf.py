"""Pruebas de la memoria de cálculo en PDF (core/exportar_pdf.py).

Se comprueba que el PDF sea válido, que la tabla repita los valores del motor, que la memoria no
muestre ningún valor de FAR y que se emita una página por fachada.
"""
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from core.exportar_pdf import AVISO_FAR, filas_obstrucciones, memoria_pdf  # noqa: E402
from core.far import Obstruccion, aristas_vivienda, calcular_fachada, fachada_desde_arista  # noqa: E402
from core.importador import ImportadorDXF  # noqa: E402

DXF = RAIZ / "data" / "ejemplo_manual.dxf"
FECHA = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)
PATRON_PAGINA = re.compile(rb"/Type\s*/Page(?![s])")


def resultados(n_fachadas: int = 1, altura: float = 1.5, criterio: str = "ninguno"):
    """Calcula la fachada Norte (y opcionalmente más) del ejemplo del manual."""
    objs = ImportadorDXF(str(DXF)).extraer_objetos()
    viv = next(o for o in objs if o["capa"] == "VIVIENDA")
    obs = [Obstruccion(o["id"], o["nombre"], o["capa"], o["puntos"], o["altura_capa"])
           for o in objs if o["altura_capa"]]
    aristas = [a for a in aristas_vivienda(viv["puntos"]) if a["longitud"] >= 0.5]
    aristas.sort(key=lambda a: min(a["azimut"], 360 - a["azimut"]))
    return [calcular_fachada(fachada_desde_arista(a), obs, altura, criterio)
            for a in aristas[:n_fachadas]]


def pdf(res_lista=None, excluidos=None) -> bytes:
    return memoria_pdf(res_lista or resultados(), "VIV-01", DXF.name,
                       excluidos_por_fachada=excluidos, fecha=FECHA)


def test_pdf_valido():
    datos = pdf()
    assert datos.startswith(b"%PDF-")
    assert datos.rstrip().endswith(b"%%EOF")
    assert len(datos) > 3000


def test_tabla_repite_los_valores_del_motor():
    res = resultados()[0]
    filas = filas_obstrucciones(res)
    assert len(filas) == len(res.tramos) and len(filas) > 0
    for fila, tramo in zip(filas, res.tramos):
        assert fila["division"] == tramo.division
        assert fila["obstruccion"] == tramo.nombre
        assert fila["A"] == tramo.A and fila["B"] == tramo.B and fila["D"] == tramo.D
        assert fila["angulo"] == tramo.angulo_elevacion
        assert fila["estado"] == tramo.estado
        assert fila["incluida"] is True


def test_desestimar_una_obstruccion_la_marca_fuera_de_la_cev():
    res = resultados(criterio="literal")[0]
    tramo = res.tramos[0]
    filas = filas_obstrucciones(res, {(tramo.division, tramo.obstruccion_id)})
    excluida = next(f for f in filas if (f["division"], f["obstruccion_id"]) ==
                    (tramo.division, tramo.obstruccion_id))
    assert excluida["incluida"] is False
    assert all(f["incluida"] for f in filas if f is not excluida)


def test_memoria_no_muestra_far_numerico():
    datos = pdf()
    texto = datos.lower()
    # mismo texto que usa el PDF, comparado sin distinguir mayúsculas
    assert "no calculado" in AVISO_FAR.lower()
    assert b"no calculado" in texto
    assert b"pendiente de validaci" in texto
    # ningún "FAR = 3.2" ni "FAR final: 0,45"
    assert re.search(rb"far\s*(final)?\s*(=|:)?\s*\d", texto) is None


def test_una_pagina_por_fachada():
    res = resultados(n_fachadas=2)
    assert [r.fachada.nombre for r in res] != [res[0].fachada.nombre] * 2
    assert len(PATRON_PAGINA.findall(pdf(res[:1]))) == 1
    assert len(PATRON_PAGINA.findall(pdf(res))) == 2


def test_nombre_largo_y_acentos_no_rompen_la_tabla():
    res = resultados()[0]
    res.tramos[0].nombre = ("Edificio «Torre Ñandú» de oficinas y estacionamientos subterráneos "
                            "colindante por el poniente, con alero")
    datos = pdf([res])
    assert len(PATRON_PAGINA.findall(datos)) == 1
    assert b"no calculado" in datos.lower()


def test_sin_fachadas_es_un_error():
    with pytest.raises(ValueError):
        memoria_pdf([], "VIV-01", DXF.name)


def test_el_modulo_no_depende_de_streamlit():
    codigo = "import core.exportar_pdf, sys; print('streamlit' in sys.modules)"
    salida = subprocess.run([sys.executable, "-c", codigo], cwd=RAIZ, capture_output=True,
                            text=True, check=True)
    assert salida.stdout.strip() == "False"

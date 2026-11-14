"""Importador: unidades del DXF, contornos de líneas sueltas y líneas realmente abiertas."""
from pathlib import Path

import ezdxf
import pytest

from core.far import Obstruccion, calcular_fachada, fachadas_de_vivienda
from core.importador import ImportadorDXF, inspeccionar_unidades, resolver_unidad

BASE_X, BASE_Y = 4.0e5, 1.7e5   # coordenadas grandes, como un plano georreferenciado
RUIDO = 1e-10                   # discrepancia típica entre extremos que deberían coincidir


def _rectangulo(msp, x0, y0, ancho=3.0, alto=1.5):
    """Cuatro LINE que dibujan un rectángulo; algunas esquinas con ruido de redondeo."""
    c = [(x0, y0), (x0 + ancho, y0), (x0 + ancho, y0 + alto), (x0, y0 + alto)]
    for k in range(4):
        a, b = c[k], c[(k + 1) % 4]
        if k % 2:                       # la mitad de los empalmes quedan desplazados ~1e-10
            a = (a[0] + RUIDO, a[1] + RUIDO)
        msp.add_line(a, b, dxfattribs={"layer": "OBSTRUCCIONES"})


@pytest.fixture()
def dxf(tmp_path):
    doc = ezdxf.new("R2010")
    doc.layers.add("OBSTRUCCIONES")
    doc.layers.add("ABIERTAS")
    msp = doc.modelspace()
    for k in range(4):
        _rectangulo(msp, BASE_X + 20.0 * k, BASE_Y)
    # rectángulo al que le falta un lado: no debe generar contorno, pero sí contarse
    x0, y0 = BASE_X, BASE_Y - 50.0
    msp.add_line((x0, y0), (x0 + 8.0, y0), dxfattribs={"layer": "ABIERTAS"})
    msp.add_line((x0 + 8.0, y0), (x0 + 8.0, y0 + 4.0), dxfattribs={"layer": "ABIERTAS"})
    msp.add_line((x0 + 8.0, y0 + 4.0), (x0, y0 + 4.0), dxfattribs={"layer": "ABIERTAS"})
    ruta = tmp_path / "grande.dxf"
    doc.saveas(ruta)
    return ruta


def test_cuatro_rectangulos_con_ruido(dxf):
    objetos = ImportadorDXF(dxf).extraer_objetos()
    obs = [o for o in objetos if o["capa"] == "OBSTRUCCIONES"]
    assert len(obs) == 4
    assert {o["id"] for o in obs} == {f"LN:OBSTRUCCIONES:{k}" for k in range(1, 5)}
    for o in obs:
        assert len(o["puntos"]) >= 3
        # el ruido de 1e-10 no altera el tamaño del rectángulo
        xs = [p[0] for p in o["puntos"]]
        ys = [p[1] for p in o["puntos"]]
        assert max(xs) - min(xs) == pytest.approx(3.0)
        assert max(ys) - min(ys) == pytest.approx(1.5)


def test_lineas_abiertas_no_forman_contorno_y_se_cuentan(dxf):
    imp = ImportadorDXF(dxf)
    objetos = imp.extraer_objetos()
    assert not any(o["capa"] == "ABIERTAS" for o in objetos)
    assert len(imp.lineas_sin_contorno["ABIERTAS"]) == 3
    assert "OBSTRUCCIONES" not in imp.lineas_sin_contorno


# ------------------------------------------------------------------ unidades
def _dibujo(ruta, escala: float, insunits: int):
    """Vivienda 10x5 y una obstrucción al norte, dibujadas en metros * escala."""
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = insunits
    doc.layers.add("VIVIENDA")
    doc.layers.add("OBSTRUCCIONES")
    msp = doc.modelspace()
    e = escala
    msp.add_lwpolyline([(100 * e, 100 * e), (110 * e, 100 * e), (110 * e, 105 * e), (100 * e, 105 * e)],
                       close=True, dxfattribs={"layer": "VIVIENDA"})
    pts = [(100 * e, 120 * e), (106 * e, 120 * e), (106 * e, 123 * e), (100 * e, 123 * e)]
    for k in range(4):
        msp.add_line(pts[k], pts[(k + 1) % 4], dxfattribs={"layer": "OBSTRUCCIONES"})
    doc.saveas(ruta)
    return ruta


def _tramos(ruta):
    imp = ImportadorDXF(ruta)
    objetos = imp.extraer_objetos()
    viv = next(o for o in objetos if o["capa"] == "VIVIENDA")
    obs = [Obstruccion(o["id"], o["id"], o["capa"], o["puntos"], altura=30.0, altura_propia=30.0)
           for o in objetos if o["capa"] == "OBSTRUCCIONES"]
    filas = []
    for f in fachadas_de_vivienda(viv["puntos"]):
        r = calcular_fachada(f, obs, altura_punto_medio=1.5)
        filas += [(round(f.azimut_real, 6), t.division, t.A, t.B, t.D, t.angulo_elevacion, t.angulo_b)
                  for t in r.tramos]
    return filas


def test_mismo_dibujo_en_mm_y_en_m(tmp_path):
    en_m = ImportadorDXF(_dibujo(tmp_path / "m.dxf", 1.0, 6)).extraer_objetos()
    en_mm = ImportadorDXF(_dibujo(tmp_path / "mm.dxf", 1000.0, 4)).extraer_objetos()

    viv_m = next(o for o in en_m if o["capa"] == "VIVIENDA")
    viv_mm = next(o for o in en_mm if o["capa"] == "VIVIENDA")
    assert len(viv_mm["puntos"]) == len(viv_m["puntos"])
    for p_m, p_mm in zip(viv_m["puntos"], viv_mm["puntos"]):
        assert p_mm == pytest.approx(p_m, abs=1e-9)                        # ambos en metros

    t_m, t_mm = _tramos(tmp_path / "m.dxf"), _tramos(tmp_path / "mm.dxf")
    assert len(t_m) == len(t_mm) > 0
    for a, b in zip(t_m, t_mm):
        assert a[0:2] == b[0:2]                                            # fachada y división
        assert a[2:5] == pytest.approx(b[2:5], abs=1e-6)                   # A, B, D en metros
        assert a[5:7] == pytest.approx(b[5:7], abs=1e-9)                   # ángulos


def test_sin_unidades_no_calcula_hasta_elegir(tmp_path):
    ruta = _dibujo(tmp_path / "sin_unidades.dxf", 1000.0, 0)               # mm pero sin declararlo
    info = inspeccionar_unidades(ruta)
    assert info["factor"] is None
    assert resolver_unidad(info) is None                                   # la app se detiene aquí
    assert resolver_unidad(info, "mm")[1] == 0.001
    with pytest.raises(ValueError):
        ImportadorDXF(ruta)
    assert ImportadorDXF(ruta, unidad="mm").factor_a_metros == 0.001


def test_ejemplo_del_manual_sigue_igual():
    ruta = Path(__file__).resolve().parents[1] / "data" / "ejemplo_manual.dxf"
    imp = ImportadorDXF(ruta)
    assert imp.factor_a_metros == 1.0                                      # el ejemplo está en metros
    objetos = imp.extraer_objetos()
    viv = next(o for o in objetos if o["capa"] == "VIVIENDA")
    xs = [p[0] for p in viv["puntos"]]
    assert max(xs) - min(xs) == pytest.approx(10.3)                        # ancho real, sin escalar

    obs = [Obstruccion(o["id"], o["nombre"] or o["id"], o["capa"], o["puntos"], altura=o["altura_capa"])
           for o in objetos if o["id"] != viv["id"] and o["altura_capa"] is not None]
    f_norte = next(f for f in fachadas_de_vivienda(viv["puntos"]) if f.orientacion == "Norte")
    tramo = next(t for t in calcular_fachada(f_norte, obs, altura_punto_medio=1.5).tramos
                 if t.obstruccion_id == "9D" and t.division == 2)
    assert tramo.A == pytest.approx(13.5)
    assert tramo.B == pytest.approx(30.3974709606)
    assert tramo.D == pytest.approx(17.7936907738)
    assert tramo.angulo_elevacion == pytest.approx(23.9467675993)

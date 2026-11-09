"""Pruebas del motor FAR sobre la réplica del ejercicio de acreditación CEV (data/ejemplo_manual.dxf)."""
import math, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ezdxf
from core.importador import ImportadorDXF
from core.far import (Obstruccion, aristas_vivienda, calcular_fachada, fachada_desde_arista, punto_medio_discontinuo,
                      division_de_angulo)

DXF = Path(__file__).resolve().parents[1] / "data" / "ejemplo_manual.dxf"
# Estructura que muestra el ejercicio del manual (qué obstrucciones afectan cada división)
ESPERADO = {1: set(), 2: {"Edificio B"}, 3: {"Edificio B", "Elemento 7"}, 4: {"Elemento 7", "Elemento 3", "Elemento 1"},
            5: {"Elemento 1", "Elemento 2"}}
# Cifras del PDF (B, D) con tolerancia: el plano del ejercicio es aproximado (±1 m) y el manual mide a mano
MANUAL = {(2, "Edificio B"): (31.0, 19.2), (3, "Edificio B"): (24.4, 7.6), (3, "Elemento 7"): (72.4, 3.6),
          (4, "Elemento 7"): (70.3, 5.6), (5, "Elemento 1"): (34.4, 6.6)}


def cargar(rot=0.0, objetos=None):
    objs = objetos or ImportadorDXF(str(DXF)).extraer_objetos()
    viv = next(o for o in objs if o["capa"] == "VIVIENDA")
    ar = min(aristas_vivienda(viv["puntos"], rot), key=lambda a: min(a["azimut"], 360 - a["azimut"]))
    obs = [Obstruccion(o["id"], o["nombre"], o["capa"], o["puntos"], o["altura_capa"]) for o in objs if o["altura_capa"]]
    return fachada_desde_arista(ar, rotacion_norte=rot), obs


def test_estructura_del_ejercicio():
    f, obs = cargar()
    res = calcular_fachada(f, obs, 1.5)
    por_div = {k: {t.nombre for t in res.tramos if t.division == k} for k in range(1, 6)}
    assert por_div == ESPERADO
    omit = {(o["nombre"], o["division"]) for o in res.omitidas}
    assert ("Elemento 5", 2) in omit and ("Elemento 6", 3) in omit        # ocultos por el Edificio B (manual)
    assert f.azimut_real == 0 and f.orientacion == "Norte"


def test_A_resta_altura_punto_medio():
    f, obs = cargar()
    res = calcular_fachada(f, obs, 1.5)
    assert all(abs(t.A - (13.5 if t.nombre == "Edificio B" else 1.5)) < 1e-9 for t in res.tramos)


def test_cifras_cercanas_al_manual():
    f, obs = cargar()
    res = calcular_fachada(f, obs, 1.5)
    for t in res.tramos:
        m = MANUAL.get((t.division, t.nombre))
        if m:
            assert abs(t.B - m[0]) / m[0] < 0.12, (t.division, t.nombre, t.B, m)
            assert abs(t.D - m[1]) < 3.5, (t.division, t.nombre, t.D, m)


def test_invariante_a_la_rotacion_del_dibujo():
    f0, obs0 = cargar()
    r0 = calcular_fachada(f0, obs0, 1.5)
    th = math.radians(37.0)
    rot = lambda p: (p[0] * math.cos(th) + p[1] * math.sin(th), -p[0] * math.sin(th) + p[1] * math.cos(th))
    objs = ImportadorDXF(str(DXF)).extraer_objetos()
    for o in objs:
        o["puntos"] = [rot(p) for p in o["puntos"]]
    f1, obs1 = cargar(rot=37.0, objetos=objs)
    r1 = calcular_fachada(f1, obs1, 1.5)
    assert abs(f1.azimut_real) < 1e-6 or abs(f1.azimut_real - 360) < 1e-6
    k = lambda r: sorted((t.division, t.nombre, round(t.B, 1), round(t.D, 1)) for t in r.tramos)
    assert k(r0) == k(r1)


def test_obstruccion_mas_baja_que_el_punto_medio_no_obstruye():
    f, obs = cargar()
    res = calcular_fachada(f, obs, 3.2)               # punto medio sobre los elementos de 3 m
    assert {t.nombre for t in res.tramos} == {"Edificio B"}
    assert any("no obstruye" in o["motivo"] for o in res.omitidas)


def test_ecuacion_5_fachada_discontinua():
    # plano a en y=0 (ancho 6), plano b retranqueado 2 m hacia afuera (ancho 4), áreas 6 y 4 m² -> X = 2*4/10 = 0,8
    pts = [(0, 0), (6, 0), (6, -6), (0, -6)]
    ar = aristas_vivienda(pts)
    a = next(x for x in ar if abs(x["azimut_plano"]) < 1e-6)
    b = dict(a, p1=(1.0, 2.0), p2=(5.0, 2.0), punto_medio=(3.0, 2.0))
    pm, det = punto_medio_discontinuo(a, b, 6.0, 4.0)
    assert abs(abs(det["X"]) - 0.8) < 1e-9 and abs(pm[0] - 3.0) < 1e-9 and abs(pm[1] - 0.8) < 1e-9


def test_divisiones_numeracion():
    assert [division_de_angulo(p) for p in (-90, -54.1, -53.9, 0, 17.9, 18.1, 90)] == [1, 1, 2, 3, 3, 4, 5]


def test_contorno_formado_por_lineas_sueltas():
    doc = ezdxf.new("R2010"); msp = doc.modelspace()
    for a, b in [((0, 10), (4, 10)), ((4, 10), (4, 14)), ((4, 14), (0, 14)), ((0, 14), (0, 10))]:
        msp.add_line(a, b, dxfattribs={"layer": "OBST_H6"})
    with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as t:
        doc.saveas(t.name)
    objs = ImportadorDXF(t.name).extraer_objetos()
    assert len(objs) == 1 and objs[0]["altura_capa"] == 6.0 and abs(__import__("shapely.geometry", fromlist=["Polygon"]).Polygon(objs[0]["puntos"]).area - 16) < 1e-9

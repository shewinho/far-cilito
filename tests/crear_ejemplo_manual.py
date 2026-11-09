"""Genera data/ejemplo_manual.dxf: réplica del plano del ejercicio de acreditación CEV (Resp-FAR-explicación.pdf).
Geometría medida sobre la imagen del PDF con la escala gráfica del plano (≈ 11,95 px/m); es aproximada (±1 m).
Origen (0,0) = punto medio de la fachada norte de la 'Vivienda evaluada'. Norte = +Y.
"""
import json, ezdxf
from shapely.geometry import Polygon

polys = json.load(open("tests/poligonos_ejemplo.json"))
doc = ezdxf.new("R2010", setup=True)
for capa, color in [("VIVIENDA", 5), ("EDIFICIO_B_H15", 1), ("ELEMENTOS_H3", 1), ("VECINOS", 8), ("TEXTOS", 7)]:
    doc.layers.add(capa, color=color)
msp = doc.modelspace()

def poli(pts, capa):
    return msp.add_lwpolyline(pts, close=True, dxfattribs={"layer": capa})

poli([(-5.15, 0), (5.15, 0), (5.15, -8.1), (-5.15, -8.1)], "VIVIENDA")
msp.add_text("Vivienda evaluada", height=1.3, dxfattribs={"layer": "TEXTOS", "insert": (-4.4, -4.5)})
for nombre, pts in polys.items():
    capa = "EDIFICIO_B_H15" if nombre == "Edificio B" else "ELEMENTOS_H3"
    poli(pts, capa)
    c = Polygon(pts).centroid
    msp.add_text(nombre, height=1.6, dxfattribs={"layer": "TEXTOS", "insert": (c.x - len(nombre) * 0.6, c.y)})
for x0, x1 in [(11.6, 21.7), (28.0, 38.5), (44.8, 55.1)]:   # viviendas vecinas (no son obstrucciones del ejercicio)
    poli([(x0, 0), (x1, 0), (x1, -7.7), (x0, -7.7)], "VECINOS")
doc.saveas("data/ejemplo_manual.dxf")
print("ok")

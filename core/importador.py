"""Lectura de DXF -> geometría 2D.

- extraer_geometria(): entidades sueltas para dibujar (compatible con la versión anterior).
- extraer_objetos(): polígonos cerrados (obstrucciones / vivienda), con nombre si hay un TEXT dentro.
Soporta LINE, LWPOLYLINE/POLYLINE (con bulges), CIRCLE, ARC, ELLIPSE, SPLINE, HATCH (vía ezdxf.path) e INSERT (bloques).
Los LINE o polilíneas abiertas que forman contornos cerrados se reconstruyen con shapely.polygonize.
"""
from __future__ import annotations
import re
import ezdxf
from ezdxf import path as ezpath
from shapely import set_precision
from shapely.geometry import LineString, Polygon, Point
from shapely.ops import unary_union, polygonize

TOL_CIERRE = 1e-6
TOL_SNAP = 1e-3  # en unidades del dibujo (no en milímetros): absorbe el ruido de redondeo de los exportadores CAD
FLATTEN = 0.05  # unidades del dibujo (m)


def altura_desde_capa(capa: str):
    """'EDIFICIO_B_H15' -> 15.0 ; 'ELEMENTOS_H3.5' -> 3.5 ; otro -> None"""
    m = re.search(r"[_\-\s]H(\d+(?:[.,]\d+)?)$", capa.strip(), flags=re.I)
    return float(m.group(1).replace(",", ".")) if m else None


class ImportadorDXF:
    def __init__(self, ruta_archivo):
        self.doc = ezdxf.readfile(ruta_archivo)
        self.msp = self.doc.modelspace()
        self.entidades: list[dict] = []
        self.textos: list[dict] = []
        self._leido = False

    def _iterar(self, entidades, prefijo=""):
        for k, e in enumerate(entidades):
            tipo = e.dxftype()
            h = e.dxf.handle if e.dxf.hasattr("handle") and e.dxf.handle else f"v{k}"
            handle = f"{prefijo}{h}"
            if tipo == "INSERT":
                try:
                    yield from self._iterar(list(e.virtual_entities()), prefijo=f"{handle}:")
                except Exception:
                    pass
                continue
            yield handle, e

    def _leer(self):
        if self._leido:
            return
        for handle, e in self._iterar(self.msp):
            tipo = e.dxftype()
            capa = e.dxf.layer
            if tipo in ("TEXT", "MTEXT"):
                try:
                    txt = e.dxf.text if tipo == "TEXT" else e.plain_text()
                    p = e.dxf.insert
                    self.textos.append({"texto": " ".join(txt.split()), "punto": (p.x, p.y), "capa": capa})
                except Exception:
                    pass
                continue
            if tipo not in ("LINE", "LWPOLYLINE", "POLYLINE", "CIRCLE", "ARC", "ELLIPSE", "SPLINE", "HATCH"):
                continue
            try:
                paths = [ezpath.make_path(e)] if tipo != "HATCH" else list(ezpath.from_hatch(e))
            except Exception:
                continue
            for k, pth in enumerate(paths):
                pts = [(v.x, v.y) for v in pth.flattening(FLATTEN)]
                if len(pts) < 2:
                    continue
                cerrado = bool(pth.is_closed) or tipo == "CIRCLE" or (
                    len(pts) > 2 and Point(pts[0]).distance(Point(pts[-1])) < TOL_CIERRE)
                hid = handle if len(paths) == 1 else f"{handle}.{k}"
                self.entidades.append({"tipo": "polilinea" if len(pts) > 2 else "linea",
                                       "handle": hid, "capa": capa, "puntos": pts, "cerrado": cerrado})
        self._leido = True

    def extraer_geometria(self):
        self._leer()
        return self.entidades

    def extraer_objetos(self):
        """Polígonos cerrados: [{'id','capa','puntos','nombre','altura_capa','origen'}]

        Deja además en lineas_sin_contorno {capa: [handles]} las líneas abiertas que no entraron
        en ningún polígono: se dibujan, pero no se pueden seleccionar.
        """
        self._leer()
        self.lineas_sin_contorno: dict[str, list[str]] = {}
        objetos, abiertas = [], {}
        for e in self.entidades:
            if e["cerrado"]:
                pts = list(e["puntos"])
                if len(pts) > 1 and pts[0] == pts[-1]:
                    pts = pts[:-1]
                if len(pts) >= 3 and Polygon(pts).area > 1e-6:
                    objetos.append({"id": e["handle"], "capa": e["capa"], "puntos": pts, "origen": "polilínea cerrada"})
                    continue
            abiertas.setdefault(e["capa"], []).append((e["handle"], LineString(e["puntos"])))
        for capa, lineas in abiertas.items():           # contornos formados por líneas sueltas
            try:
                # Los extremos que deberían coincidir suelen diferir en el último decimal si el dibujo usa
                # coordenadas grandes; se ajustan a una rejilla antes de polygonize o el anillo no cierra.
                geom = set_precision(unary_union([ln for _, ln in lineas]), TOL_SNAP)
                polys = [p for p in polygonize(geom) if p.area > 1e-6]
                borde = unary_union([p.boundary for p in polys]).buffer(TOL_SNAP)
                sueltas = [h for h, ln in lineas if not borde.covers(ln)]
                if sueltas:
                    self.lineas_sin_contorno[capa] = sueltas
                for i, poly in enumerate(polys, 1):
                    objetos.append({"id": f"LN:{capa}:{i}", "capa": capa,
                                    "puntos": list(poly.exterior.coords)[:-1], "origen": "líneas unidas"})
            except Exception:
                pass
        for o in objetos:                               # nombre = TEXT contenido en el polígono
            poly = Polygon(o["puntos"]).buffer(1e-6)
            dentro = [t["texto"] for t in self.textos if poly.contains(Point(t["punto"]))]
            o["nombre"] = dentro[0] if dentro else ""
            o["altura_capa"] = altura_desde_capa(o["capa"])
        return objetos

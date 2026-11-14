"""Lectura de DXF -> geometría 2D en METROS.

- extraer_geometria(): entidades sueltas para dibujar (compatible con la versión anterior).
- extraer_objetos(): polígonos cerrados (obstrucciones / vivienda), con nombre si hay un TEXT dentro.
Soporta LINE, LWPOLYLINE/POLYLINE (con bulges), CIRCLE, ARC, ELLIPSE, SPLINE, HATCH (vía ezdxf.path) e INSERT (bloques).
Los LINE o polilíneas abiertas que forman contornos cerrados se reconstruyen con shapely.polygonize.

Unidades: se lee $INSUNITS y las coordenadas se escalan a metros al leer, de modo que el resto del
programa trabaja siempre en metros. Si el DXF no declara unidades (0 o ausente) hay que indicar la
unidad del dibujo con ImportadorDXF(ruta, unidad="m"|"cm"|"mm").
"""
from __future__ import annotations
import re
import ezdxf
from ezdxf import path as ezpath
from shapely import set_precision
from shapely.geometry import LineString, Polygon, Point
from shapely.ops import unary_union, polygonize

TOL_CIERRE = 1e-6   # m
TOL_SNAP = 1e-3     # m: absorbe el ruido de redondeo de los exportadores CAD
FLATTEN = 0.05      # m, paso de aplanado de curvas

# $INSUNITS de AutoCAD -> (nombre, factor a metros). Solo los que pueden aparecer en un plano.
UNIDADES_INSUNITS: dict[int, tuple[str, float]] = {
    1: ("in", 0.0254), 2: ("ft", 0.3048), 3: ("mi", 1609.344), 4: ("mm", 0.001),
    5: ("cm", 0.01), 6: ("m", 1.0), 7: ("km", 1000.0), 8: ("µin", 2.54e-8),
    9: ("mil", 2.54e-5), 10: ("yd", 0.9144), 11: ("Å", 1e-10), 12: ("nm", 1e-9),
    13: ("µm", 1e-6), 14: ("dm", 0.1), 15: ("dam", 10.0), 16: ("hm", 100.0),
    17: ("Gm", 1e9), 18: ("AU", 1.495978707e11), 19: ("año luz", 9.4607304725808e15),
    20: ("pc", 3.085677581491367e16),
}

# Unidades que puede elegir el usuario cuando el DXF no declara ninguna.
UNIDADES_MANUALES: dict[str, float] = {"m": 1.0, "cm": 0.01, "mm": 0.001}


def sugerir_unidad(extension: float | None) -> str | None:
    """Unidad probable según el tamaño del dibujo, solo como pista (nunca se preselecciona)."""
    if not extension or extension <= 0:
        return None
    if extension > 2000:
        return "mm"
    if extension > 200:
        return "cm"
    return "m"


def resolver_unidad(info: dict, eleccion: str | None = None):
    """Decide la unidad a usar: (unidad, factor, origen) o None si falta elegirla.

    Si el DXF declara $INSUNITS, manda lo declarado. Si no, hace falta `eleccion` (m, cm o mm).
    """
    if info.get("factor") is not None:
        return info["unidad"], info["factor"], "declarada en el DXF ($INSUNITS)"
    if eleccion is None:
        return None
    if eleccion not in UNIDADES_MANUALES:
        raise ValueError(f"Unidad no admitida: {eleccion!r} (usa m, cm o mm).")
    return eleccion, UNIDADES_MANUALES[eleccion], "elegida por el usuario"


def inspeccionar_unidades(ruta_archivo) -> dict:
    """{'insunits', 'unidad', 'factor', 'extension', 'sugerencia'} sin leer la geometría completa."""
    doc = ezdxf.readfile(ruta_archivo)
    codigo = int(doc.header.get("$INSUNITS", 0) or 0)
    unidad, factor = UNIDADES_INSUNITS.get(codigo, (None, None))
    extension = None
    try:
        emin, emax = doc.header["$EXTMIN"], doc.header["$EXTMAX"]
        extension = max(float(emax[0]) - float(emin[0]), float(emax[1]) - float(emin[1]))
        if not (0 < extension < 1e18):       # EXTMIN/EXTMAX sin calcular quedan en ±1e20
            extension = None
    except Exception:
        pass
    return {"insunits": codigo, "unidad": unidad, "factor": factor,
            "extension": extension, "sugerencia": sugerir_unidad(extension)}


def altura_desde_capa(capa: str):
    """'EDIFICIO_B_H15' -> 15.0 ; 'ELEMENTOS_H3.5' -> 3.5 ; otro -> None"""
    m = re.search(r"[_\-\s]H(\d+(?:[.,]\d+)?)$", capa.strip(), flags=re.I)
    return float(m.group(1).replace(",", ".")) if m else None


class ImportadorDXF:
    def __init__(self, ruta_archivo, unidad: str | None = None):
        """unidad: "m", "cm" o "mm"; solo se usa si el DXF no declara $INSUNITS."""
        self.doc = ezdxf.readfile(ruta_archivo)
        self.msp = self.doc.modelspace()
        self.insunits = int(self.doc.header.get("$INSUNITS", 0) or 0)
        nombre, factor = UNIDADES_INSUNITS.get(self.insunits, (None, None))
        if factor is None:
            if unidad is None:
                raise ValueError("El DXF no declara unidades ($INSUNITS): indica la unidad del dibujo "
                                 "con ImportadorDXF(ruta, unidad='m'|'cm'|'mm').")
            if unidad not in UNIDADES_MANUALES:
                raise ValueError(f"Unidad no admitida: {unidad!r} (usa m, cm o mm).")
            nombre, factor = unidad, UNIDADES_MANUALES[unidad]
        self.unidad = nombre                 # unidad del dibujo, solo informativa
        self.factor_a_metros = factor        # coordenadas del archivo * factor = metros
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
                    f = self.factor_a_metros
                    self.textos.append({"texto": " ".join(txt.split()), "punto": (p.x * f, p.y * f), "capa": capa})
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
                # FLATTEN está en metros: se convierte al paso equivalente en unidades del dibujo.
                paso = FLATTEN / self.factor_a_metros
                f = self.factor_a_metros
                pts = [(v.x * f, v.y * f) for v in pth.flattening(paso)]
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

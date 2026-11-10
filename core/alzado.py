"""Herramientas de alzado (elevación) del manual CEV 6.8:

  * Centro de una fachada irregular (Fig. 30 y 33): se inscribe el área de la fachada en un paralelepípedo
    (rectángulo en alzado) y se asume su centro como centro de la fachada. Se omiten elementos que no
    interrumpen el acondicionamiento térmico y muros con altura interior ≤ 1,6 m.
  * Altura promedio de un obstáculo de altura variable (Fig. 36 y 37): área de la obstrucción en alzado
    SOBRE el punto medio de la fachada dividida por la longitud de su base.

Convención: x = ancho (m), z = altura sobre el terreno (m).
"""
from __future__ import annotations

import plotly.graph_objects as go
from shapely.geometry import Polygon, box

MURO_BAJO_INTERIOR = 1.6   # m (manual 6.8: se omiten muros con altura interior ≤ 1,6 m)


def _fmt(x, nd=2):
    return f"{x:.{nd}f}".replace(".", ",")


def centro_alzado(cuerpos: dict[str, list[tuple[float, float]]], omitir: set[str] | None = None) -> dict | None:
    """Inscribe los cuerpos incluidos en un rectángulo y devuelve su centro. cuerpos: {nombre: [(x, z), ...]}"""
    omitir = omitir or set()
    xs, zs = [], []
    for nombre, pts in cuerpos.items():
        if nombre in omitir or len(pts) < 3:
            continue
        xs += [p[0] for p in pts]
        zs += [p[1] for p in pts]
    if not xs:
        return None
    x0, x1, z0, z1 = min(xs), max(xs), min(zs), max(zs)
    return {"x_min": x0, "x_max": x1, "z_min": z0, "z_max": z1, "ancho": x1 - x0, "alto": z1 - z0,
            "x_centro": (x0 + x1) / 2, "z_centro": (z0 + z1) / 2}


def figura_alzado(cuerpos, omitir, centro, titulo="Alzado de la fachada") -> go.Figure:
    omitir = omitir or set()
    fig = go.Figure()
    for nombre, pts in cuerpos.items():
        if len(pts) < 3:
            continue
        om = nombre in omitir
        xs = [p[0] for p in pts] + [pts[0][0]]
        zs = [p[1] for p in pts] + [pts[0][1]]
        fig.add_trace(go.Scatter(x=xs, y=zs, mode="lines", fill="toself",
                                 fillcolor="rgba(150,150,150,0.25)" if om else "rgba(15,105,180,0.25)",
                                 line=dict(color="#888" if om else "#0f69b4", width=2, dash="dot" if om else "solid"),
                                 name=f"{nombre}{' (omitido)' if om else ''}", hoverinfo="name"))
    if centro:
        bx = [centro["x_min"], centro["x_max"], centro["x_max"], centro["x_min"], centro["x_min"]]
        bz = [centro["z_min"], centro["z_min"], centro["z_max"], centro["z_max"], centro["z_min"]]
        fig.add_trace(go.Scatter(x=bx, y=bz, mode="lines", line=dict(color="#e65100", width=2, dash="dash"),
                                 name="Paralelepípedo inscrito", hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=[centro["x_min"], centro["x_max"]], y=[centro["z_centro"]] * 2, mode="lines",
                                 line=dict(color="#e65100", width=1, dash="dot"), showlegend=False, hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=[centro["x_centro"]] * 2, y=[centro["z_min"], centro["z_max"]], mode="lines",
                                 line=dict(color="#e65100", width=1, dash="dot"), showlegend=False, hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=[centro["x_centro"]], y=[centro["z_centro"]], mode="markers+text",
                                 marker=dict(size=12, color="#e65100", symbol="x"),
                                 text=[f"Punto medio  z = {_fmt(centro['z_centro'])} m"], textposition="top right",
                                 name="Centro de la fachada"))
    fig.update_layout(template="plotly_white", height=430, margin=dict(l=0, r=0, t=40, b=0), title=titulo,
                      xaxis=dict(title="Ancho (m)"), yaxis=dict(title="Altura sobre el terreno (m)", scaleanchor="x", scaleratio=1),
                      legend=dict(orientation="h", y=-0.2))
    return fig


def altura_promedio(poligono: list[tuple[float, float]], z_plano: float, longitud_base: float | None = None) -> dict | None:
    """Altura promedio (A) de un obstáculo irregular sobre el plano z_plano (punto medio de la fachada).

    Área de la obstrucción en alzado sobre ese plano / longitud de su base. Si no se da la base, se usa el
    ancho de la parte que queda sobre el plano."""
    if len(poligono) < 3:
        return None
    poly = Polygon(poligono)
    if not poly.is_valid:
        poly = poly.buffer(0)
    x0, z0, x1, z1 = poly.bounds
    sobre = poly.intersection(box(x0 - 1, z_plano, x1 + 1, max(z1, z_plano) + 1))
    if sobre.is_empty or sobre.area < 1e-9:
        return {"area_sobre": 0.0, "base": 0.0, "A_promedio": 0.0, "z_techo_max": z1, "geom": None}
    bx0, _, bx1, _ = sobre.bounds
    base = longitud_base if longitud_base and longitud_base > 0 else (bx1 - bx0)
    return {"area_sobre": float(sobre.area), "base": float(base), "A_promedio": float(sobre.area / base),
            "z_techo_max": float(z1), "geom": sobre}


def figura_altura_promedio(poligono, z_plano, info, titulo="Altura promedio del obstáculo (manual Fig. 37)") -> go.Figure:
    fig = go.Figure()
    if len(poligono) >= 3:
        xs = [p[0] for p in poligono] + [poligono[0][0]]
        zs = [p[1] for p in poligono] + [poligono[0][1]]
        fig.add_trace(go.Scatter(x=xs, y=zs, mode="lines", fill="toself", fillcolor="rgba(150,150,150,0.15)",
                                 line=dict(color="#555", width=2), name="Obstrucción en alzado", hoverinfo="name"))
    if info and info.get("geom") is not None:
        g = info["geom"]
        for part in getattr(g, "geoms", [g]):
            gx, gz = part.exterior.xy
            fig.add_trace(go.Scatter(x=list(gx), y=list(gz), mode="lines", fill="toself", fillcolor="rgba(90,90,90,0.55)",
                                     line=dict(color="#333", width=1), name="Área sobre el punto medio", hoverinfo="name"))
        x0, _, x1, _ = g.bounds
        a = info["A_promedio"]
        fig.add_trace(go.Scatter(x=[x0, x1], y=[z_plano + a] * 2, mode="lines", line=dict(color="#e65100", width=2, dash="dash"),
                                 name=f"Altura promedio A = {_fmt(a)} m"))
    xs_all = [p[0] for p in poligono] or [0, 1]
    fig.add_trace(go.Scatter(x=[min(xs_all) - 1, max(xs_all) + 1], y=[z_plano] * 2, mode="lines",
                             line=dict(color="#2e7d32", width=2), name=f"Punto medio de la fachada (z = {_fmt(z_plano)} m)"))
    fig.update_layout(template="plotly_white", height=430, margin=dict(l=0, r=0, t=40, b=0), title=titulo,
                      xaxis=dict(title="Ancho (m)"), yaxis=dict(title="Altura (m)", scaleanchor="x", scaleratio=1),
                      legend=dict(orientation="h", y=-0.2))
    return fig

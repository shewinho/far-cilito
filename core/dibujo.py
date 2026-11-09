"""Dibujo del FAR en planta, replicando las láminas del ejercicio de acreditación CEV:
  Paso 1  trazar el semicírculo y las 5 divisiones de 36°
  Paso 2  identificar las divisiones (División 1..5)
  Paso 3  obstrucciones por división: cono de visión, distancia B, ancho D (perpendicular a B) y rótulo B/D/A
"""
from __future__ import annotations

import math

import numpy as np
import plotly.graph_objects as go

from .far import ANCHO_DIV, N_DIVISIONES, ResultadoFachada, limites_division

COLOR_VIVIENDA = "#0f69b4"
COLOR_OBSTRUCCION = "#d9363e"
COLOR_EXCLUIDO = "#9aa0a6"
COLOR_CONO = "rgba(90,90,90,0.45)"


def _fmt(x, nd=1):
    return f"{x:.{nd}f}".replace(".", ",")


def _punto(O, az0, phi, r):
    a = math.radians(az0 + phi)
    return (O[0] + r * math.sin(a), O[1] + r * math.cos(a))


def _relleno_rayado(color):
    try:
        return dict(fill="toself", fillcolor="rgba(255,255,255,0)",
                    fillpattern=dict(shape="/", size=6, solidity=0.28, fgcolor=color, bgcolor="rgba(255,255,255,0.9)"))
    except Exception:  # pragma: no cover
        return dict(fill="toself", fillcolor="rgba(150,150,150,0.25)")


def figura_far(entidades: list[dict], objetos: list[dict], res: ResultadoFachada,
               paso: int = 3, division_foco: int | None = None,
               mostrar_omitidas: bool = True, ajustar_vista: bool = True,
               mostrar_rotulos: bool = True, mostrar_recuadros: bool = True) -> go.Figure:
    """objetos: [{'id','nombre','puntos','rol'}] con rol in {'vivienda','obstruccion','excluido'}."""
    fig = go.Figure()
    f = res.fachada
    O, az0 = f.punto_medio, f.azimut_normal
    visibles = [t for t in res.tramos if division_foco in (None, t.division)]

    bmax = max([t.B for t in res.tramos], default=0.0)
    R = max(bmax * 1.12, 25.0)

    # ---- geometría base del DXF (líneas que no son objetos cerrados)
    ids_obj = {o["id"] for o in objetos}
    xs, ys = [], []
    for e in entidades:
        if e["handle"] in ids_obj:
            continue
        xs += [p[0] for p in e["puntos"]] + [None]
        ys += [p[1] for p in e["puntos"]] + [None]
    if xs:
        fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", line=dict(color="#b8bcc2", width=1, dash="dashdot"),
                                 hoverinfo="skip", name="Otras líneas del DXF", showlegend=False))

    # ---- objetos con rayado como en el plano del manual
    for o in objetos:
        pts = list(o["puntos"]) + [o["puntos"][0]]
        color = {"vivienda": COLOR_VIVIENDA, "obstruccion": "#444", "excluido": COLOR_EXCLUIDO}[o["rol"]]
        fig.add_trace(go.Scatter(
            x=[p[0] for p in pts], y=[p[1] for p in pts], mode="lines", line=dict(color=color, width=1.6),
            hovertemplate=f"<b>{o.get('nombre') or o['id']}</b><br>handle {o['id']}<extra></extra>",
            showlegend=False,
            **(dict(fill="toself", fillcolor="rgba(15,105,180,0.10)") if o["rol"] == "vivienda" else _relleno_rayado(color))))
        if o.get("nombre"):
            from shapely.geometry import Polygon
            c = Polygon(o["puntos"]).representative_point()
            if o["rol"] == "vivienda":
                txt = "<b>Vivienda<br>evaluada</b>"
            else:
                txt = f"<b>{o['nombre']}</b>" + (f"<br>h= {_fmt(o['altura'], 1)} m" if o.get("altura") else "")
            fig.add_annotation(x=c.x, y=c.y, text=txt, showarrow=False, font=dict(size=9, color="#222"),
                               bgcolor="rgba(255,255,255,0.75)", borderpad=1)
    fig.add_trace(go.Scatter(x=[O[0]], y=[O[1]], mode="markers", marker=dict(size=9, color="black", symbol="circle"),
                             hovertemplate="Punto medio de la fachada<br>(%{x:.2f}, %{y:.2f})<extra></extra>", showlegend=False))

    # ---- sector resaltado de la división en foco
    if division_foco:
        a0, a1 = limites_division(division_foco)
        th = np.linspace(a0, a1, 40)
        pts = [O] + [_punto(O, az0, p, R) for p in th] + [O]
        fig.add_trace(go.Scatter(x=[p[0] for p in pts], y=[p[1] for p in pts], mode="lines", fill="toself",
                                 fillcolor="rgba(255,235,59,0.18)", line=dict(width=0), hoverinfo="skip", showlegend=False))

    # ---- PASO 1: semicírculo, base y divisiones de 36°
    th = np.linspace(-90, 90, 181)
    arco = [_punto(O, az0, p, R) for p in th]
    fig.add_trace(go.Scatter(x=[p[0] for p in arco], y=[p[1] for p in arco], mode="lines",
                             line=dict(color="black", width=1.6), hoverinfo="skip", showlegend=False))
    base = [_punto(O, az0, -90, R), _punto(O, az0, 90, R)]
    fig.add_trace(go.Scatter(x=[base[0][0], base[1][0]], y=[base[0][1], base[1][1]], mode="lines",
                             line=dict(color="#555", width=1, dash="dot"), hoverinfo="skip", showlegend=False))
    for k in range(N_DIVISIONES + 1):
        phi = -90 + k * ANCHO_DIV
        p = _punto(O, az0, phi, R)
        fig.add_trace(go.Scatter(x=[O[0], p[0]], y=[O[1], p[1]], mode="lines",
                                 line=dict(color="#e91e8c", width=1), hoverinfo="skip", showlegend=False))
    for k in range(1, N_DIVISIONES + 1):
        a0, a1 = limites_division(k)
        t = _punto(O, az0, (a0 + a1) / 2, R * 0.9)
        fig.add_annotation(x=t[0], y=t[1], text="36°", showarrow=False, font=dict(size=10))

    # ---- PASO 2: rótulos de división
    divs_con_recuadro = set() if (paso < 3 or not mostrar_recuadros) else ({division_foco} if division_foco else set(range(1, N_DIVISIONES + 1)))
    if paso >= 2:
        for k in range(1, N_DIVISIONES + 1):
            if k in divs_con_recuadro:
                continue
            a0, a1 = limites_division(k)
            t = _punto(O, az0, (a0 + a1) / 2, R * 1.045)
            fig.add_annotation(x=t[0], y=t[1], text=f"<b>División {k}</b>", showarrow=False,
                               font=dict(size=12, color="#0f69b4" if division_foco in (None, k) else "#9aa0a6"))

    # ---- PASO 3: obstrucciones
    if paso >= 3:
        for t in visibles:
            cono = [O] + t.cara_visible + [O]
            gris = COLOR_CONO if t.estado != "desestimable" else "rgba(200,160,60,0.35)"
            fig.add_trace(go.Scatter(x=[p[0] for p in cono], y=[p[1] for p in cono], mode="lines", fill="toself",
                                     fillcolor=gris, line=dict(color="rgba(60,60,60,0.6)", width=0.8),
                                     hovertemplate=(f"<b>{t.nombre}</b> · División {t.division}<br>A={_fmt(t.A,2)} m · B={_fmt(t.B,2)} m · "
                                                    f"D={_fmt(t.D,2)} m<extra></extra>"), showlegend=False))
        for n_t, t in enumerate(visibles):
            pb = t.punto_b
            fig.add_annotation(x=pb[0], y=pb[1], ax=O[0], ay=O[1], xref="x", yref="y", axref="x", ayref="y",
                               showarrow=True, arrowhead=2, arrowsize=1.1, arrowwidth=1.6, arrowcolor="black")
            fig.add_trace(go.Scatter(x=[t.p_d1[0], t.p_d2[0]], y=[t.p_d1[1], t.p_d2[1]], mode="lines+markers",
                                     line=dict(color="#e65100", width=2),
                                     marker=dict(symbol="line-ns-open", size=9, color="#e65100",
                                                 angleref="previous"), hoverinfo="skip", showlegend=False))
            # marca de ángulo recto entre B y D
            ux, uy = (pb[0] - O[0]), (pb[1] - O[1]); n = math.hypot(ux, uy); ux, uy = ux / n, uy / n
            vx, vy = -uy, ux
            s = min(max(R * 0.012, 0.4), 2.0)
            sq = [(pb[0] - ux * s, pb[1] - uy * s), (pb[0] - ux * s + vx * s, pb[1] - uy * s + vy * s), (pb[0] + vx * s, pb[1] + vy * s)]
            fig.add_trace(go.Scatter(x=[p[0] for p in sq], y=[p[1] for p in sq], mode="lines", line=dict(color="#e65100", width=1),
                                     hoverinfo="skip", showlegend=False))
            if mostrar_rotulos:
                fr = 0.45 + 0.14 * (n_t % 3)
                mid = (O[0] + (pb[0] - O[0]) * fr, O[1] + (pb[1] - O[1]) * fr)
                fig.add_annotation(x=mid[0], y=mid[1], text=_fmt(t.B, 1), showarrow=False, font=dict(size=11, color="black"),
                                   bgcolor="rgba(255,255,255,0.85)", borderpad=1)
                dm = ((t.p_d1[0] + t.p_d2[0]) / 2, (t.p_d1[1] + t.p_d2[1]) / 2)
                fig.add_annotation(x=dm[0] + vx * 0, y=dm[1] + vy * 0, text=_fmt(t.D, 1), showarrow=False,
                                   font=dict(size=10, color="#e65100"), bgcolor="rgba(255,255,255,0.8)", borderpad=1, yshift=9)

        # recuadros por división (como en las láminas: Edificio B / B= / D= / A=)
        por_div: dict[int, list] = {}
        for t in visibles:
            por_div.setdefault(t.division, []).append(t)
        divs_a_rotular = [] if not mostrar_recuadros else ([division_foco] if division_foco else range(1, N_DIVISIONES + 1))
        for k in divs_a_rotular:
            a0, a1 = limites_division(k)
            lineas = [f"<b>División {k}</b>"]
            ts = por_div.get(k, [])
            omit = [o for o in res.omitidas if o["division"] == k] if mostrar_omitidas else []
            if not ts and not omit:
                lineas.append("No hay obstrucciones")
            for t in ts:
                lineas.append(f"<b>{t.nombre}</b>" + (" (desestimable)" if t.estado == "desestimable" else ""))
                lineas.append(f"B= {_fmt(t.B)} m · D= {_fmt(t.D)} m")
                lineas.append(f"A= {_fmt(t.altura_obstruccion, 1)}−{_fmt(res.altura_punto_medio, 1)} = {_fmt(t.A, 1)} m")
            for o in omit:
                lineas.append(f"<i>{o['nombre']}: omitida</i>")
            p = _punto(O, az0, (a0 + a1) / 2, R * 1.07)
            xa, ya = {1: ("right", "middle"), 2: ("right", "bottom"), 3: ("center", "bottom"),
                      4: ("left", "bottom"), 5: ("left", "middle")}[k]
            fig.add_annotation(x=p[0], y=p[1], xanchor=xa, yanchor=ya, text="<br>".join(lineas), showarrow=False, align="left",
                               font=dict(size=9.5, color="#222"), bgcolor="rgba(255,255,255,0.9)",
                               bordercolor="#bbb", borderwidth=1, borderpad=3)

    fig.update_layout(
        template="plotly_white", height=760, margin=dict(l=0, r=0, t=30, b=0),
        title=dict(text=f"{f.nombre} · azimut del eje ortogonal {f.azimut_real:.0f}° · punto medio ({O[0]:.2f}, {O[1]:.2f})",
                   font=dict(size=13)),
        xaxis=dict(visible=False), yaxis=dict(visible=False, scaleanchor="x", scaleratio=1),
        dragmode="pan",
    )
    if ajustar_vista:
        pts = [_punto(O, az0, p, R * 1.62) for p in (-90, -54, -18, 0, 18, 54, 90)] + [O]
        for q in [_punto(O, az0, p, 0.35 * R) for p in (180,)]:
            pts.append(q)
        xs_, ys_ = [p[0] for p in pts], [p[1] for p in pts]
        m = 0.04 * R
        fig.update_xaxes(range=[min(xs_) - m, max(xs_) + m])
        fig.update_yaxes(range=[min(ys_) - m, max(ys_) + m])
    return fig

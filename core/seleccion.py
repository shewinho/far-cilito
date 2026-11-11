"""Selección por clic sobre el dibujo (Plotly + st.plotly_chart(on_select=...))."""
from __future__ import annotations

import math

import plotly.graph_objects as go
from shapely.geometry import Polygon

PREFIJO_ARISTA = "ARISTA:"


def densificar(puntos, paso: float = 1.0, max_puntos: int = 60):
    """Puntos a lo largo del contorno para que el polígono sea fácil de pinchar (Plotly selecciona puntos, no líneas)."""
    pts = list(puntos) + [puntos[0]]
    largo = sum(math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))
    paso = max(paso, largo / max_puntos)
    out = []
    for a, b in zip(pts[:-1], pts[1:]):
        d = math.dist(a, b)
        n = max(1, int(d // paso))
        out += [(a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n) for k in range(n)]
    return out


def ids_desde_evento(evento) -> list[str]:
    """Extrae los ids (customdata) de los puntos seleccionados, sin repetir y en orden."""
    try:
        puntos = evento["selection"]["points"]
    except (KeyError, TypeError):
        try:
            puntos = evento.selection.points
        except AttributeError:
            return []
    ids = []
    for p in puntos or []:
        cd = p.get("customdata") if isinstance(p, dict) else None
        if isinstance(cd, (list, tuple)):
            cd = cd[0] if cd else None
        if cd is not None and str(cd) not in ids:
            ids.append(str(cd))
    return ids


def actualizar_seleccion(modo: str, clics: list[str], vivienda_id: str | None, obstruccion_ids: list[str],
                         arista: int | None = None):
    """Aplica los clics al estado.

    modo: 'vivienda' (el clic define la vivienda), 'obstruccion' (cada clic alterna la inclusión),
          'fachada' (clic sobre el centro de una arista de la vivienda).
    Devuelve (vivienda_id, obstruccion_ids, arista).
    """
    obs = list(obstruccion_ids)
    for c in clics:
        if c.startswith(PREFIJO_ARISTA):
            if modo == "fachada":
                arista = int(c[len(PREFIJO_ARISTA):])
            continue
        if modo == "vivienda":
            vivienda_id = c
            obs = [o for o in obs if o != c]
        elif modo == "obstruccion" and c != vivienda_id:
            obs = [o for o in obs if o != c] if c in obs else obs + [c]
    return vivienda_id, obs, arista


def figura_seleccion(entidades, objetos, vivienda_id, obstruccion_ids, aristas=None, arista_sel=None,
                     titulo="Haz clic sobre el plano", altura=640, foco_id=None, sin_altura=None) -> go.Figure:
    """objetos: [{'id','nombre','puntos','capa'}]. Marcadores clicables en el contorno y el centro de cada objeto."""
    fig = go.Figure()
    ids_obj = {o["id"] for o in objetos}
    xs, ys = [], []
    for e in entidades:
        if e["handle"] in ids_obj:
            continue
        xs += [p[0] for p in e["puntos"]] + [None]
        ys += [p[1] for p in e["puntos"]] + [None]
    if xs:
        fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", line=dict(color="#b8bcc2", width=1, dash="dashdot"),
                                 hoverinfo="skip", showlegend=False))
    sin_altura = sin_altura or set()
    mx, my, mid, mtxt = [], [], [], []
    for o in objetos:
        es_viv = o["id"] == vivienda_id
        es_obs = o["id"] in obstruccion_ids
        falta = es_obs and o["id"] in sin_altura
        color = "#0f69b4" if es_viv else (("#f08c00" if falta else "#d9363e") if es_obs else "#9aa0a6")
        rotulo = o.get("nombre") or o["id"]
        pts = list(o["puntos"]) + [o["puntos"][0]]
        fig.add_trace(go.Scatter(
            x=[p[0] for p in pts], y=[p[1] for p in pts], mode="lines", line=dict(color=color, width=2.5 if (es_viv or es_obs) else 1),
            fill="toself", fillcolor={"#0f69b4": "rgba(15,105,180,0.20)", "#d9363e": "rgba(217,54,62,0.18)",
                       "#f08c00": "rgba(240,140,0,0.25)"}.get(color, "rgba(150,150,150,0.10)"),
            hoverinfo="skip", showlegend=False))
        c = Polygon(o["puntos"]).representative_point()
        etiqueta = "Vivienda" if es_viv else (("⚠ falta altura" if falta else "Obstrucción") if es_obs else "sin usar")
        texto = "<b>Vivienda evaluada</b>" if es_viv else f"<b>{rotulo}</b><br><i>{etiqueta}</i>"
        fig.add_annotation(x=c.x, y=c.y, text=texto, showarrow=False, font=dict(size=9, color="#222"),
                           bgcolor="rgba(255,255,255,0.75)", borderpad=1)
        for p in densificar(o["puntos"]) + [(c.x, c.y)]:
            mx.append(p[0]); my.append(p[1]); mid.append(o["id"]); mtxt.append(f"{rotulo} · {etiqueta}")
    if foco_id:
        of = next((o for o in objetos if o["id"] == foco_id), None)
        if of:
            pf = list(of["puntos"]) + [of["puntos"][0]]
            fig.add_trace(go.Scatter(x=[p[0] for p in pf], y=[p[1] for p in pf], mode="lines",
                                     line=dict(color="#f2c500", width=6), hoverinfo="skip", showlegend=False))
    fig.add_trace(go.Scatter(x=mx, y=my, mode="markers", customdata=mid, text=mtxt,
                             marker=dict(size=14, color="rgba(0,0,0,0.01)"), hovertemplate="%{text}<br>clic para editar<extra></extra>",
                             selected=dict(marker=dict(opacity=0.01)), unselected=dict(marker=dict(opacity=0.01)),
                             showlegend=False, name="objetos"))
    if aristas:
        ax, ay, aid, atxt = [], [], [], []
        for a in aristas:
            ax.append(a["punto_medio"][0]); ay.append(a["punto_medio"][1]); aid.append(f"{PREFIJO_ARISTA}{a['indice']}")
            atxt.append(f"Fachada {a['azimut']:.0f}° (arista {a['indice']})")
        sel = [a["indice"] == arista_sel for a in aristas]
        fig.add_trace(go.Scatter(x=ax, y=ay, mode="markers", customdata=aid, text=atxt,
                                 marker=dict(size=[16 if s else 11 for s in sel], symbol="diamond",
                                             color=["#e65100" if s else "#fff" for s in sel], line=dict(color="#e65100", width=2)),
                                 hovertemplate="%{text}<br>clic para elegirla (modo Fachada)<extra></extra>", showlegend=False))
    fig.update_layout(template="plotly_white", height=altura, margin=dict(l=0, r=0, t=36, b=0), title=dict(text=titulo, font=dict(size=13)),
                      xaxis=dict(visible=False), yaxis=dict(visible=False, scaleanchor="x", scaleratio=1), dragmode="pan", clickmode="event+select")
    return fig

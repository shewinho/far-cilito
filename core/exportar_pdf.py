"""Memoria de cálculo del FAR en PDF (Manual CEV 2025, secciones 6.8 y 11.8).

Genera un PDF en memoria con los datos de la vivienda y la fachada, la tabla de obstrucciones
(A, B, D, división y ángulo) y la lámina vectorial del semicírculo con sus 5 divisiones de 36°.

No calcula ni muestra el factor FAR final: la ecuación FAR(A,B,D) está pendiente de validación
con MINVU (ver core/reglas.py). El PDF solo reproduce lo que el motor sí calcula.

No depende de Streamlit ni escribe archivos temporales: devuelve los bytes para que la interfaz
los ofrezca como descarga.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from io import BytesIO

from reportlab.graphics.shapes import Circle, Drawing, Line, Polygon, PolyLine, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (BaseDocTemplate, Frame, PageBreak, PageTemplate, Paragraph,
                                Spacer, Table, TableStyle)

from .far import N_DIVISIONES, ResultadoFachada, limites_division
from .reglas import VERSION_REGLAS

# Texto único del aviso: lo usan el PDF y las pruebas, para que no puedan divergir.
AVISO_FAR = ("FAR final: no calculado. La ecuación FAR(A,B,D) está pendiente de validación con "
             "MINVU; este documento entrega solo A, B y D, que son datos de entrada al FAR.")

AZUL = colors.HexColor("#0f69b4")
GRIS = colors.HexColor("#6b7280")
GRIS_CLARO = colors.HexColor("#e5e7eb")
NARANJA = colors.HexColor("#e65100")
FONDO_AVISO = colors.HexColor("#fff4e5")
GRIS_CABECERA = colors.HexColor("#374151")
CONO = colors.HexColor("#d1d5db")

MARGEN = 18 * mm
ANCHO_UTIL = A4[0] - 2 * MARGEN

_ESTILO_TITULO = ParagraphStyle("titulo", fontName="Helvetica-Bold", fontSize=15, leading=18,
                                textColor=AZUL, spaceAfter=2)
_ESTILO_SUBTITULO = ParagraphStyle("subtitulo", fontName="Helvetica", fontSize=8.5, leading=11,
                                   textColor=GRIS)
_ESTILO_H2 = ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=10.5, leading=13,
                            textColor=colors.black, spaceBefore=6, spaceAfter=3)
_ESTILO_SECCION = ParagraphStyle("seccion", fontName="Helvetica-Bold", fontSize=9, leading=11,
                                 textColor=GRIS_CABECERA, spaceBefore=4, spaceAfter=2)
_ESTILO_TEXTO = ParagraphStyle("texto", fontName="Helvetica", fontSize=8, leading=10.5)
_ESTILO_CELDA = ParagraphStyle("celda", fontName="Helvetica", fontSize=7.5, leading=9)
_ESTILO_ETIQUETA = ParagraphStyle("celda_p", fontName="Helvetica", fontSize=7, leading=8.5,
                                  textColor=GRIS)
_ESTILO_AVISO = ParagraphStyle("aviso", fontName="Helvetica", fontSize=8.5, leading=11,
                               textColor=colors.HexColor("#7c2d12"))


# ------------------------------------------------------------------ datos de la tabla
def numero(x: float | None, decimales: int = 2) -> str:
    """Formato local (coma decimal). Un valor ausente se muestra como raya, nunca como cero."""
    if x is None or not math.isfinite(x):
        return "—"
    return f"{x:.{decimales}f}".replace(".", ",")


def filas_obstrucciones(res: ResultadoFachada, excluidos=()) -> list[dict]:
    """Filas de la tabla con los valores crudos del motor (sin formatear).

    `excluidos` contiene pares (division, obstruccion_id) que el evaluador desestimó de forma
    explícita; no altera los valores, solo la marca `incluida`.
    """
    excl = set(excluidos)
    return [{
        "division": t.division,
        "obstruccion": t.nombre,
        "obstruccion_id": t.obstruccion_id,
        "capa": t.capa,
        "A": t.A,
        "B": t.B,
        "D": t.D,
        "B_D": t.B / t.D if t.D > 1e-9 else None,
        "B_A": t.B / t.A if t.A > 1e-9 else None,
        "angulo": t.angulo_elevacion,
        "estado": t.estado,
        "incluida": (t.division, t.obstruccion_id) not in excl,
    } for t in res.tramos]


# ------------------------------------------------------------------------ lámina
def _plana(puntos) -> list[float]:
    """ReportLab pide las polilíneas como [x1, y1, x2, y2, ...]."""
    return [c for p in puntos for c in p]


def _lamina(res: ResultadoFachada, ancho: float = ANCHO_UTIL - 8, alto: float = 205) -> Drawing:
    """Semicírculo con las 5 divisiones y las obstrucciones acotadas, en vector."""
    f = res.fachada
    O = f.punto_medio
    az0 = f.azimut_normal
    bmax = max([t.B for t in res.tramos], default=0.0)
    R = max(bmax * 1.12, 25.0)

    def punto(phi: float, r: float) -> tuple[float, float]:
        a = math.radians(az0 + phi)
        return (O[0] + r * math.sin(a), O[1] + r * math.cos(a))

    arco = [punto(-90 + k * 2.0, R) for k in range(91)]

    # todo lo que hay que encuadrar: arco, punto medio y el cono de cada tramo
    pts = arco + [O]
    for t in res.tramos:
        pts += list(t.cara_visible) + [t.punto_b, t.p_d1, t.p_d2]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    sx = max(x1 - x0, 1e-6)
    sy = max(y1 - y0, 1e-6)
    pad = 10.0          # margen para que los rótulos de división no queden cortados
    escala = min((ancho - 2 * pad) / sx, (alto - 2 * pad) / sy)
    mx = (ancho - sx * escala) / 2
    my = (alto - sy * escala) / 2

    def txy(p) -> tuple[float, float]:
        return ((p[0] - x0) * escala + mx, (p[1] - y0) * escala + my)

    dib = Drawing(ancho, alto)

    # cono de visión de cada tramo
    for t in res.tramos:
        cono = [O] + list(t.cara_visible) + [O]
        dib.add(Polygon(_plana([txy(p) for p in cono]), fillColor=CONO,
                        strokeColor=colors.HexColor("#9ca3af"), strokeWidth=0.5))

    # semicírculo y base
    dib.add(PolyLine(_plana([txy(p) for p in arco]), strokeColor=colors.black, strokeWidth=1.2))
    base = Line(*txy(arco[0]), *txy(arco[-1]), strokeColor=GRIS, strokeWidth=0.6,
                strokeDashArray=[2, 2])
    dib.add(base)

    # divisiones de 36°
    for k in range(1, N_DIVISIONES):
        dib.add(Line(*txy(O), *txy(punto(-90 + k * 36, R)), strokeColor=colors.HexColor("#e91e8c"),
                     strokeWidth=0.7))

    # etiquetas de división
    for k in range(1, N_DIVISIONES + 1):
        a0, a1 = limites_division(k)
        px, py = txy(punto((a0 + a1) / 2, R))
        dib.add(String(px, py + 2, f"Div. {k}", fontName="Helvetica", fontSize=5.5,
                       fillColor=AZUL, textAnchor="middle"))

    # cota de B y de D por tramo; el rótulo se separa alternando de lado para que no se pisen
    for i, t in enumerate(res.tramos):
        ox, oy = txy(O)
        bx, by = txy(t.punto_b)
        dib.add(Line(ox, oy, bx, by, strokeColor=colors.black, strokeWidth=0.8))
        dx, dy = bx - ox, by - oy
        n = math.hypot(dx, dy) or 1.0
        # perpendicular a B: se alterna el lado y la distancia para separar rótulos vecinos
        lado = 1.0 if i % 2 == 0 else -1.0
        off = 6.0 + 2.0 * (i % 3)
        px, py = -dy / n * off * lado, dx / n * off * lado
        frac = (0.40, 0.58, 0.72)[i % 3]
        dib.add(String(ox + dx * frac + px, oy + dy * frac + py, numero(t.B, 1),
                       fontName="Helvetica-Bold", fontSize=5.5, fillColor=colors.black,
                       textAnchor="middle"))
        d1x, d1y = txy(t.p_d1)
        d2x, d2y = txy(t.p_d2)
        dib.add(Line(d1x, d1y, d2x, d2y, strokeColor=NARANJA, strokeWidth=1.2))
        dib.add(String((d1x + d2x) / 2 + px, (d1y + d2y) / 2 + py - 2, numero(t.D, 1),
                       fontName="Helvetica", fontSize=5.5, fillColor=NARANJA, textAnchor="middle"))

    ox, oy = txy(O)
    dib.add(Circle(ox, oy, 2.2, fillColor=colors.black, strokeColor=colors.black))
    return dib


# ------------------------------------------------------------------- documento
def _pie(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFont("Helvetica", 6.5)
    canvas.setFillColor(GRIS)
    canvas.drawString(MARGEN, 11 * mm, f"FARcilito · memoria de cálculo · reglas {VERSION_REGLAS}")
    canvas.drawRightString(A4[0] - MARGEN, 11 * mm, f"página {doc.page}")
    canvas.restoreState()


def _factor_txt(factor: float) -> str:
    """0.001 -> '0,001'; 1.0 -> '1'."""
    return f"{factor:.6g}".replace(".", ",")


def _tabla_datos(res: ResultadoFachada, vivienda_id: str, origen_dxf: str, fecha: str,
                 unidades: dict | None = None) -> Table:
    f = res.fachada
    pares = [
        ("Vivienda", str(vivienda_id)),
        ("Fachada", f.nombre),
        ("Orientación", f"{f.orientacion} ({numero(f.azimut_real, 1)}°)"),
        ("Rotación del Norte", f"{numero(f.rotacion_norte, 1)}°"),
        ("Punto medio (x, y)", f"({numero(f.punto_medio[0])}, {numero(f.punto_medio[1])}) m"),
        ("Modo del punto medio", f.modo_punto_medio),
        ("Cota del punto medio", f"{numero(res.altura_punto_medio, 2)} m"),
        ("Criterio de desestimación", res.criterio),
        ("Archivo DXF", origen_dxf),
        ("Generado", fecha),
    ]
    if unidades:
        pares += [
            ("Unidad del DXF", f"{unidades.get('dxf', '—')} ({unidades.get('origen', '—')})"),
            ("Factor a metros", f"{_factor_txt(unidades.get('factor_a_metros') or 0)} → coordenadas en m"),
        ]
    filas = []
    for i in range(0, len(pares), 2):
        a = pares[i]
        b = pares[i + 1] if i + 1 < len(pares) else ("", "")
        filas.append([Paragraph(a[0], _ESTILO_ETIQUETA), Paragraph(a[1], _ESTILO_CELDA),
                      Paragraph(b[0], _ESTILO_ETIQUETA), Paragraph(b[1], _ESTILO_CELDA)])
    tabla = Table(filas, colWidths=[32 * mm, 55 * mm, 32 * mm, 55 * mm])
    tabla.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 1.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, GRIS_CLARO),
    ]))
    return tabla


def _tabla_obstrucciones(res: ResultadoFachada, excluidos) -> Table:
    encabezado = ["Div.", "Obstrucción", "A (m)", "B (m)", "D (m)", "B/D", "B/A", "α (°)",
                  "Estado", "En CEV"]
    datos = [[Paragraph(h, ParagraphStyle("th", fontName="Helvetica-Bold", fontSize=7.5,
                                          leading=9, textColor=colors.white,
                                          alignment=1 if i else 0)) for i, h in enumerate(encabezado)]]
    for fila in filas_obstrucciones(res, excluidos):
        datos.append([
            str(fila["division"]),
            Paragraph(str(fila["obstruccion"]), _ESTILO_CELDA),
            numero(fila["A"], 2), numero(fila["B"], 2), numero(fila["D"], 2),
            numero(fila["B_D"], 2), numero(fila["B_A"], 2), numero(fila["angulo"], 1),
            Paragraph(fila["estado"], _ESTILO_CELDA),
            "sí" if fila["incluida"] else "no",
        ])
    if len(datos) == 1:
        datos.append(["—", Paragraph("Sin obstrucciones en el semicírculo.", _ESTILO_CELDA),
                      "—", "—", "—", "—", "—", "—", "—", "—"])
    anchos = [11, 44, 16, 16, 16, 13, 13, 14, 23, 13]
    tabla = Table(datos, colWidths=[w * mm for w in anchos], repeatRows=1)
    estilo = [
        ("BACKGROUND", (0, 0), (-1, 0), GRIS_CABECERA),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("ALIGN", (2, 1), (9, -1), "RIGHT"),
        ("ALIGN", (8, 1), (9, -1), "CENTER"),
        ("FONTSIZE", (0, 0), (-1, -1), 7.5),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("GRID", (0, 0), (-1, -1), 0.25, GRIS_CLARO),
    ]
    for i, fila in enumerate(datos[1:], start=1):
        if i % 2 == 0:
            estilo.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#f9fafb")))
    tabla.setStyle(TableStyle(estilo))
    return tabla


def _aviso_far() -> Table:
    tabla = Table([[Paragraph("<b>FAR final no incluido en esta memoria</b><br/>" + AVISO_FAR,
                              _ESTILO_AVISO)]], colWidths=[ANCHO_UTIL])
    tabla.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), FONDO_AVISO),
        ("BOX", (0, 0), (-1, -1), 0.8, NARANJA),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return tabla


def _historia(resultados: list[ResultadoFachada], vivienda_id: str, origen_dxf: str,
              excluidos_por_fachada: dict, fecha: str, unidades: dict | None = None) -> list:
    historia: list = [
        Paragraph("Memoria de cálculo FAR", _ESTILO_TITULO),
        Paragraph("Manual de Procedimientos CEV 2025 · secciones 6.8 y 11.8 · "
                  f"reglas <b>{VERSION_REGLAS}</b>", _ESTILO_SUBTITULO),
        Spacer(1, 6),
    ]
    for i, res in enumerate(resultados):
        excluidos = excluidos_por_fachada.get(res.fachada.nombre, set())
        historia += [
            Paragraph(res.fachada.nombre, _ESTILO_H2),
            _tabla_datos(res, vivienda_id, origen_dxf, fecha, unidades),
            Paragraph("Obstrucciones por división", _ESTILO_SECCION),
            _tabla_obstrucciones(res, excluidos),
        ]
        if res.omitidas:
            motivos = "<br/>".join(
                f"• {o['nombre']}"
                + (f" (división {o['division']})" if o.get("division") else "")
                + f": {o['motivo']}" for o in res.omitidas)
            historia += [Paragraph("Obstrucciones omitidas", _ESTILO_SECCION),
                         Paragraph(motivos, _ESTILO_TEXTO)]
        historia += [Spacer(1, 6), _aviso_far(), Spacer(1, 10),
                     Paragraph("Lámina de la fachada", _ESTILO_SECCION),
                     Spacer(1, 2), _lamina(res), Spacer(1, 6),
                     Paragraph("Lámina generada por el motor: semicírculo de 180° con 5 divisiones de "
                               "36°, cono de visión, B y D de cada obstrucción. La numeración de las "
                               "divisiones es de izquierda a derecha para un observador dentro de la "
                               "vivienda.", _ESTILO_TEXTO)]
        if res.advertencias:
            historia += [Spacer(1, 4), Paragraph("Advertencias", _ESTILO_SECCION),
                         Paragraph("<br/>".join("• " + a for a in res.advertencias), _ESTILO_TEXTO)]
        if i < len(resultados) - 1:
            historia.append(PageBreak())
    return historia


def memoria_pdf(resultados: list[ResultadoFachada], vivienda_id: str, origen_dxf: str,
                excluidos_por_fachada: dict | None = None,
                fecha: datetime | None = None,
                unidades: dict | None = None) -> bytes:
    """Devuelve el PDF de la memoria de cálculo (una sección por fachada).

    excluidos_por_fachada: {nombre_fachada: {(division, obstruccion_id), ...}}.
    fecha: instante a informar; por defecto, ahora en UTC.
    unidades: {'dxf', 'factor_a_metros', 'origen', ...} para la trazabilidad del PDF.
    """
    if not resultados:
        raise ValueError("Se necesita al menos una fachada calculada para generar la memoria.")
    excluidos_por_fachada = excluidos_por_fachada or {}
    fecha = fecha or datetime.now(timezone.utc)
    sello = fecha.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    buf = BytesIO()
    doc = BaseDocTemplate(
        buf, pagesize=A4, leftMargin=MARGEN, rightMargin=MARGEN, topMargin=MARGEN,
        bottomMargin=15 * mm, title="Memoria de cálculo FAR",
        author="FARcilito", subject="Manual CEV 2025, secciones 6.8 y 11.8",
        # sin comprimir el flujo de página: el texto queda legible en los bytes del PDF
        pageCompression=0,
    )
    marco = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="normal",
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate(id="pagina", frames=[marco], onPage=_pie)])
    doc.build(_historia(resultados, vivienda_id, origen_dxf, excluidos_por_fachada, sello, unidades))
    return buf.getvalue()

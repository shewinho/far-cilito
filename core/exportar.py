"""Exportación de resultados (trazabilidad) en el orden de ingreso de la sección 11.8 del manual."""
from __future__ import annotations
from datetime import datetime, timezone
from .far import ResultadoFachada, Tramo
from .reglas import VERSION_REGLAS


def tramo_a_dict(t: Tramo, incluido: bool = True) -> dict:
    return {
        "division": t.division, "obstruccion": t.nombre, "obstruccion_id": t.obstruccion_id, "capa": t.capa,
        "A": round(t.A, 2), "B": round(t.B, 2), "D": round(t.D, 2),
        "cota_techo_obstruccion": round(t.altura_obstruccion, 2),
        "altura_edificio": None if t.altura_propia is None else round(t.altura_propia, 2),
        "cota_terreno_obstruccion": round(t.cota_terreno, 2),
        "angulo_elevacion_deg": round(t.angulo_elevacion, 2), "angulo_B_deg": round(t.angulo_b, 2),
        "B_sobre_D": None if t.D <= 1e-9 else round(t.B_sobre_D, 3), "B_sobre_A": round(t.B_sobre_A, 3),
        "estado": t.estado, "incluido_en_CEV": incluido, "notas": t.notas,
        "punto_B": [round(c, 3) for c in t.punto_b],
    }


def a_dict(res: ResultadoFachada, vivienda_id: str, excluidos: set[tuple[int, str]], origen_dxf: str) -> dict:
    f = res.fachada
    return {
        "version_reglas": VERSION_REGLAS,
        "generado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "archivo": origen_dxf,
        "vivienda_id": vivienda_id,
        "fachada": {
            "orientacion": f.orientacion, "azimut_eje_ortogonal": round(f.azimut_real, 2),
            "punto_medio": [round(c, 3) for c in f.punto_medio], "modo_punto_medio": f.modo_punto_medio,
            "detalle_punto_medio": f.detalle, "rotacion_norte": f.rotacion_norte,
        },
        "cota_punto_medio_fachada": res.altura_punto_medio,
        "criterio_desestimacion": res.criterio,
        "obstrucciones": [tramo_a_dict(t, (t.division, t.obstruccion_id) not in excluidos) for t in res.tramos],
        "omitidas": res.omitidas,
        "advertencias": res.advertencias,
        "far_final": "No calculado: ecuación FAR(A,B,D) pendiente de validación con MINVU",
    }


def a_dict_multiple(resultados: list[ResultadoFachada], vivienda_id: str, excluidos_por_fachada: dict, origen_dxf: str) -> dict:
    """Varias fachadas en un solo JSON. excluidos_por_fachada: {nombre_fachada: {(division, obstruccion_id), ...}}"""
    fachadas = [a_dict(r, vivienda_id, excluidos_por_fachada.get(r.fachada.nombre, set()), origen_dxf) for r in resultados]
    return {"version_reglas": VERSION_REGLAS, "archivo": origen_dxf, "vivienda_id": vivienda_id,
            "generado": fachadas[0]["generado"] if fachadas else None,
            "fachadas": [{k: v for k, v in f.items() if k not in ("version_reglas", "archivo", "vivienda_id", "generado")} for f in fachadas],
            "far_final": "No calculado: ecuación FAR(A,B,D) pendiente de validación con MINVU"}

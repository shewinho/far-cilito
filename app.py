import json
import math
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from core.dibujo import figura_far
from core.exportar import a_dict_multiple
from core.far import (ALTURA_PUNTO_MEDIO_DEFECTO, Fachada, Obstruccion, aristas_vivienda, calcular_fachada,
                      fachada_desde_arista, fachadas_de_vivienda, nombre_orientacion,
                      punto_medio_discontinuo)
from core.importador import ImportadorDXF
from core.reglas import VERSION_REGLAS

st.set_page_config(page_title="FARcilito - CEV", layout="wide")
st.title("🏠 FARcilito")
st.caption(f"Parámetros del FAR (A, B, D por división) · Manual CEV 2025, secc. 6.8 y 11.8 · Reglas: {VERSION_REGLAS}")

RUTA_EJEMPLO = Path(__file__).parent / "data" / "ejemplo_manual.dxf"
CRITERIOS = {
    "No desestimar (solo informar los cocientes)": "ninguno",
    "Literal del manual: B/D < 0,1 o B/A < 0,1": "literal",
    "Invertido: D/B < 0,1 o A/B < 0,1": "invertido",
}


def fmt(x, nd=2):
    return f"{x:.{nd}f}".replace(".", ",")


def mostrar(obj, **kw):
    """st.plotly_chart / st.dataframe compatibles con versiones nuevas y antiguas de Streamlit."""
    fn = st.plotly_chart if hasattr(obj, "to_plotly_json") else st.dataframe
    try:
        return fn(obj, width="stretch", **kw)
    except TypeError:
        return fn(obj, use_container_width=True, **kw)


@st.cache_data(show_spinner="Leyendo DXF…")
def importar(contenido: bytes):
    with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as tmp:
        tmp.write(contenido)
        ruta = tmp.name
    try:
        imp = ImportadorDXF(ruta)
        ents = imp.extraer_geometria()
        objs = imp.extraer_objetos()
    finally:
        Path(ruta).unlink(missing_ok=True)
    return ents, objs


# =============================================================== 1. Plano
with st.sidebar:
    st.header("1. Plano")
    archivo = st.file_uploader("Sube un archivo DXF", type=["dxf"])
    if st.button("Cargar ejemplo del manual (ejercicio CEV)"):
        st.session_state["ejemplo"] = True
    if archivo is not None:
        st.session_state["ejemplo"] = False
        contenido, origen = archivo.getvalue(), archivo.name
    elif st.session_state.get("ejemplo") and RUTA_EJEMPLO.exists():
        contenido, origen = RUTA_EJEMPLO.read_bytes(), RUTA_EJEMPLO.name
    else:
        contenido, origen = None, None

if contenido is None:
    st.info("Sube un DXF o carga el ejemplo del manual para empezar. El Norte se asume hacia +Y del dibujo "
            "(se puede corregir con la rotación del Norte).")
    st.stop()

try:
    entidades, objetos = importar(contenido)
except Exception as e:
    st.error(f"No pude leer el DXF: {e}")
    st.stop()
if not objetos:
    st.error("El DXF no contiene contornos cerrados (polilíneas cerradas o líneas que formen un contorno).")
    st.stop()

plano_id = f"{origen}-{len(contenido)}"
por_id = {o["id"]: o for o in objetos}


def etiqueta(o):
    return f"{o['nombre'] or 'sin nombre'} · {o['capa']} · {o['id']}"


with st.sidebar:
    st.success(f"{origen}: {len(entidades)} entidades, {len(objetos)} contornos cerrados.")
    st.markdown("---")
    # ============================================================= 2. Vivienda y fachada
    st.header("2. Vivienda y fachada")
    por_defecto = next((i for i, o in enumerate(objetos) if "VIVIENDA" in o["capa"].upper() or "vivienda" in o["nombre"].lower()), 0)
    vivienda_id = st.selectbox("Contorno de la vivienda evaluada", [o["id"] for o in objetos], index=por_defecto,
                               format_func=lambda i: etiqueta(por_id[i]), key=f"viv_{plano_id}")
    vivienda = por_id[vivienda_id]
    rot = st.number_input("Rotación del Norte (° horario desde +Y)", value=0.0, step=1.0,
                          help="Si la flecha del Norte del plano apunta, por ejemplo, 20° a la derecha de la vertical, ingresa 20.")
    aristas = aristas_vivienda(vivienda["puntos"], rotacion_norte=rot)
    et_ar = {a["indice"]: f"Arista {a['indice']} · {nombre_orientacion(a['azimut'])} (azimut {a['azimut']:.0f}°) · {a['longitud']:.1f} m"
             for a in aristas}
    idx_norte = min(aristas, key=lambda a: min(a["azimut"], 360 - a["azimut"]))["indice"]
    calculo_360 = st.radio("Qué calcular", ["Una fachada", "Todas las fachadas (360°)"], key=f"calc_{plano_id}",
                           help="360° calcula cada fachada real de la vivienda con su propio semicírculo, centrado en el punto medio de la fachada y orientado por su normal exterior.") != "Una fachada"
    fachada = None
    if calculo_360:
        st.caption("Se usa el centro de cada arista como punto medio de su fachada.")
    else:
        modo = st.radio("Punto medio de la fachada",
                        ["Centro de la arista", "Fachada discontinua (Ecuación 5)", "Manual"], key=f"modo_{plano_id}")
        ar_a = st.selectbox("Arista de la fachada" if modo != "Fachada discontinua (Ecuación 5)" else "Arista a (plano a)",
                            [a["indice"] for a in aristas], index=[a["indice"] for a in aristas].index(idx_norte),
                            format_func=lambda i: et_ar[i], key=f"ar_{plano_id}_{vivienda_id}")
        arista_a = next(a for a in aristas if a["indice"] == ar_a)
        if modo == "Centro de la arista":
            fachada = fachada_desde_arista(arista_a, rotacion_norte=rot)
        elif modo == "Fachada discontinua (Ecuación 5)":
            paralelas = [a["indice"] for a in aristas if a["indice"] != ar_a and abs(((a["azimut_plano"] - arista_a["azimut_plano"] + 180) % 360) - 180) < 1.0]
            if not paralelas:
                st.warning("No hay otra arista paralela con la misma orientación para formar la fachada discontinua.")
                fachada = fachada_desde_arista(arista_a, rotacion_norte=rot)
            else:
                ar_b = st.selectbox("Arista b (plano b)", paralelas, format_func=lambda i: et_ar[i])
                arista_b = next(a for a in aristas if a["indice"] == ar_b)
                c1, c2 = st.columns(2)
                area_a = c1.number_input("Área a (m²)", value=float(round(arista_a["longitud"], 2)), min_value=0.01,
                                         help="Área de fachada del plano a. Por defecto, proporcional a su largo (misma altura).")
                area_b = c2.number_input("Área b (m²)", value=float(round(arista_b["longitud"], 2)), min_value=0.01)
                pm, det = punto_medio_discontinuo(arista_a, arista_b, area_a, area_b)
                fachada = fachada_desde_arista(arista_a, rotacion_norte=rot)
                fachada.punto_medio, fachada.modo_punto_medio, fachada.detalle = pm, "Ecuación 5 (fachada discontinua)", det
                st.caption(f"X = D·Área_b/(Área_a+Área_b) = {fmt(det['X'])} m (D = {fmt(abs(det['D_retranqueo']))} m)")
        else:
            c1, c2 = st.columns(2)
            px = c1.number_input("X punto medio", value=float(arista_a["punto_medio"][0]), format="%.3f")
            py = c2.number_input("Y punto medio", value=float(arista_a["punto_medio"][1]), format="%.3f")
            az_man = st.number_input("Azimut del eje ortogonal (°)", value=float(arista_a["azimut"]), min_value=0.0, max_value=360.0)
            fachada = Fachada("Fachada (manual)", (px, py), (az_man + rot) % 360, arista_a["longitud"], "manual", rotacion_norte=rot)
    h_mid = st.number_input("Altura del punto medio de la fachada (m)", value=ALTURA_PUNTO_MEDIO_DEFECTO, step=0.1, min_value=0.0,
                            help="Centro del alzado de la fachada (manual 6.8 y Fig. 33). El ejercicio del manual usa 1,5 m.")
    st.markdown("---")
    # ============================================================= 3. Obstrucciones
    st.header("3. Obstrucciones")
    st.caption("Marca cuáles cuentan y define su altura total sobre el terreno natural (se toma de capas tipo «EDIFICIO_H15»).")

filas = []
for o in objetos:
    if o["id"] == vivienda_id:
        continue
    incluir = not any(k in o["capa"].upper() for k in ("VECIN", "TEXTO", "ASSENT"))
    filas.append({"Incluir": incluir, "Nombre": o["nombre"] or o["id"], "Capa": o["capa"],
                  "Altura (m)": o["altura_capa"] if o["altura_capa"] is not None else float("nan"), "ID": o["id"]})
df_obs = pd.DataFrame(filas)
with st.sidebar:
    editado = st.data_editor(df_obs, hide_index=True, disabled=["Capa", "ID"], key=f"obs_{plano_id}_{vivienda_id}",
                             column_config={"Incluir": st.column_config.CheckboxColumn(width="small"),
                                            "Altura (m)": st.column_config.NumberColumn(min_value=0.0, step=0.5, format="%.2f")})
    with st.expander("Altura promedio de un obstáculo (manual 6.8.2)"):
        st.caption("Si la altura es variable, A usa la altura promedio = área de la obstrucción en alzado (sobre el punto medio) / longitud de su base. "
                   "Si tiene cuerpos de distintas alturas, dibuja cada cuerpo como un contorno propio o usa el promedio ponderado por área.")
        a1, a2 = st.columns(2)
        ar_alz = a1.number_input("Área en alzado (m²)", value=0.0, min_value=0.0)
        lb = a2.number_input("Longitud de la base (m)", value=0.0, min_value=0.0)
        if lb > 0:
            st.write(f"Altura promedio sobre el punto medio: **{fmt(ar_alz / lb)} m** → súmale la altura del punto medio para obtener la altura total.")
    st.markdown("---")
    st.header("4. Criterio de desestimación")
    crit_txt = st.selectbox("Obstrucciones desestimables (6.8)", list(CRITERIOS), index=0,
                            help="El manual dice que se «pueden desestimar» cuando B/D < 0,1 y/o B/A < 0,1. Leído literalmente suena invertido "
                                 "(una obstrucción pegada y alta no es despreciable); por eso se ofrece también la lectura inversa y, por defecto, solo se informan los cocientes.")
    criterio = CRITERIOS[crit_txt]
    st.warning("⚠️ **FAR final bloqueado**: el manual no trae la ecuación. Aquí solo se calculan división, A, B y D.")

# =============================================================== Cálculo
obstrucciones, avisos = [], []
for _, r in editado.iterrows():
    if not r["Incluir"]:
        continue
    if pd.isna(r["Altura (m)"]):
        avisos.append(f"«{r['Nombre']}» no tiene altura definida: no se calculó. Ingrésala en la tabla de obstrucciones.")
        continue
    o = por_id[r["ID"]]
    obstrucciones.append(Obstruccion(o["id"], str(r["Nombre"]), o["capa"], o["puntos"], float(r["Altura (m)"])))
fachadas = fachadas_de_vivienda(vivienda["puntos"], rot) if calculo_360 else [fachada]
resultados = [calcular_fachada(f, obstrucciones, altura_punto_medio=h_mid, criterio_desestimacion=criterio) for f in fachadas]
avisos += [a for r in resultados[:1] for a in r.advertencias]

inc_ids = {ob.id for ob in obstrucciones}
objs_dibujo = []
for o in objetos:
    rol = "vivienda" if o["id"] == vivienda_id else ("obstruccion" if o["id"] in inc_ids else "excluido")
    alt = next((ob.altura for ob in obstrucciones if ob.id == o["id"]), None)
    objs_dibujo.append({"id": o["id"], "nombre": o["nombre"], "puntos": o["puntos"], "rol": rol, "altura": alt})

for a in avisos:
    st.warning(a)
if calculo_360 and not fachadas:
    st.error("La vivienda no tiene aristas utilizables como fachada.")
    st.stop()

titulos = ["📋 Resumen y exportar"] + [f"{f.orientacion} {f.azimut_real:.0f}°" if not calculo_360 else f"{f.nombre} ({f.azimut_real:.0f}°)" for f in fachadas]
tabs = st.tabs(titulos)
excluidos_por_fachada: dict[str, set] = {}


def tabla_tramos(res):
    return [{
        "División": t.division, "Obstrucción": t.nombre, "Altura obst. (m)": round(t.altura_obstruccion, 2),
        "A (m)": round(t.A, 2), "B (m)": round(t.B, 2), "D (m)": round(t.D, 2), "Elevación (°)": round(t.angulo_elevacion, 1),
        "B/D": None if t.D < 1e-9 else round(t.B_sobre_D, 2), "B/A": round(t.B_sobre_A, 1),
        "Estado": t.estado, "Notas": " ".join(t.notas), "_id": t.obstruccion_id} for t in res.tramos]


# ------------------------------------------------------ una pestaña por fachada
for k_f, (res, tab) in enumerate(zip(resultados, tabs[1:])):
    f = res.fachada
    with tab:
        st.subheader(f"{f.nombre} · {f.orientacion} · azimut del eje ortogonal {f.azimut_real:.0f}°")
        c1, c2, c3 = st.columns([2.2, 1.2, 2.0])
        paso = c1.radio("Lámina del ejercicio", [1, 2, 3], index=2, horizontal=True, key=f"paso_{k_f}",
                        format_func=lambda p: {1: "Paso 1 · Trazar divisiones", 2: "Paso 2 · Identificar divisiones", 3: "Paso 3 · Obstrucciones, B, D y A"}[p])
        foco = c2.selectbox("División", [0, 1, 2, 3, 4, 5], key=f"foco_{k_f}", format_func=lambda k: "Todas" if k == 0 else f"División {k}")
        ajustar = c3.checkbox("Ajustar vista al semicírculo", value=True, key=f"ajuste_{k_f}")
        recuadros = c3.checkbox("Recuadros por división", value=True, key=f"recuadros_{k_f}",
                                help="Apágalos si tapan obstrucciones; los mismos datos están en la tabla de abajo.")
        fig = figura_far(entidades, objs_dibujo, res, paso=paso, division_foco=foco or None, ajustar_vista=ajustar,
                         mostrar_recuadros=recuadros)
        mostrar(fig, config={"displayModeBar": True, "scrollZoom": True,
                             "toImageButtonOptions": {"format": "png", "filename": f"FAR_{f.nombre}", "scale": 2}}, key=f"fig_{k_f}")
        st.caption("Semicírculo con base en el punto medio de la fachada y orientado por su eje ortogonal (fijo para todas las obstrucciones). "
                   "Divisiones numeradas de izquierda a derecha para un observador dentro de la vivienda.")

        filas_res = tabla_tramos(res)
        st.markdown("**Parámetros por obstrucción y división** (manual 11.8)")
        if filas_res:
            mostrar(pd.DataFrame(filas_res).drop(columns="_id"), hide_index=True)
            etq = {f"Div {r['División']} · {r['Obstrucción']}": (r["División"], r["_id"]) for r in filas_res}
            por_def = [k for k, r in zip(etq, filas_res) if r["Estado"] == "desestimable"]
            excl = st.multiselect("Tramos que el evaluador decide excluir de la CEV", list(etq), default=por_def, key=f"excl_{k_f}")
            excluidos_por_fachada[f.nombre] = {etq[k] for k in excl}
        else:
            st.info("Ninguna obstrucción supera la altura del punto medio dentro del semicírculo de esta fachada.")
        if res.omitidas:
            st.markdown("**Obstrucciones omitidas** (no se ingresan a la CEV)")
            mostrar(pd.DataFrame([{"Obstrucción": o["nombre"], "División": o["division"] or "—", "Motivo": o["motivo"]} for o in res.omitidas]), hide_index=True)
        sin = [k for k in range(1, 6) if not any(t.division == k for t in res.tramos)]
        if sin:
            st.caption("Divisiones sin obstrucciones: " + ", ".join(str(k) for k in sin) + " (se informan como «no hay obstrucciones»).")

# ------------------------------------------------------ resumen y exportación
with tabs[0]:
    cev = pd.DataFrame([{
        "Orientación": r.fachada.orientacion, "Fachada": r.fachada.nombre, "Azimut (°)": round(r.fachada.azimut_real, 1),
        "División": t.division, "Obstrucción": t.nombre, "A (m)": round(t.A, 2), "B (m)": round(t.B, 2), "D (m)": round(t.D, 2)}
        for r in resultados for t in r.tramos
        if (t.division, t.obstruccion_id) not in excluidos_por_fachada.get(r.fachada.nombre, set())])
    st.markdown("**Datos a ingresar en la CEV (sección 11.8): orientación, azimut, división, A, B y D por obstrucción**")
    if cev.empty:
        st.info("No hay obstrucciones que informar con los parámetros actuales.")
    else:
        mostrar(cev, hide_index=True)
        st.download_button("📥 Descargar CSV", cev.to_csv(index=False).encode("utf-8-sig"), file_name="far_resumen.csv", mime="text/csv")
    datos = a_dict_multiple(resultados, vivienda_id, excluidos_por_fachada, origen)
    st.download_button("📥 Descargar JSON (trazabilidad)", json.dumps(datos, indent=2, ensure_ascii=False),
                       file_name="far_resultados.json", mime="application/json")
    with st.expander("📖 Reglas del manual aplicadas"):
        st.markdown("""
- **Centro de la fachada**: punto medio del ancho; con retranqueos, Ecuación 5 `X = D·Área_b/(Área_a+Área_b)`.
- **Semicírculo y divisiones**: base en el centro de la fachada, 5 divisiones de 36° numeradas de izquierda a derecha (observador dentro de la vivienda); el eje es la normal exterior de la fachada.
- **Obstrucción en varias divisiones**: se trata por separado en cada una (B, D y A propios).
- **A** = altura del obstáculo − altura del punto medio de la fachada (altura promedio si es variable).
- **B** = distancia del punto medio de la fachada al punto medio de la parte visible de la obstrucción en esa división (sobre la cara visible, ponderada por su sombra).
- **D** = ancho del bloqueo solar: cuerda perpendicular a B, por el punto donde termina B, dentro del cono de visión.
- **Sobrepuestas**: en la sección sobrepuesta prevalece la de mayor ángulo respecto a la horizontal del punto medio, `atan(A/B)` a lo largo de cada visual; la otra se omite.
- **Desestimar**: opcional, según el criterio elegido en la barra lateral.
- **Sin ecuación final**: el factor FAR no se calcula.
""")

import json
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from core.alzado import altura_promedio, centro_alzado, figura_altura_promedio, figura_alzado
from core.dibujo import figura_far
from core.exportar import a_dict_multiple
from core.far import (ALTURA_PUNTO_MEDIO_DEFECTO, Fachada, Obstruccion, aristas_vivienda, calcular_fachada,
                      fachada_desde_arista, fachadas_de_vivienda, nombre_orientacion, punto_medio_discontinuo)
from core.importador import ImportadorDXF
from core.reglas import VERSION_REGLAS
from core.seleccion import actualizar_seleccion, figura_seleccion, ids_desde_evento

st.set_page_config(page_title="FARcilito - CEV", layout="wide")
st.title("🏠 FARcilito")
st.caption(f"Parámetros del FAR (A, B, D por división) · Manual CEV 2025, secc. 6.8 y 11.8 · Reglas: {VERSION_REGLAS}")

ss = st.session_state
RUTA_EJEMPLO = Path(__file__).parent / "data" / "ejemplo_manual.dxf"
CRITERIOS = {
    "No desestimar (solo informar los cocientes)": "ninguno",
    "Literal del manual: B/D < 0,1 o B/A < 0,1": "literal",
    "Invertido: D/B < 0,1 o A/B < 0,1": "invertido",
}
NAN = float("nan")


def fmt(x, nd=2):
    return f"{x:.{nd}f}".replace(".", ",")


def mostrar(obj, **kw):
    """st.plotly_chart / st.dataframe compatibles con versiones nuevas y antiguas de Streamlit."""
    fn = st.plotly_chart if hasattr(obj, "to_plotly_json") else st.dataframe
    try:
        return fn(obj, width="stretch", **kw)
    except TypeError:
        return fn(obj, use_container_width=True, **kw)


def grafico_clic(fig, key):
    """Gráfico que devuelve los puntos clicados (Streamlit >= 1.35)."""
    kw = dict(key=key, on_select="rerun", selection_mode="points",
              config={"displayModeBar": True, "scrollZoom": True})
    try:
        return st.plotly_chart(fig, width="stretch", **kw)
    except TypeError:
        try:
            return st.plotly_chart(fig, use_container_width=True, **kw)
        except TypeError:
            st.plotly_chart(fig, use_container_width=True, key=key)
            st.warning("Tu versión de Streamlit no permite elegir con clic (requiere 1.35 o superior). Usa las listas de abajo.")
            return None


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
        ss["ejemplo"] = True
    if archivo is not None:
        ss["ejemplo"] = False
        contenido, origen = archivo.getvalue(), archivo.name
    elif ss.get("ejemplo") and RUTA_EJEMPLO.exists():
        contenido, origen = RUTA_EJEMPLO.read_bytes(), RUTA_EJEMPLO.name
    else:
        contenido, origen = None, None

if contenido is None:
    st.info("Sube un DXF o carga el ejemplo del manual para empezar. El Norte se asume hacia +Y del dibujo "
            "(se puede corregir con la rotación del Norte). Después eliges la vivienda, las obstrucciones y la fachada haciendo clic en el plano.")
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


def _excluido_por_defecto(o):
    return any(k in o["capa"].upper() for k in ("VECIN", "TEXTO", "ASSENT"))


# ---- estado de la selección (se reinicia al cambiar de plano)
if ss.get("plano_id") != plano_id:
    viv0 = next((o["id"] for o in objetos if "VIVIENDA" in o["capa"].upper() or "vivienda" in o["nombre"].lower()), objetos[0]["id"])
    ss.plano_id = plano_id
    ss.vivienda_id = viv0
    ss.obs_ids = [o["id"] for o in objetos if o["id"] != viv0 and not _excluido_por_defecto(o)]
    ss.datos_obs = {}
    ss.arista = None
    ss.h_mid_fachada = {}
    ss.mapa_v = 0
    ss.alz_incl = None
    ss.alz_v = 0


def dato(oid):
    """Nombre, altura del edificio y cota del terreno al pie de cada obstrucción (persisten al cambiar la selección)."""
    if oid not in ss.datos_obs:
        o = por_id[oid]
        ss.datos_obs[oid] = {"nombre": o["nombre"] or o["id"],
                             "altura": o["altura_capa"] if o["altura_capa"] is not None else NAN, "cota": 0.0}
    return ss.datos_obs[oid]


def etiqueta(o):
    return f"{o['nombre'] or 'sin nombre'} · {o['capa']} · {o['id']}"


vivienda = por_id[ss.vivienda_id]

# =============================================================== 2. Fachada (barra lateral)
with st.sidebar:
    st.success(f"{origen}: {len(entidades)} entidades, {len(objetos)} contornos cerrados.")
    st.caption(f"Vivienda: **{vivienda['nombre'] or vivienda['id']}** · Obstrucciones: **{len(ss.obs_ids)}** "
               "(se eligen con clic en la pestaña «Plano y selección»).")
    st.markdown("---")
    st.header("2. Fachada y terreno")
    rot = st.number_input("Rotación del Norte (° horario desde +Y)", value=0.0, step=1.0,
                          help="Si la flecha del Norte del plano apunta, por ejemplo, 20° a la derecha de la vertical, ingresa 20.")
    aristas = aristas_vivienda(vivienda["puntos"], rotacion_norte=rot)
    idx_validos = [a["indice"] for a in aristas]
    if ss.arista not in idx_validos:
        ss.arista = min(aristas, key=lambda a: min(a["azimut"], 360 - a["azimut"]))["indice"]
    et_ar = {a["indice"]: f"Arista {a['indice']} · {nombre_orientacion(a['azimut'])} (azimut {a['azimut']:.0f}°) · {a['longitud']:.1f} m"
             for a in aristas}
    calculo_360 = st.radio("Qué calcular", ["Una fachada", "Todas las fachadas (360°)"], key=f"calc_{plano_id}",
                           help="360° calcula cada fachada real de la vivienda con su propio semicírculo, centrado en el punto medio de la fachada y orientado por su normal exterior.") != "Una fachada"
    fachada = None
    arista_a = next(a for a in aristas if a["indice"] == ss.arista)
    if calculo_360:
        st.caption("Se usa el centro de cada arista como punto medio de su fachada.")
    else:
        modo = st.radio("Punto medio de la fachada", ["Centro de la arista", "Fachada discontinua (Ecuación 5)", "Manual"], key=f"modo_{plano_id}")
        ar_sel = st.selectbox("Arista de la fachada" if modo != "Fachada discontinua (Ecuación 5)" else "Arista a (plano a)",
                              idx_validos, index=idx_validos.index(ss.arista), format_func=lambda i: et_ar[i],
                              key=f"ar_{plano_id}_{ss.vivienda_id}_{ss.arista}",
                              help="También puedes elegirla con clic en el plano (modo «Fachada»).")
        if ar_sel != ss.arista:
            ss.arista = ar_sel
            arista_a = next(a for a in aristas if a["indice"] == ar_sel)
        if modo == "Centro de la arista":
            fachada = fachada_desde_arista(arista_a, rotacion_norte=rot)
        elif modo == "Fachada discontinua (Ecuación 5)":
            paralelas = [a["indice"] for a in aristas if a["indice"] != arista_a["indice"]
                         and abs(((a["azimut_plano"] - arista_a["azimut_plano"] + 180) % 360) - 180) < 1.0]
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
        fachada.detalle = {**(fachada.detalle or {}), "arista": arista_a["indice"]}
    cota_f = st.number_input("Cota del terreno en la fachada (m)", value=0.0, step=0.1,
                             help="Nivel del terreno natural al pie de la fachada. Si el terreno es plano déjalo en 0 y usa cotas relativas.")
    h_def = st.number_input("Altura del punto medio sobre ese terreno (m)", value=ALTURA_PUNTO_MEDIO_DEFECTO, step=0.1, min_value=0.0,
                            help="Centro del alzado de la fachada (manual 6.8, Fig. 33). El ejercicio del manual usa 1,5 m. "
                                 "Para fachadas irregulares, calcúlalo en la pestaña «Alzado e irregulares».")
    st.markdown("---")
    st.header("3. Criterio de desestimación")
    crit_txt = st.selectbox("Obstrucciones desestimables (6.8)", list(CRITERIOS), index=0,
                            help="El manual dice que se «pueden desestimar» cuando B/D < 0,1 y/o B/A < 0,1. Leído literalmente suena invertido "
                                 "(una obstrucción pegada y alta no es despreciable); por eso se ofrece también la lectura inversa y, por defecto, solo se informan los cocientes.")
    criterio = CRITERIOS[crit_txt]
    st.warning("⚠️ **FAR final bloqueado**: el manual no trae la ecuación. Aquí solo se calculan división, A, B y D.")

fachadas = fachadas_de_vivienda(vivienda["puntos"], rot) if calculo_360 else [fachada]


def clave_fachada(f):
    return f"{ss.vivienda_id}:{f.detalle.get('arista', '?')}"


def h_sobre_terreno(f):
    return ss.h_mid_fachada.get(clave_fachada(f), h_def)


def cota_punto_medio(f):
    return cota_f + h_sobre_terreno(f)


# =============================================================== pestañas
titulos = ["🖱️ Plano y selección", "📐 Alzado e irregulares", "📋 Resumen y exportar"] + \
          [(f"{f.orientacion} {f.azimut_real:.0f}°" if not calculo_360 else f"{f.nombre} ({f.azimut_real:.0f}°)") for f in fachadas]
tabs = st.tabs(titulos)

# ------------------------------------------------------------ plano y selección
with tabs[0]:
    c1, c2 = st.columns([3, 1.3])
    with c2:
        modo_clic = st.radio("Con cada clic eliges…", ["Vivienda evaluada", "Obstrucciones", "Fachada (arista)"],
                             index=1,
                             help="Vivienda: el clic define cuál es la vivienda. Obstrucciones: cada clic agrega o quita un contorno. "
                                  "Fachada: clic en un rombo del centro de una arista de la vivienda.")
        modo_key = {"Vivienda evaluada": "vivienda", "Obstrucciones": "obstruccion", "Fachada (arista)": "fachada"}[modo_clic]
        b1, b2 = st.columns(2)
        if b1.button("Todas"):
            ss.obs_ids = [o["id"] for o in objetos if o["id"] != ss.vivienda_id]
            ss.mapa_v += 1
            st.rerun()
        if b2.button("Ninguna"):
            ss.obs_ids = []
            ss.mapa_v += 1
            st.rerun()
        st.caption("Azul = vivienda · rojo = obstrucción · gris = no usado · rombo naranja = fachada elegida.")
        with st.expander("Elegir con listas (alternativa)"):
            ids = [o["id"] for o in objetos]
            v_new = st.selectbox("Vivienda", ids, index=ids.index(ss.vivienda_id), format_func=lambda i: etiqueta(por_id[i]),
                                 key=f"lv_{ss.mapa_v}")
            o_new = st.multiselect("Obstrucciones", [i for i in ids if i != v_new], default=[i for i in ss.obs_ids if i != v_new],
                                   format_func=lambda i: etiqueta(por_id[i]), key=f"lo_{ss.mapa_v}")
            if v_new != ss.vivienda_id or o_new != ss.obs_ids:
                ss.vivienda_id, ss.obs_ids = v_new, o_new
                ss.mapa_v += 1
                st.rerun()
    with c1:
        objs_sel = [{"id": o["id"], "nombre": dato(o["id"])["nombre"] if o["id"] != ss.vivienda_id else (o["nombre"] or "Vivienda"),
                     "puntos": o["puntos"], "capa": o["capa"]} for o in objetos]
        fig_sel = figura_seleccion(entidades, objs_sel, ss.vivienda_id, ss.obs_ids, aristas=aristas, arista_sel=ss.arista,
                                   titulo=f"Modo: {modo_clic}")
        evento = grafico_clic(fig_sel, key=f"mapa_{plano_id}_{ss.mapa_v}")
    clics = ids_desde_evento(evento)
    if clics:
        ss.vivienda_id, ss.obs_ids, ss.arista = actualizar_seleccion(modo_key, clics, ss.vivienda_id, ss.obs_ids, ss.arista)
        ss.mapa_v += 1
        st.rerun()

    st.markdown("#### Altura de cada obstrucción y terreno en su punto")
    st.caption("Altura del edificio = desde su propio terreno hasta el techo (o altura promedio si es irregular). "
               "Cota del terreno = nivel del suelo al pie del edificio, con la misma referencia que la cota del terreno en la fachada. "
               "A = (cota del terreno + altura del edificio) − cota del punto medio de la fachada.")
    if ss.obs_ids:
        df_obs = pd.DataFrame([{"Nombre": dato(i)["nombre"], "Capa": por_id[i]["capa"], "Altura edificio (m)": dato(i)["altura"],
                                "Cota terreno al pie (m)": dato(i)["cota"], "ID": i} for i in ss.obs_ids])
        editado = st.data_editor(df_obs, hide_index=True, disabled=["Capa", "ID"],
                                 key=f"tabla_{plano_id}_{abs(hash(tuple(ss.obs_ids)))}",
                                 column_config={"Altura edificio (m)": st.column_config.NumberColumn(min_value=0.0, step=0.5, format="%.2f"),
                                                "Cota terreno al pie (m)": st.column_config.NumberColumn(step=0.1, format="%.2f")})
        for _, r in editado.iterrows():
            d = dato(r["ID"])
            d["nombre"], d["altura"] = str(r["Nombre"]), r["Altura edificio (m)"]
            d["cota"] = 0.0 if pd.isna(r["Cota terreno al pie (m)"]) else float(r["Cota terreno al pie (m)"])
        ref = cota_f + h_def
        filas_dif = []
        for i in ss.obs_ids:
            d = dato(i)
            techo = None if pd.isna(d["altura"]) else d["cota"] + d["altura"]
            filas_dif.append({"Obstrucción": d["nombre"], "Cota del techo (m)": None if techo is None else round(techo, 2),
                              "Cota punto medio fachada (m)": round(ref, 2),
                              "Diferencia A (m)": None if techo is None else round(techo - ref, 2),
                              "Estado": "sin altura" if techo is None else ("no obstruye (A ≤ 0)" if techo - ref <= 0 else "obstruye")})
        st.markdown("**Diferencia de altura frente al punto medio** (con el punto medio por defecto; una fachada irregular puede tener otro valor)")
        mostrar(pd.DataFrame(filas_dif), hide_index=True)
    else:
        st.info("Aún no hay obstrucciones elegidas. Pon el modo en «Obstrucciones» y haz clic sobre los contornos.")

# ------------------------------------------------------------------- cálculo
obstrucciones, avisos = [], []
for i in ss.obs_ids:
    d, o = dato(i), por_id[i]
    if pd.isna(d["altura"]):
        avisos.append(f"«{d['nombre']}» no tiene altura definida: no se calculó. Ingrésala en la tabla de la pestaña «Plano y selección».")
        continue
    obstrucciones.append(Obstruccion(i, d["nombre"], o["capa"], o["puntos"], altura=d["cota"] + d["altura"],
                                     altura_propia=d["altura"], cota_terreno=d["cota"]))
resultados = [calcular_fachada(f, obstrucciones, altura_punto_medio=cota_punto_medio(f), criterio_desestimacion=criterio) for f in fachadas]
avisos += [a for r in resultados[:1] for a in r.advertencias]

inc_ids = {ob.id for ob in obstrucciones}
objs_dibujo = []
for o in objetos:
    rol = "vivienda" if o["id"] == ss.vivienda_id else ("obstruccion" if o["id"] in inc_ids else "excluido")
    alt = next((ob.altura_propia for ob in obstrucciones if ob.id == o["id"]), None)
    nombre = o["nombre"] if rol == "vivienda" or o["id"] not in ss.datos_obs else ss.datos_obs[o["id"]]["nombre"]
    objs_dibujo.append({"id": o["id"], "nombre": nombre, "puntos": o["puntos"], "rol": rol, "altura": alt})

if not fachadas:
    st.error("La vivienda no tiene aristas utilizables como fachada.")
    st.stop()
for a in avisos:
    st.warning(a)

excluidos_por_fachada: dict[str, set] = {}


def tabla_tramos(res):
    return [{
        "División": t.division, "Obstrucción": t.nombre,
        "Altura edificio (m)": None if t.altura_propia is None else round(t.altura_propia, 2),
        "Cota terreno (m)": round(t.cota_terreno, 2), "Cota techo (m)": round(t.altura_obstruccion, 2),
        "A (m)": round(t.A, 2), "B (m)": round(t.B, 2), "D (m)": round(t.D, 2), "Elevación (°)": round(t.angulo_elevacion, 1),
        "B/D": None if t.D < 1e-9 else round(t.B_sobre_D, 2), "B/A": round(t.B_sobre_A, 1),
        "Estado": t.estado, "Notas": " ".join(t.notas), "_id": t.obstruccion_id} for t in res.tramos]


# ------------------------------------------------------ una pestaña por fachada
for k_f, (res, tab) in enumerate(zip(resultados, tabs[3:])):
    f = res.fachada
    with tab:
        st.subheader(f"{f.nombre} · {f.orientacion} · azimut del eje ortogonal {f.azimut_real:.0f}°")
        st.caption(f"Punto medio a cota {fmt(res.altura_punto_medio)} m "
                   f"({fmt(h_sobre_terreno(f))} m sobre el terreno, "
                   f"{'definida en «Alzado e irregulares»' if clave_fachada(f) in ss.h_mid_fachada else 'valor por defecto'}).")
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
with tabs[2]:
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
    datos = a_dict_multiple(resultados, ss.vivienda_id, excluidos_por_fachada, origen)
    st.download_button("📥 Descargar JSON (trazabilidad)", json.dumps(datos, indent=2, ensure_ascii=False),
                       file_name="far_resultados.json", mime="application/json")
    with st.expander("📖 Reglas del manual aplicadas"):
        st.markdown("""
- **Centro de la fachada**: punto medio del ancho; con retranqueos, Ecuación 5 `X = D·Área_b/(Área_a+Área_b)`. En alzado, centro del paralelepípedo que inscribe el área de la fachada (pestaña «Alzado e irregulares»).
- **Semicírculo y divisiones**: base en el centro de la fachada, 5 divisiones de 36° numeradas de izquierda a derecha (observador dentro de la vivienda); el eje es la normal exterior de la fachada.
- **Obstrucción en varias divisiones**: se trata por separado en cada una (B, D y A propios).
- **A** = cota del techo del obstáculo − cota del punto medio de la fachada (altura promedio si es variable). Cota = cota del terreno + altura sobre ese terreno.
- **B** = distancia del punto medio de la fachada al punto medio de la parte visible de la obstrucción en esa división (sobre la cara visible, ponderada por su sombra).
- **D** = ancho del bloqueo solar: cuerda perpendicular a B, por el punto donde termina B, dentro del cono de visión.
- **Sobrepuestas**: en la sección sobrepuesta prevalece la de mayor ángulo respecto a la horizontal del punto medio, `atan(A/B)` a lo largo de cada visual; la otra se omite.
- **Desestimar**: opcional, según el criterio elegido en la barra lateral.
- **Sin ecuación final**: el factor FAR no se calcula.
""")

# ------------------------------------------------------ alzado e irregulares
EJEMPLO_CUERPOS = pd.DataFrame({
    "Cuerpo": ["Planta baja"] * 4 + ["Segundo piso"] * 4,
    "x (m)": [0.0, 8.0, 8.0, 0.0, 2.0, 6.0, 6.0, 2.0],
    "z (m)": [0.0, 0.0, 2.4, 2.4, 2.4, 2.4, 5.0, 5.0]})
EJEMPLO_OBSTACULO = pd.DataFrame({"x (m)": [0.0, 10.0, 10.0, 5.0, 0.0], "z (m)": [0.0, 0.0, 6.0, 9.0, 6.0]})

with tabs[1]:
    st.markdown("### 1 · Centro de una fachada irregular (manual 6.8, Fig. 30 y 33)")
    st.caption("Si la fachada tiene retranqueos, cielos inclinados o alturas dobles, se inscribe su área en un paralelepípedo (rectángulo en alzado) "
               "y se asume su centro como centro de la fachada. Se omiten elementos que no interrumpen el acondicionamiento térmico "
               "y muros con altura interior ≤ 1,6 m. El centro del ancho es la mitad del ancho.")
    i_f = st.selectbox("Fachada", range(len(fachadas)), format_func=lambda i: f"{fachadas[i].nombre} ({fachadas[i].azimut_real:.0f}°)")
    fa = fachadas[i_f]
    ck = clave_fachada(fa)
    st.info(f"Altura del punto medio vigente: **{fmt(h_sobre_terreno(fa))} m** sobre el terreno "
            f"({'definida aquí' if ck in ss.h_mid_fachada else 'valor por defecto de la barra lateral'}).")
    how = st.radio("Cómo definir el alzado", ["Regular (solo la altura)", "Irregular: ingresar cuerpos", "Irregular: desde un DXF de alzado"], horizontal=True)
    nuevo = None
    if how == "Regular (solo la altura)":
        H = st.number_input("Altura de la fachada (m)", value=float(2 * h_def) if h_def > 0 else 2.5, min_value=0.1, step=0.1)
        nuevo = H / 2
        ancho = fa.longitud or 8.0
        cuerpos = {"Fachada": [(0, 0), (ancho, 0), (ancho, H), (0, H)]}
        mostrar(figura_alzado(cuerpos, set(), centro_alzado(cuerpos), "Alzado regular: el centro está a la mitad de la altura"))
    elif how == "Irregular: ingresar cuerpos":
        st.caption("Ingresa los vértices de cada cuerpo del alzado (x = ancho, z = altura sobre el terreno). Cada cuerpo es un polígono. "
                   "Puedes subir una imagen del alzado como referencia para tenerla al lado.")
        cA, cB = st.columns([1.1, 1])
        with cB:
            img = st.file_uploader("Imagen del alzado (opcional, solo referencia)", type=["png", "jpg", "jpeg"], key="img_alzado")
            if img is not None:
                st.image(img, caption="Alzado de referencia")
        with cA:
            df_c = st.data_editor(EJEMPLO_CUERPOS, num_rows="dynamic", hide_index=True, key="cuerpos_alzado")
        cuerpos = {}
        for nombre, g in df_c.dropna().groupby("Cuerpo", sort=False):
            cuerpos[str(nombre)] = list(zip(g["x (m)"].astype(float), g["z (m)"].astype(float)))
        omitir = set(st.multiselect("Cuerpos a omitir (muros ≤ 1,6 m interior o que no interrumpen el acondicionamiento)", list(cuerpos)))
        centro = centro_alzado(cuerpos, omitir)
        if centro:
            nuevo = centro["z_centro"]
            mostrar(figura_alzado(cuerpos, omitir, centro))
            m1, m2, m3 = st.columns(3)
            m1.metric("Ancho inscrito", f"{fmt(centro['ancho'])} m")
            m2.metric("Alto inscrito", f"{fmt(centro['alto'])} m")
            m3.metric("Centro del alzado", f"z = {fmt(centro['z_centro'])} m")
        else:
            st.info("Ingresa al menos un cuerpo con 3 vértices.")
    else:
        up = st.file_uploader("DXF del alzado (x = ancho, y = altura)", type=["dxf"], key="dxf_alzado")
        if up is None:
            st.info("Sube un DXF con el alzado de la fachada dibujado como contornos cerrados (un contorno por cuerpo).")
        else:
            try:
                ents_a, objs_a = importar(up.getvalue())
            except Exception as e:
                objs_a = []
                st.error(f"No pude leer el DXF del alzado: {e}")
            if objs_a:
                if ss.alz_incl is None or any(i not in {o["id"] for o in objs_a} for i in ss.alz_incl):
                    ss.alz_incl = [o["id"] for o in objs_a]
                ys = [p[1] for o in objs_a for p in o["puntos"]]
                z0 = st.number_input("Nivel del terreno en el dibujo (valor Y)", value=float(min(ys)), step=0.1)
                st.caption("Haz clic en un contorno para incluirlo o excluirlo del paralelepípedo (rojo = incluido).")
                oa = [{"id": o["id"], "nombre": o["nombre"] or o["id"], "puntos": o["puntos"], "capa": o["capa"]} for o in objs_a]
                ev = grafico_clic(figura_seleccion(ents_a, oa, None, ss.alz_incl, titulo="Alzado: clic para incluir/excluir", altura=420),
                                  key=f"alz_{ss.alz_v}")
                cl = ids_desde_evento(ev)
                if cl:
                    _, ss.alz_incl, _ = actualizar_seleccion("obstruccion", cl, None, ss.alz_incl)
                    ss.alz_v += 1
                    st.rerun()
                cuerpos = {o["id"]: [(p[0], p[1] - z0) for p in o["puntos"]] for o in objs_a}
                omitir = {o["id"] for o in objs_a if o["id"] not in ss.alz_incl}
                centro = centro_alzado(cuerpos, omitir)
                if centro:
                    nuevo = centro["z_centro"]
                    mostrar(figura_alzado(cuerpos, omitir, centro))
                    st.metric("Centro del alzado", f"z = {fmt(centro['z_centro'])} m sobre el terreno")
    if nuevo is not None:
        b1, b2 = st.columns(2)
        if b1.button(f"Usar {fmt(nuevo)} m como altura del punto medio de «{fa.nombre}»", type="primary"):
            ss.h_mid_fachada[ck] = float(nuevo)
            st.rerun()
        if ck in ss.h_mid_fachada and b2.button("Volver al valor por defecto"):
            ss.h_mid_fachada.pop(ck, None)
            st.rerun()

    st.markdown("---")
    st.markdown("### 2 · Altura promedio de un obstáculo irregular (manual 6.8.2, Fig. 36 y 37)")
    st.caption("Si la altura del obstáculo es variable se usa la altura promedio: área de la obstrucción en alzado SOBRE el punto medio de la fachada "
               "dividida por la longitud de su base. Si tiene cuerpos de alturas distintas, también puedes ingresarlos como obstrucciones separadas.")
    if not ss.obs_ids:
        st.info("Primero elige al menos una obstrucción en «Plano y selección».")
    else:
        nombres_obs = {i: dato(i)["nombre"] for i in ss.obs_ids}
        oid = st.selectbox("Obstrucción", ss.obs_ids, format_func=lambda i: nombres_obs.get(i, i),
                           key=f"obs_prom_{abs(hash(tuple(ss.obs_ids)))}")
        z_m_rel = cota_punto_medio(fa) - dato(oid)["cota"]
        st.caption(f"Plano del punto medio de «{fa.nombre}»: {fmt(z_m_rel)} m sobre el terreno de esta obstrucción.")
        cA, cB = st.columns([1, 1.5])
        with cA:
            df_o = st.data_editor(EJEMPLO_OBSTACULO, num_rows="dynamic", hide_index=True, key=f"obst_alzado_{oid}")
            base_man = st.number_input("Longitud de la base (m) · 0 = automática", value=0.0, min_value=0.0, step=0.5,
                                       help="Largo del área de la obstrucción en la división analizada (Fig. 37). Si lo dejas en 0 se usa el ancho de la parte que queda sobre el punto medio.")
        d_o = df_o.dropna()
        poly = list(zip(d_o["x (m)"].astype(float), d_o["z (m)"].astype(float)))
        info = altura_promedio(poly, z_m_rel, base_man or None)
        with cB:
            if info:
                mostrar(figura_altura_promedio(poly, z_m_rel, info))
        if info and info["area_sobre"] > 0:
            total_sobre_terreno = z_m_rel + info["A_promedio"]
            m1, m2, m3 = st.columns(3)
            m1.metric("Área sobre el punto medio", f"{fmt(info['area_sobre'])} m²")
            m2.metric("A promedio", f"{fmt(info['A_promedio'])} m")
            m3.metric("Altura equivalente del edificio", f"{fmt(total_sobre_terreno)} m")
            if st.button("Aplicar como altura del edificio", key="aplicar_prom"):
                ss.datos_obs[oid]["altura"] = float(total_sobre_terreno)
                st.rerun()
        elif info:
            st.info("El obstáculo no sobrepasa el punto medio de la fachada: no obstruye.")

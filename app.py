import streamlit as st
import plotly.graph_objects as go
from core.importador import ImportadorDXF
from core.reglas import ReglasFAR, VERSION_REGLAS
import json

st.set_page_config(page_title="FARcilito - CEV", layout="wide")
st.title("🏠 FARcilito")
st.caption(f"Herramienta Asistida FAR - CEV | Reglas: {VERSION_REGLAS}")

with st.sidebar:
    st.header("1. Importar Geometría")
    archivo_dxf = st.file_uploader("Sube un archivo DXF", type=["dxf"])
    
    if archivo_dxf is not None:
        with open("temp.dxf", "wb") as f:
            f.write(archivo_dxf.getbuffer())
        
        try:
            importador = ImportadorDXF("temp.dxf")
            entidades = importador.extraer_geometria()
            st.success(f"DXF cargado: {len(entidades)} entidades.")
            st.session_state['entidades'] = entidades
            if 'resultado_abd' in st.session_state:
                del st.session_state['resultado_abd']
        except Exception as e:
            st.error(f"Error al leer DXF: {e}")

    st.markdown("---")
    st.warning("⚠️ **Cálculo FAR Bloqueado** hasta validar ecuación con MINVU.")

if 'entidades' in st.session_state:
    entidades = st.session_state['entidades']
    
    if 'resultado_abd' not in st.session_state:
        st.session_state['resultado_abd'] = None

    col1, col2 = st.columns([2, 1])
    
    # --- COLUMNA IZQUIERDA: VISOR GRÁFICO ---
    with col1:
        st.subheader("Visor Geométrico (DXF)")
        fig = go.Figure()
        
        # Agrupar líneas por capa (Optimización)
        capas = {}
        for ent in entidades:
            capa = ent['capa']
            if capa not in capas:
                capas[capa] = {'x': [], 'y': []}
            
            x_vals = [p[0] for p in ent['puntos']] + [None]
            y_vals = [p[1] for p in ent['puntos']] + [None]
            
            capas[capa]['x'].extend(x_vals)
            capas[capa]['y'].extend(y_vals)

        for capa, datos in capas.items():
            color = 'blue' if 'VIVIENDA' in capa.upper() else 'gray'
            if 'EDIFICIO' in capa.upper() or 'ELEMENTOS' in capa.upper():
                color = 'red'
            elif 'MURO' in capa.upper():
                color = 'cyan'
                
            fig.add_trace(go.Scatter(
                x=datos['x'], y=datos['y'],
                mode='lines',
                line=dict(color=color, width=1),
                name=f"Capa: {capa}",
                hoverinfo='name'
            ))
        
        # Dibujar la línea de medición si hay cálculo
        if st.session_state['resultado_abd'] is not None:
            res = st.session_state['resultado_abd']
            cf = ReglasFAR.calcular_centro_polilinea(res['fachada_puntos'])
            co = ReglasFAR.calcular_centro_polilinea(res['obstaculo_puntos'])
            
            fig.add_trace(go.Scatter(
                x=[cf[0], co[0]], y=[cf[1], co[1]],
                mode='lines+markers',
                line=dict(color='yellow', width=4, dash='dash'),
                marker=dict(size=10, color='yellow'),
                name='Medición B'
            ))
            
            fig.add_annotation(
                x=(cf[0]+co[0])/2, y=(cf[1]+co[1])/2,
                text=f"B: {res['B']}m",
                showarrow=False,
                font=dict(color="yellow", size=16),
                bgcolor="black",
                borderpad=4
            )

        fig.update_layout(
            title="Planta 2D",
            yaxis=dict(scaleanchor="x", scaleratio=1),
            height=700,
            template="plotly_dark",
            margin=dict(l=0, r=0, t=80, b=0),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        st.plotly_chart(fig, use_container_width=True)
        
    # --- COLUMNA DERECHA: PANEL DE REVISIÓN ---
    with col2:
        st.subheader("Revisión de Parámetros")
        handles = {e['handle']: e for e in entidades}
        
        with st.form("form_revision"):
            fachada_handle = st.selectbox("Handle de la Fachada", list(handles.keys()))
            obstaculo_handle = st.selectbox("Handle de la Obstrucción", list(handles.keys()))
            submit = st.form_submit_button("Calcular A, B y D")
            
            if submit:
                fachada = handles[fachada_handle]
                obstaculo = handles[obstaculo_handle]
                
                params = ReglasFAR.calcular_parametros_geometricos(
                    fachada['puntos'], obstaculo['puntos'], obstaculo['capa']
                )
                division_calc, angulo = ReglasFAR.calcular_division_obstaculo(
                    fachada['puntos'], obstaculo['puntos']
                )
                params['division'] = division_calc
                params['angulo'] = angulo
                params['fachada_puntos'] = fachada['puntos']
                params['obstaculo_puntos'] = obstaculo['puntos']
                
                st.session_state['resultado_abd'] = params
                st.rerun() # <--- ESTO HACE QUE EL GRÁFICO SE ACTUALICE

        # --- MOSTRAR RESULTADOS ---
        if st.session_state['resultado_abd'] is not None:
            res = st.session_state['resultado_abd']
            st.success("✅ Cálculo realizado")
            
            st.number_input("Distancia B (m)", value=res['B'], disabled=True)
            st.number_input("Distancia D (m)", value=res['D'], disabled=True)
            
            # Al cambiar esto, se actualiza el session_state automáticamente
            nueva_altura = st.number_input("Distancia A (m) [Altura]", value=res['A'], step=0.5)
            res['A'] = nueva_altura 
            
            st.info(f"📍 División **{res['division']}** (Ángulo: {res['angulo']}°)")
            
            export_data = {
                "version_reglas": VERSION_REGLAS,
                "fachada_id": fachada_handle,
                "obstruccion_id": obstaculo_handle,
                "capa": handles[obstaculo_handle]['capa'],
                "parametros": {
                    "B": res['B'], "D": res['D'], "A": res['A'],
                    "division": res['division'], "angulo": res['angulo']
                }
            }
            st.download_button(
                label="📥 Descargar Reporte (JSON)",
                data=json.dumps(export_data, indent=2),
                file_name=f"reporte_far_{fachada_handle}.json",
                mime="application/json"
            )

import streamlit as st
import plotly.graph_objects as go
from core.importador import ImportadorDXF
from core.reglas import ReglasFAR, VERSION_REGLAS

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
            # Limpiamos resultados anteriores si se sube un archivo nuevo
                    # Si hay un cálculo, dibujamos la línea de medición B
        if st.session_state['resultado_abd'] is not None:
            res = st.session_state['resultado_abd']
        except Exception as e:
            st.error(f"Error al leer DXF: {e}")

    st.markdown("---")
    st.warning("⚠️ **Cálculo FAR Bloqueado** hasta validar ecuación con MINVU.")

if 'entidades' in st.session_state:
    entidades = st.session_state['entidades']
    
    col1, col2 = st.columns([2, 1])
        # Aseguramos que los datos del cálculo estén disponibles para el dibujo
    if 'resultado_abd' not in st.session_state:
        st.session_state['resultado_abd'] = None
    
    with col1:
        st.subheader("Visor Geométrico (DXF)")
        fig = go.Figure()
        
        # Dibujar todas las entidades
        for ent in entidades:
            x_vals = [p[0] for p in ent['puntos']]
            y_vals = [p[1] for p in ent['puntos']]
            
            color = 'blue' if 'VIVIENDA' in ent['capa'].upper() else 'gray'
            if 'EDIFICIO' in ent['capa'].upper() or 'ELEMENTOS' in ent['capa'].upper():
                color = 'red'
            
            fig.add_trace(go.Scatter(
                x=x_vals, y=y_vals,
                mode='lines',
                line=dict(color=color, width=2),
                name=f"{ent['tipo']} ({ent['capa']})",
                hoverinfo='name'
            ))
        
        # Si hay un cálculo, dibujamos la línea de medición B
        if 'resultado_abd' in st.session_state:
            res = st.session_state['resultado_abd']
            # Buscamos los puntos de la fachada y el obstáculo guardados
            f_pts = res['fachada_puntos']
            o_pts = res['obstaculo_puntos']
            
            # Centros
            cf = ReglasFAR.calcular_centro_polilinea(f_pts)
            co = ReglasFAR.calcular_centro_polilinea(o_pts)
            
            # Dibujar línea B
            fig.add_trace(go.Scatter(
                x=[cf[0], co[0]], y=[cf[1], co[1]],
                mode='lines+markers',
                line=dict(color='yellow', width=3, dash='dash'),
                marker=dict(size=8, color='yellow'),
                name='Línea de Medición B'
            ))
            
            # Texto con la distancia B en el medio de la línea
            fig.add_annotation(
                x=(cf[0]+co[0])/2, y=(cf[1]+co[1])/2,
                text=f"B: {res['B']}m",
                showarrow=False,
                font=dict(color="yellow", size=14),
                bgcolor="black",
                borderpad=4
            )

                fig.update_layout(
            title="Planta 2D",
            yaxis=dict(scaleanchor="x", scaleratio=1),
            height=600,
            template="plotly_dark",
            margin=dict(l=0, r=0, t=80, b=0), # t=80 para dar espacio arriba
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        )
        st.plotly_chart(fig, use_container_width=True)
        st.info("💡 Usa la barra de herramientas (arriba a la derecha del gráfico) para descargar la imagen del plano con las mediciones.")

    with col2:
        st.subheader("Revisión de Parámetros")
        handles = {e['handle']: e for e in entidades}
        
        with st.form("form_revision"):
            fachada_handle = st.selectbox("Handle de la Fachada", list(handles.keys()))
            obstaculo_handle = st.selectbox("Handle de la Obstrucción", list(handles.keys()))
            
            if st.form_submit_button("Calcular A, B y D"):
                fachada = handles[fachada_handle]
                obstaculo = handles[obstaculo_handle]
                
                params = ReglasFAR.calcular_parametros_geometricos(
                    fachada['puntos'], 
                    obstaculo['puntos'],
                    obstaculo['capa']
                )
                
                division_calc, angulo = ReglasFAR.calcular_division_obstaculo(
                    fachada['puntos'], obstaculo['puntos']
                )
                params['division'] = division_calc
                params['angulo'] = angulo
                
                # Guardamos las coordenadas para poder dibujar la línea
                params['fachada_puntos'] = fachada['puntos']
                params['obstaculo_puntos'] = obstaculo['puntos']
                
                st.session_state['resultado_abd'] = params
                st.success("Cálculo geométrico y de división realizado.")

        if 'resultado_abd' in st.session_state:
            res = st.session_state['resultado_abd']
            
            st.number_input("Distancia B (m)", value=res['B'], disabled=True)
            st.number_input("Distancia D (m)", value=res['D'], disabled=True)
            
            # NUEVO: Campo interactivo para cambiar la altura
            nueva_altura = st.number_input("Distancia A (m) [Altura del Edificio]", value=res['A'], step=0.5)
            # Actualizamos el resultado en memoria si el usuario cambia el valor
            res['A'] = nueva_altura 
            
            st.info(f"📍 División **{res['division']}** (Ángulo: {res['angulo']}°)")
            
            # --- Botón de Exportación ---
            st.markdown("---")
            export_data = {
                "version_reglas": VERSION_REGLAS,
                "fachada_id": fachada_handle,
                "obstruccion_id": obstaculo_handle,
                "capa_obstruccion": handles[obstaculo_handle]['capa'],
                "parametros": {
                    "B": res['B'],
                    "D": res['D'],
                    "A": res['A'],
                    "division": res['division'],
                    "angulo": res['angulo']
                }
            }
            
            import json
            json_string = json.dumps(export_data, indent=2)
            
            st.download_button(
                label="📥 Descargar Reporte (JSON)",
                data=json_string,
                file_name=f"reporte_far_{fachada_handle}_{obstaculo_handle}.json",
                mime="application/json"
            )

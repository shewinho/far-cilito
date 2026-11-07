import streamlit as st
import plotly.graph_objects as go
from core.importador import ImportadorDXF
from core.reglas import ReglasFAR, VERSION_REGLAS
import json
import time
import math
import numpy as np

st.set_page_config(page_title="FARcilito - CEV", layout="wide")
st.title("🏠 FARcilito")
st.caption(f"Herramienta Asistida FAR - CEV | Reglas: {VERSION_REGLAS}")

# --- INICIALIZACIÓN DE MEMORIA ---
if 'resultado_abd' not in st.session_state:
    st.session_state['resultado_abd'] = None

# --- BARRA LATERAL ---
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
            st.session_state['resultado_abd'] = None 
        except Exception as e:
            st.error(f"Error al leer DXF: {e}")

    st.markdown("---")
    
    if 'entidades' in st.session_state:
        st.header("2. Revisión de Parámetros")
        handles = {e['handle']: e for e in st.session_state['entidades']}
        
        fachada_handle = st.selectbox("Handle de la Fachada", list(handles.keys()))
        obstaculo_handle = st.selectbox("Handle de la Obstrucción", list(handles.keys()))
        
        if st.button("Calcular A, B y D", use_container_width=True):
            with st.spinner("Procesando geometría y divisiones..."):
                time.sleep(0.5)
                
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
                params['fachada_id'] = fachada_handle
                params['obstruccion_id'] = obstaculo_handle
                params['capa'] = obstaculo['capa']
                
                st.session_state['resultado_abd'] = params
                st.success("¡Cálculo completado!")

    st.markdown("---")
    st.warning("⚠️ **Cálculo FAR Bloqueado** hasta validar ecuación con MINVU.")


# --- ÁREA PRINCIPAL ---
if 'entidades' in st.session_state:
    entidades = st.session_state['entidades']
    
    col1, col2 = st.columns([2.5, 1])
    
    with col1:
        st.subheader("Visor Geométrico y Divisiones FAR")
        fig = go.Figure()
        
        # 1. Dibujar el DXF
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
                mode='lines', line=dict(color=color, width=1),
                name=f"Capa: {capa}", hoverinfo='name'
            ))
        
        # 2. Si hay cálculo, dibujar la visualización FAR
        if st.session_state['resultado_abd'] is not None:
            res = st.session_state['resultado_abd']
            cf = ReglasFAR.calcular_centro_polilinea(res['fachada_puntos'])
            co = ReglasFAR.calcular_centro_polilinea(res['obstaculo_puntos'])
            
            # Radio del arco (proporcional a la distancia B para que se vea bien)
            radio = max(res['B'] * 1.2, 10) 
            
            # --- A. Dibujar el Semicírculo (Arco exterior) ---
            # Asumimos que la fachada mira al Norte (0°)
            # El arco va desde -90° (Izquierda) a +90° (Derecha)
            theta = np.linspace(np.radians(-90), np.radians(90), 100)
            x_arco = cf[0] + radio * np.sin(theta)
            y_arco = cf[1] + radio * np.cos(theta)
            
            fig.add_trace(go.Scatter(
                x=x_arco, y=y_arco, mode='lines',
                line=dict(color='rgba(255, 255, 255, 0.5)', width=2),
                name='Semicírculo FAR', hoverinfo='skip'
            ))

            # --- B. Dibujar las Líneas Divisorias (Cada 36°) ---
            # Ángulos: -90, -54, -18, 18, 54, 90
            angulos_div = [-90, -54, -18, 18, 54, 90]
            for ang in angulos_div:
                rad = np.radians(ang)
                x_line = [cf[0], cf[0] + radio * np.sin(rad)]
                y_line = [cf[1], cf[1] + radio * np.cos(rad)]
                fig.add_trace(go.Scatter(
                    x=x_line, y=y_line, mode='lines',
                    line=dict(color='rgba(255, 255, 255, 0.3)', width=1, dash='dot'),
                    showlegend=False, hoverinfo='skip'
                ))

            # --- C. Etiquetas de las Divisiones ---
            # Centros de cada división (promedio de sus límites)
            centros_div = [-72, -36, 0, 36, 72]
            for i, ang_centro in enumerate(centros_div):
                rad = np.radians(ang_centro)
                # Un poco más adentro del arco para que se lea bien
                x_txt = cf[0] + (radio * 0.85) * np.sin(rad)
                y_txt = cf[1] + (radio * 0.85) * np.cos(rad)
                
                fig.add_annotation(
                    x=x_txt, y=y_txt,
                    text=f"Div {i+1}",
                    showarrow=False,
                    font=dict(color="white", size=12),
                    bgcolor="rgba(0,0,0,0.5)",
                    borderpad=2
                )

            # --- D. Resaltar el Sector del Obstáculo ---
            # Buscamos los límites del sector calculado
            limites_div = {
                1: (-90, -54), 2: (-54, -18), 3: (-18, 18), 4: (18, 54), 5: (54, 90)
            }
            lim_inf, lim_sup = limites_div[res['division']]
            
            # Creamos el polígono del sector resaltado
            theta_sector = np.linspace(np.radians(lim_inf), np.radians(lim_sup), 50)
            x_sector = cf[0] + radio * np.sin(theta_sector)
            y_sector = cf[1] + radio * np.cos(theta_sector)
            
            # Cerramos el polígono en el centro
            x_sector = np.append(x_sector, cf[0])
            y_sector = np.append(y_sector, cf[1])
            
            fig.add_trace(go.Scatter(
                x=x_sector, y=y_sector,
                fill='toself',
                fillcolor='rgba(255, 255, 0, 0.2)', # Amarillo translúcido
                line=dict(color='yellow', width=2),
                name=f'División {res["division"]} (Obstáculo)',
                hoverinfo='skip'
            ))

            # --- E. Línea de Medición B y Punto del Obstáculo ---
            fig.add_trace(go.Scatter(
                x=[cf[0], co[0]], y=[cf[1], co[1]],
                mode='lines+markers',
                line=dict(color='red', width=3, dash='dash'),
                marker=dict(size=10, color='red'),
                name='Medición B'
            ))
            
            fig.add_annotation(
                x=(cf[0]+co[0])/2, y=(cf[1]+co[1])/2,
                text=f"B: {res['B']}m",
                showarrow=False,
                font=dict(color="red", size=14),
                bgcolor="white",
                borderpad=4
            )

        # Configuración visual
        fig.update_layout(
            title="Planta 2D con Semicírculo FAR",
            yaxis=dict(scaleanchor="x", scaleratio=1),
            height=700,
            template="plotly_dark",
            margin=dict(l=0, r=0, t=80, b=0),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': True})
        
    with col2:
        st.subheader("Resultados")
        
        if st.session_state['resultado_abd'] is not None:
            res = st.session_state['resultado_abd']
            
            st.number_input("Distancia B (m)", value=res['B'], disabled=True)
            st.number_input("Distancia D (m)", value=res['D'], disabled=True)
            
            nueva_altura = st.number_input("Distancia A (m) [Altura]", value=res['A'], step=0.5)
            res['A'] = nueva_altura 
            
            st.info(f"📍 División **{res['division']}** (Ángulo: {res['angulo']}°)")
            
            st.markdown("---")
            
            export_data = {
                "version_reglas": VERSION_REGLAS,
                "fachada_id": res['fachada_id'],
                "obstruccion_id": res['obstruccion_id'],
                "capa": res['capa'],
                "parametros": {
                    "B": res['B'], "D": res['D'], "A": res['A'],
                    "division": res['division'], "angulo": res['angulo']
                }
            }
            
            st.download_button(
                label="📥 Descargar Reporte (JSON)",
                data=json.dumps(export_data, indent=2),
                file_name=f"reporte_far_{res['fachada_id']}.json",
                mime="application/json",
                use_container_width=True
            )
        else:
            st.info("👈 Configura los parámetros en la barra lateral y presiona 'Calcular'.")

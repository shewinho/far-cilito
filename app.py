import streamlit as st
import plotly.graph_objects as go
from core.importador import ImportadorDXF
from core.reglas import ReglasFAR, VERSION_REGLAS
import json
import time
import math
import numpy as np

st.set_page_config(page_title="FARcilito 360° - CEV", layout="wide")
st.title("🏠 FARcilito 360°")
st.caption(f"Motor Geométrico FAR | Múltiples Orientaciones | Reglas: {VERSION_REGLAS}")

if 'resultados_360' not in st.session_state:
    st.session_state['resultados_360'] = None

with st.sidebar:
    st.header("1. Carga de Geometría")
    archivo_dxf = st.file_uploader("Sube un archivo DXF", type=["dxf"])
    
    if archivo_dxf is not None:
        with open("temp.dxf", "wb") as f:
            f.write(archivo_dxf.getbuffer())
        try:
            importador = ImportadorDXF("temp.dxf")
            entidades = importador.extraer_geometria()
            st.session_state['entidades'] = entidades
            st.success(f"DXF cargado: {len(entidades)} polígonos.")
        except Exception as e:
            st.error(f"Error al leer DXF: {e}")

    st.markdown("---")
    
    if 'entidades' in st.session_state:
        st.header("2. Parámetros Globales")
        entidades = st.session_state['entidades']
        
        casas = [e for e in entidades if 'VIVIENDA' in e['capa'].upper()]
        obstaculos = [e for e in entidades if 'VIVIENDA' not in e['capa'].upper()]
        
        if not casas:
            st.warning("No se encontró capa 'VIVIENDA' en el DXF.")
            fachadas_disp = {f"{e['handle']} ({e['capa']})": e for e in entidades}
        else:
            fachadas_disp = {f"{e['handle']} ({e['capa']})": e for e in casas}
            
        fachada_key = st.selectbox("Selecciona la Vivienda", list(fachadas_disp.keys()))
        
        h_fachada = st.number_input("Altura P. Medio Fachada (m)", value=1.5, step=0.1)
        radio_busq = st.number_input("Radio de Búsqueda (m)", value=100.0, step=10.0)
        
        st.markdown("### Ajuste de Alturas (Obstáculos)")
        h_custom_dict = {}
        with st.expander("Editar Alturas de Obstáculos"):
            for obs in obstaculos:
                h_def = 15.0 if "EDIFICIO" in obs['capa'].upper() else 3.0
                h_val = st.number_input(f"{obs['handle']} ({obs['capa']})", value=h_def, key=f"h_{obs['handle']}")
                h_custom_dict[obs['handle']] = h_val
        
        if st.button("Escanear Entorno (8 Orientaciones)", use_container_width=True):
            with st.spinner("Analizando conos CEV y descartando solapamientos..."):
                time.sleep(0.5)
                fachada = fachadas_disp[fachada_key]
                
                for obs in obstaculos:
                    obs['h_custom'] = h_custom_dict.get(obs['handle'])
                
                res_360 = ReglasFAR.escanear_entorno(fachada['puntos'], obstaculos, h_fachada, radio_busqueda=radio_busq)
                
                st.session_state['resultados_360'] = {
                    'datos': res_360,
                    'fachada_activa': fachada['puntos'],
                    'fachada_id': fachada['handle'],
                    'radio': radio_busq
                }
                st.success("¡Escaneo CEV completado!")

if 'entidades' in st.session_state and st.session_state['resultados_360'] is not None:
    res_master = st.session_state['resultados_360']
    datos_ori = res_master['datos']
    orientaciones_detectadas = list(datos_ori.keys())
    
    if not orientaciones_detectadas:
        st.info("No se detectaron obstáculos dentro del radio de búsqueda para ninguna orientación.")
    else:
        tabs = st.tabs(orientaciones_detectadas)
        
        for idx, tab_name in enumerate(orientaciones_detectadas):
            with tabs[idx]:
                col1, col2 = st.columns([2.5, 1.2])
                lista_divs = datos_ori[tab_name]
                
                with col1:
                    fig = go.Figure()
                    
                    for ent in st.session_state['entidades']:
                        capa = ent['capa']
                        pts = list(ent['puntos'])
                        if len(pts) >= 3 and pts[0] != pts[-1]: pts.append(pts[0])
                        color = 'rgba(0, 191, 255, 0.4)' if 'VIVIENDA' in capa.upper() else 'rgba(128, 128, 128, 0.3)'
                        if 'EDIFICIO' in capa.upper() or 'ELEMENTO' in capa.upper(): color = 'rgba(255, 75, 75, 0.3)'
                        fig.add_trace(go.Scatter(
                            x=[p[0] for p in pts], y=[p[1] for p in pts], mode='lines',
                            line=dict(color=color, width=1), showlegend=False, hoverinfo='skip'
                        ))

                    if lista_divs:
                        pf = lista_divs[0]['punto_fachada']
                        angulo_normal = lista_divs[0]['angulo_rad_B']
                        radio = res_master['radio']
                        
                        theta = np.linspace(angulo_normal - math.pi/2, angulo_normal + math.pi/2, 100)
                        fig.add_trace(go.Scatter(
                            x=pf[0] + radio * np.cos(theta), y=pf[1] + radio * np.sin(theta), mode='lines',
                            line=dict(color='rgba(255,255,255,0.4)', width=1, dash='dash'), name='Radio de Búsqueda'
                        ))

                        for ang in [-90, -54, -18, 18, 54, 90]:
                            rad = angulo_normal + math.radians(ang)
                            fig.add_trace(go.Scatter(
                                x=[pf[0], pf[0] + radio * math.cos(rad)], y=[pf[1], pf[1] + radio * np.sin(rad)],
                                mode='lines', line=dict(color='rgba(255,255,255,0.2)', width=1), showlegend=False
                            ))

                        limites_cev = {1: (54, 90), 2: (18, 54), 3: (-18, 18), 4: (-54, -18), 5: (-90, -54)}
                        
                        for item in lista_divs:
                            div_id = item['division']
                            po = item['punto_obstaculo']
                            p_D1, p_D2 = item['p_D1'], item['p_D2']
                            
                            # Relleno del sector amarillo (36 grados)
                            lim_inf, lim_sup = limites_cev[div_id]
                            theta_sec = np.linspace(angulo_normal + math.radians(lim_inf), angulo_normal + math.radians(lim_sup), 30)
                            x_sec = np.append(pf[0] + radio * np.cos(theta_sec), pf[0])
                            y_sec = np.append(pf[1] + radio * np.sin(theta_sec), pf[1])
                            
                            fig.add_trace(go.Scatter(
                                x=x_sec, y=y_sec, fill='toself', fillcolor='rgba(255, 230, 0, 0.08)',
                                line=dict(color='yellow', width=1), name=f'Sector Div {div_id}'
                            ))

                            # Cono de Sombra (Fachada hacia las esquinas del obstáculo D1 y D2)
                            fig.add_trace(go.Scatter(
                                x=[pf[0], p_D1[0], p_D2[0], pf[0]], 
                                y=[pf[1], p_D1[1], p_D2[1], pf[1]], 
                                fill='toself', fillcolor='rgba(0, 210, 255, 0.25)',
                                mode='lines', line=dict(color='#00d2ff', width=1.5, dash='dot'), 
                                name=f'Sombra (Div {div_id})'
                            ))

                            # Línea B (Rojo Intenso)
                            fig.add_trace(go.Scatter(
                                x=[pf[0], po[0]], y=[pf[1], po[1]], mode='lines+markers',
                                line=dict(color='#ff2b2b', width=2.5), marker=dict(size=6, color='#ff2b2b'), name=f'B (Div {div_id})'
                            ))

                            # Línea D (Celeste)
                            fig.add_trace(go.Scatter(
                                x=[p_D1[0], p_D2[0]], y=[p_D1[1], p_D2[1]], mode='lines+markers',
                                line=dict(color='#00d2ff', width=3.5), marker=dict(size=6, color='#00d2ff'), name=f'D (Div {div_id})'
                            ))

                    fig.update_layout(
                        title=f"Visor Geométrico - Fachada {tab_name}",
                        yaxis=dict(scaleanchor="x", scaleratio=1),
                        height=650, template="plotly_dark", margin=dict(l=0, r=0, t=40, b=0)
                    )
                    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': True})
                
                with col2:
                    st.subheader(f"Métricas ({tab_name})")
                    for item in lista_divs:
                        with st.expander(f"📍 Div {item['division']} (Obstáculo: {item['id_obs']})", expanded=True):
                            st.caption(f"Altura obstáculo analizada: {item['h_obs']}m")
                            st.metric("Distancia B (m)", f"{item['B']} m")
                            st.metric("Ancho D (m)", f"{item['D']} m")
                            st.metric("Diferencia Altura A (m)", f"{item['A']} m")

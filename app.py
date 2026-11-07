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

if 'resultado_abd' not in st.session_state:
    st.session_state['resultado_abd'] = None

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
            with st.spinner("Calculando intersecciones..."):
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

if 'entidades' in st.session_state:
    entidades = st.session_state['entidades']
    
    col1, col2 = st.columns([2.5, 1])
    
    with col1:
        st.subheader("Visor Geométrico con Semicírculo FAR")
        fig = go.Figure()
        
        # 1. Dibujar DXF
        capas = {}
        for ent in entidades:
            capa = ent['capa']
            if capa not in capas: capas[capa] = {'x': [], 'y': []}
            capas[capa]['x'].extend([p[0] for p in ent['puntos']] + [None])
            capas[capa]['y'].extend([p[1] for p in ent['puntos']] + [None])

        for capa, datos in capas.items():
            color = 'blue' if 'VIVIENDA' in capa.upper() else 'gray'
            if 'EDIFICIO' in capa.upper() or 'ELEMENTOS' in capa.upper(): color = 'red'
            elif 'MURO' in capa.upper(): color = 'cyan'
            fig.add_trace(go.Scatter(x=datos['x'], y=datos['y'], mode='lines', line=dict(color=color, width=1), name=f"Capa: {capa}"))
        
        # 2. Dibujar FAR
        if st.session_state['resultado_abd'] is not None:
            res = st.session_state['resultado_abd']
            
            # Coordenadas clave
            pf = res['punto_fachada'] # Nace en el borde de la casa
            po = res['punto_obstaculo'] # Choca con el borde del edificio
            
            # Arco (nace desde el punto de la fachada)
            radio = max(res['B'] * 1.2, 10) 
            theta = np.linspace(np.radians(-90), np.radians(90), 100)
            # Para que el arco siempre mire hacia el obstáculo, rotamos según la línea B
            angulo_B = math.atan2(po[1] - pf[1], po[0] - pf[0])
            x_arco = pf[0] + radio * np.sin(theta + angulo_B + math.pi/2)
            y_arco = pf[1] + radio * np.cos(theta + angulo_B + math.pi/2)
            
            fig.add_trace(go.Scatter(x=x_arco, y=y_arco, mode='lines', line=dict(color='rgba(255,255,255,0.5)', width=2), name='Semicírculo'))

            # Divisiones
            angulos_div = [-90, -54, -18, 18, 54, 90]
            for ang in angulos_div:
                rad = np.radians(ang) + angulo_B + math.pi/2
                fig.add_trace(go.Scatter(x=[pf[0], pf[0] + radio*np.sin(rad)], y=[pf[1], pf[1] + radio*np.cos(rad)], mode='lines', line=dict(color='rgba(255,255,255,0.3)', width=1, dash='dot'), showlegend=False))

            # Resaltar sector
            limites_div = {1: (-90, -54), 2: (-54, -18), 3: (-18, 18), 4: (18, 54), 5: (54, 90)}
            lim_inf, lim_sup = limites_div[res['division']]
            theta_sector = np.linspace(np.radians(lim_inf), np.radians(lim_sup), 50) + angulo_B + math.pi/2
            x_sector = np.append(pf[0] + radio*np.sin(theta_sector), pf[0])
            y_sector = np.append(pf[1] + radio*np.cos(theta_sector), pf[1])
            
            fig.add_trace(go.Scatter(x=x_sector, y=y_sector, fill='toself', fillcolor='rgba(255,255,0,0.2)', line=dict(color='yellow', width=2), name=f'División {res["division"]}'))

            # 3. Línea B (desde borde casa a borde edificio)
            fig.add_trace(go.Scatter(x=[pf[0], po[0]], y=[pf[1], po[1]], mode='lines+markers', line=dict(color='red', width=3), marker=dict(size=8, color='red'), name='Distancia B'))
            
            # Etiqueta B
            fig.add_annotation(x=(pf[0]+po[0])/2, y=(pf[1]+po[1])/2, text=f"B: {res['B']}m", showarrow=False, font=dict(color="white", size=14), bgcolor="red", borderpad=4)

            # 4. Línea D (Perpendicular en el obstáculo)
            p_D1, p_D2 = res['p_D1'], res['p_D2']
            fig.add_trace(go.Scatter(x=[p_D1[0], p_D2[0]], y=[p_D1[1], p_D2[1]], mode='lines+markers', line=dict(color='orange', width=3), marker=dict(size=6, color='orange'), name='Ancho D'))
            
            # Etiqueta D
            fig.add_annotation(x=(p_D1[0]+p_D2[0])/2, y=(p_D1[1]+p_D2[1])/2, text=f"D: {res['D']}m", showarrow=False, font=dict(color="black", size=14), bgcolor="orange", borderpad=4)

        fig.update_layout(title="Planta 2D Detallada", yaxis=dict(scaleanchor="x", scaleratio=1), height=700, template="plotly_dark", margin=dict(l=0, r=0, t=80, b=0))
        st.plotly_chart(fig, use_container_width=True)
        
    with col2:
        st.subheader("Resultados")
        if st.session_state['resultado_abd'] is not None:
            res = st.session_state['resultado_abd']
            st.number_input("Distancia B (m)", value=res['B'], disabled=True)
            st.number_input("Distancia D (m)", value=res['D'], disabled=True)
            nueva_altura = st.number_input("Distancia A (m) [Altura]", value=res['A'], step=0.5)
            res['A'] = nueva_altura 
            st.info(f"📍 División **{res['division']}** (Ángulo: {res['angulo']}°)")
            
            export_data = {"version_reglas": VERSION_REGLAS, "fachada_id": res['fachada_id'], "obstruccion_id": res['obstruccion_id'], "capa": res['capa'], "parametros": {"B": res['B'], "D": res['D'], "A": res['A'], "division": res['division'], "angulo": res['angulo']}}
            st.download_button(label="📥 Descargar JSON", data=json.dumps(export_data, indent=2), file_name=f"reporte_{res['fachada_id']}.json", mime="application/json", use_container_width=True)

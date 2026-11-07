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
        except Exception as e:
            st.error(f"Error al leer DXF: {e}")

    st.markdown("---")
    
    if 'entidades' in st.session_state:
        st.header("2. Revisión de Parámetros")
        handles = {f"{e['handle']} ({e['capa']})": e for e in st.session_state['entidades']}
        opciones_keys = list(handles.keys())
        
        fachada_key = st.selectbox("Selecciona la Vivienda / Fachada", opciones_keys)
        obstaculo_key = st.selectbox("Selecciona la Obstrucción", opciones_keys)
        h_fachada = st.number_input("Altura punto medio fachada (m)", value=1.5, step=0.1)
        
        if st.button("Calcular A, B y D", use_container_width=True):
            with st.spinner("Calculando intersecciones y divisiones según norma MINVU..."):
                time.sleep(0.3)
                fachada = handles[fachada_key]
                obstaculo = handles[obstaculo_key]
                
                params = ReglasFAR.calcular_parametros_geometricos(
                    fachada['puntos'], obstaculo['puntos'], obstaculo['capa'], h_fachada
                )
                
                params['fachada_puntos'] = fachada['puntos']
                params['obstaculo_puntos'] = obstaculo['puntos']
                params['fachada_id'] = fachada['handle']
                params['obstruccion_id'] = obstaculo['handle']
                params['capa'] = obstaculo['capa']
                
                st.session_state['resultado_abd'] = params
                st.success("¡Cálculo completado!")

if 'entidades' in st.session_state:
    entidades = st.session_state['entidades']
    
    col1, col2 = st.columns([2.3, 1.2])
    
    with col1:
        st.subheader("Visor Geométrico con Semicírculo FAR (MINVU)")
        fig = go.Figure()
        
        # 1. Dibujar DXF por capas
        capas = {}
        for ent in entidades:
            capa = ent['capa']
            if capa not in capas:
                capas[capa] = {'x': [], 'y': []}
            pts = list(ent['puntos'])
            if ent['tipo'] == 'polilinea' and len(pts) >= 3 and pts[0] != pts[-1]:
                pts.append(pts[0])
            capas[capa]['x'].extend([p[0] for p in pts] + [None])
            capas[capa]['y'].extend([p[1] for p in pts] + [None])

        for capa, datos in capas.items():
            color = 'deepskyblue' if 'VIVIENDA' in capa.upper() else 'gray'
            if 'EDIFICIO' in capa.upper() or 'ELEMENTO' in capa.upper():
                color = '#ff4b4b'
            elif 'MURO' in capa.upper():
                color = 'cyan'
            fig.add_trace(go.Scatter(
                x=datos['x'], y=datos['y'], mode='lines',
                line=dict(color=color, width=1.5), name=f"Capa: {capa}"
            ))
        
        # 2. Dibujar Semicírculo FAR y Divisiones
        res = st.session_state.get('resultado_abd')
        if res is not None and 'angulo_rad_B' in res:
            pf = res['punto_fachada']
            angulo_normal = res['angulo_rad_B']
            lista_divs = res.get('divisiones_lista', [res])
            
            max_b = max([d['B'] for d in lista_divs]) if lista_divs else res['B']
            radio = max(max_b * 1.25, 25)
            
            # Arco de 180° fijo a la fachada
            theta = np.linspace(angulo_normal - math.pi/2, angulo_normal + math.pi/2, 100)
            x_arco = pf[0] + radio * np.cos(theta)
            y_arco = pf[1] + radio * np.sin(theta)
            fig.add_trace(go.Scatter(
                x=x_arco, y=y_arco, mode='lines',
                line=dict(color='rgba(255,255,255,0.6)', width=2), name='Semicírculo 180°'
            ))

            # Rayos cada 36°
            angulos_div = [-90, -54, -18, 18, 54, 90]
            for ang in angulos_div:
                rad = angulo_normal + math.radians(ang)
                fig.add_trace(go.Scatter(
                    x=[pf[0], pf[0] + radio * math.cos(rad)],
                    y=[pf[1], pf[1] + radio * math.sin(rad)],
                    mode='lines', line=dict(color='rgba(255,255,255,0.35)', width=1, dash='dot'),
                    showlegend=False
                ))

            # Etiquetas División 1 a 5 (De izquierda a derecha mirando desde adentro: +72° a -72°)
            centros_cev = {1: 72, 2: 36, 3: 0, 4: -36, 5: -72}
            for div_num, ang_centro in centros_cev.items():
                rad = angulo_normal + math.radians(ang_centro)
                x_txt = pf[0] + (radio * 0.88) * math.cos(rad)
                y_txt = pf[1] + (radio * 0.88) * math.sin(rad)
                fig.add_annotation(
                    x=x_txt, y=y_txt, text=f"Div {div_num}",
                    showarrow=False, font=dict(color="white", size=12),
                    bgcolor="rgba(0,0,0,0.6)", borderpad=3
                )

            # Dibujar B y D para cada división afectada por el obstáculo
            limites_cev = {1: (54, 90), 2: (18, 54), 3: (-18, 18), 4: (-54, -18), 5: (-90, -54)}
            for item in lista_divs:
                div_id = item['division']
                lim_inf, lim_sup = limites_cev[div_id]
                theta_sec = np.linspace(angulo_normal + math.radians(lim_inf), angulo_normal + math.radians(lim_sup), 40)
                x_sec = np.append(pf[0] + radio * np.cos(theta_sec), pf[0])
                y_sec = np.append(pf[1] + radio * np.sin(theta_sec), pf[1])
                
                fig.add_trace(go.Scatter(
                    x=x_sec, y=y_sec, fill='toself',
                    fillcolor='rgba(255, 230, 0, 0.18)',
                    line=dict(color='yellow', width=1.5),
                    name=f'Sector Div {div_id}'
                ))

                po = item['punto_obstaculo']
                p_D1, p_D2 = item['p_D1'], item['p_D2']

                # Línea B
                fig.add_trace(go.Scatter(
                    x=[pf[0], po[0]], y=[pf[1], po[1]], mode='lines+markers',
                    line=dict(color='#ff2b2b', width=3),
                    marker=dict(size=7, color='#ff2b2b'),
                    name=f'B (Div {div_id})'
                ))
                fig.add_annotation(
                    x=(pf[0]+po[0])/2, y=(pf[1]+po[1])/2,
                    text=f"B: {item['B']}m", showarrow=False,
                    font=dict(color="white", size=12), bgcolor="#c91c1c", borderpad=3
                )

                # Línea D
                fig.add_trace(go.Scatter(
                    x=[p_D1[0], p_D2[0]], y=[p_D1[1], p_D2[1]], mode='lines+markers',
                    line=dict(color='orange', width=3),
                    marker=dict(size=6, color='orange'),
                    name=f'D (Div {div_id})'
                ))
                fig.add_annotation(
                    x=(p_D1[0]+p_D2[0])/2, y=(p_D1[1]+p_D2[1])/2,
                    text=f"D: {item['D']}m", showarrow=False,
                    font=dict(color="black", size=12), bgcolor="orange", borderpad=3
                )

        fig.update_layout(
            title="Planta 2D - Divisiones CEV",
            yaxis=dict(scaleanchor="x", scaleratio=1),
            height=700, template="plotly_dark",
            margin=dict(l=0, r=0, t=50, b=0)
        )
        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': True})
        
    with col2:
        st.subheader("Resultados por División")
        res = st.session_state.get('resultado_abd')
        if res is not None and 'angulo_rad_B' in res:
            lista_divs = res.get('divisiones_lista', [res])
            if not lista_divs:
                st.warning("El obstáculo seleccionado está fuera del campo visual (180°) de esta fachada.")
            else:
                st.success(f"El obstáculo intersecta **{len(lista_divs)}** división(es).")
                for idx, item in enumerate(lista_divs):
                    with st.expander(f"📍 División {item['division']} (B={item['B']}m | D={item['D']}m)", expanded=True):
                        st.metric("Distancia B (m)", f"{item['B']} m")
                        st.metric("Ancho D (m)", f"{item['D']} m")
                        st.metric("Diferencia Altura A (m)", f"{item['A']} m")
                
                export_data = {
                    "version_reglas": VERSION_REGLAS,
                    "fachada_id": res['fachada_id'],
                    "obstruccion_id": res['obstruccion_id'],
                    "capa": res['capa'],
                    "divisiones": lista_divs
                }
                st.download_button(
                    label="📥 Descargar JSON CEV",
                    data=json.dumps(export_data, indent=2),
                    file_name=f"reporte_far_{res['obstruccion_id']}.json",
                    mime="application/json",
                    use_container_width=True
                )

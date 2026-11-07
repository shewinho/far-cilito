import streamlit as st
import plotly.graph_objects as go
from core.importador import ImportadorDXF
from core.reglas import ReglasFAR, VERSION_REGLAS

st.set_page_config(page_title="Herramienta FAR - CEV", layout="wide")

st.title("🏠 Herramienta Asistida FAR - CEV")
st.caption(f"Prototipo de revisión geométrica - Reglas: {VERSION_REGLAS}")

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
    st.warning("⚠️ **Cálculo FAR Bloqueado** hasta validar ecuación con MINVU.")

if 'entidades' in st.session_state:
    entidades = st.session_state['entidades']
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("Visor Geométrico (DXF)")
        fig = go.Figure()
        
        for ent in entidades:
            x_vals = [p[0] for p in ent['puntos']]
            y_vals = [p[1] for p in ent['puntos']]
            
            color = 'blue' if 'MURO' in ent['capa'].upper() or 'VIVIENDA' in ent['capa'].upper() else 'gray'
            if 'EDIFICIO' in ent['capa'].upper() or 'ELEMENTOS' in ent['capa'].upper():
                color = 'red'
            
            fig.add_trace(go.Scatter(
                x=x_vals, y=y_vals,
                mode='lines',
                line=dict(color=color, width=2),
                name=f"{ent['tipo']} ({ent['capa']})",
                hoverinfo='name'
            ))
        
        fig.update_layout(
            title="Planta 2D",
            yaxis=dict(scaleanchor="x", scaleratio=1),
            height=600,
            template="plotly_dark",
            margin=dict(l=0, r=0, t=30, b=0)
        )
        st.plotly_chart(fig, use_container_width=True)
        st.info("💡 Encuentra el Handle pasando el mouse por las líneas.")

    with col2:
        st.subheader("Revisión de Parámetros")
        handles = {e['handle']: e for e in entidades}
        
        with st.form("form_revision"):
            fachada_handle = st.selectbox("Handle de la Fachada", list(handles.keys()))
            obstaculo_handle = st.selectbox("Handle de la Obstrucción", list(handles.keys()))
            
            if st.form_submit_button("Calcular A, B y D"):
                fachada = handles[fachada_handle]
                obstaculo = handles[obstaculo_handle]
                
                # Llamada a la regla de cálculo
                params = ReglasFAR.calcular_parametros_geometricos(
                    fachada['puntos'], 
                    obstaculo['puntos'],
                    obstaculo['capa']
                )
                
                # Calcular la división
                division_calc, angulo = ReglasFAR.calcular_division_obstaculo(
                    fachada['puntos'], obstaculo['puntos']
                )
                params['division'] = division_calc
                params['angulo'] = angulo
                
                st.session_state['resultado_abd'] = params
                st.success("Cálculo geométrico y de división realizado.")

        if 'resultado_abd' in st.session_state:
            res = st.session_state['resultado_abd']
            st.number_input("Distancia B (m) calculada", value=res['B'], disabled=True)
            st.number_input("Distancia D (m) calculada", value=res['D'], disabled=True)
            a_manual = st.number_input("Distancia A (m) [Requiere altura]", value=res['A'], step=0.1)
            
            st.info(f"📍 El obstáculo cae en la **División {res['division']}** (Ángulo: {res['angulo']}°)")

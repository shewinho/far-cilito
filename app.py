import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from core.importador import ImportadorDXF

st.set_page_config(page_title="Herramienta FAR - CEV", layout="wide")

st.title("🏠 Herramienta Asistida FAR - CEV")
st.caption("Prototipo de revisión geométrica - v0.2")

with st.sidebar:
    st.header("1. Importar Geometría")
    archivo_dxf = st.file_uploader("Sube un archivo DXF", type=["dxf"])
    
    if archivo_dxf is not None:
        with open("temp.dxf", "wb") as f:
            f.write(archivo_dxf.getbuffer())
        
        try:
            importador = ImportadorDXF("temp.dxf")
            entidades = importador.extraer_geometria()
            st.success(f"DXF cargado: {len(entidades)} entidades encontradas.")
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
            
            color = 'blue' if 'MURO' in ent['capa'].upper() else 'gray'
            
            fig.add_trace(go.Scatter(
                x=x_vals, y=y_vals,
                mode='lines',
                line=dict(color=color, width=2),
                name=f"{ent['tipo']} ({ent['capa']})",
                hoverinfo='name'
            ))
        
        fig.update_layout(
            title="Planta 2D (Interactivo)",
            xaxis_title="X (m)",
            yaxis_title="Y (m)",
            yaxis=dict(scaleanchor="x", scaleratio=1),
            height=600,
            margin=dict(l=0, r=0, t=30, b=0),
            template="plotly_dark"
        )
        st.plotly_chart(fig, use_container_width=True)
        st.info("💡 Haz zoom y pasa el mouse sobre las líneas para ver sus capas.")

    with col2:
        st.subheader("Revisión de Parámetros")
        handles_disponibles = [e['handle'] for e in entidades]
        
        with st.form("form_revision"):
            fachada_seleccionada = st.selectbox("Handle de la Fachada", handles_disponibles)
            obstaculo_seleccionado = st.selectbox("Handle de la Obstrucción", handles_disponibles)
            division = st.selectbox("División (1-5)", [1, 2, 3, 4, 5])
            
            b_val = st.number_input("Distancia B (m)", value=0.0, step=0.1)
            d_val = st.number_input("Distancia D (m)", value=0.0, step=0.1)
            a_val = st.number_input("Distancia A (m)", value=0.0, step=0.1)
            
            submit = st.form_submit_button("Registrar Datos")
            
            if submit:
                st.success(f"Registrado: Fachada {fachada_seleccionada}")
else:
    st.info("👈 Por favor, sube un archivo DXF desde la barra lateral para comenzar.")

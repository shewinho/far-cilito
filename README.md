# FARcilito

Calcula los parámetros del **FAR** (división, A, B y D de cada obstrucción) para la Calificación Energética de Viviendas (CEV, Chile) a partir de un plano DXF, siguiendo el Manual de Procedimientos CEV 2025 (secciones 6.8 y 11.8).

> El factor FAR final **no se calcula**: el manual no incluye la ecuación. Ver `core/reglas.py`.

## Uso
```bash
pip install -r requirements.txt
streamlit run app.py
```
Botón «Cargar ejemplo del manual» para ver el ejercicio de acreditación (`data/ejemplo_manual.dxf`).

## Convenciones del DXF
- Norte = +Y (usa «Rotación del Norte» si el plano está girado).
- La vivienda y las obstrucciones son contornos cerrados (polilíneas cerradas o líneas que formen un contorno).
- Altura de cada obstrucción: capa terminada en `_H<altura>` (p. ej. `EDIFICIO_B_H15`) o se edita en la tabla de la app.
- Un `TEXT` dentro del contorno le da nombre (como «Elemento 3» en el ejercicio).

## Estructura
- `core/far.py` motor geométrico (sin Streamlit): fachadas, divisiones, sobreposiciones, A/B/D
- `core/dibujo.py` láminas Plotly como las del ejercicio
- `core/importador.py` DXF → entidades y contornos
- `core/exportar.py` JSON de trazabilidad
- `tests/` pruebas; `tests/crear_ejemplo_manual.py` regenera el DXF del ejercicio

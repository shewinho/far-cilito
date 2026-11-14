# FARcilito — conocimiento del proyecto

Este archivo resume qué es el proyecto, cómo está armado, qué funciona hoy y qué reglas no se rompen.
Todo lo marcado como «verificado» se comprobó leyendo el código de este repositorio (no son suposiciones).

---

## 1. Qué es FARcilito y el stack

**FARcilito** calcula los parámetros del **FAR** (división, A, B y D de cada obstrucción) para la
Calificación Energética de Viviendas (CEV, Chile) a partir de un plano DXF, siguiendo el
**Manual de Procedimientos CEV 2025, secciones 6.8 y 11.8**.

- La app es una interfaz **Streamlit** (`app.py`) que empieza con `st.set_page_config(...)` y usa
  `st.session_state` como estado de la sesión.
- Se publica en **Streamlit Community Cloud** alimentada desde `main`, y se muestra
  **incrustada por iframe en un blog**. Por eso la interfaz debe ser autónoma y no depender de
  archivos locales del usuario más allá del DXF que se sube.
- El desarrollo se hace desde **un Mac y un PC con Windows**, sincronizando por git. Todo cambio
  debe funcionar en ambos sistemas: rutas con `pathlib` (nunca rutas absolutas ni separadores
  fijos), texto en UTF-8 y comandos que no dependan de un solo sistema operativo.

**Dependencias declaradas** (`requirements.txt`):

| Paquete | Uso en el código |
|---|---|
| `streamlit>=1.35` | interfaz y selección por clic (`st.plotly_chart(..., on_select="rerun")`) |
| `ezdxf>=1.1` | lectura de DXF (`core/importador.py`, `tests/crear_ejemplo_manual.py`) |
| `plotly>=5.15` | láminas y figuras (`core/dibujo.py`, `core/alzado.py`, `core/seleccion.py`) |
| `pandas` | tablas de la interfaz (`app.py`) |
| `shapely>=2.0` | polígonos, `polygonize`, uniones e intersecciones de área |
| `numpy` | barrido de rayos del motor (`core/far.py`) |
| `pytest` | pruebas de `tests/test_far.py` |

> No hay dependencias de PDF, IFC ni base de datos: si se agregan, se avisa antes.

---

## 2. Estructura de archivos actual

```
app.py                      interfaz Streamlit completa (pestañas, estado, barra lateral)
requirements.txt            dependencias declaradas
README.md                   uso, convenciones del DXF y flujo
knowledge.md                este archivo

core/
  __init__.py               paquete vacío
  far.py                    motor geométrico: aristas/fachadas, rayos, divisiones, A, B, D, sobrepuestas
  importador.py             DXF -> entidades sueltas y contornos cerrados (con nombre y altura por capa)
  dibujo.py                 láminas del FAR con los 3 pasos del ejercicio (Plotly)
  alzado.py                 centro de fachada irregular y altura promedio de obstáculo variable
  seleccion.py              selección por clic sobre el dibujo (ids, alternar inclusión, aristas)
  exportar.py               JSON de trazabilidad de una o varias fachadas (sección 11.8)
  reglas.py                 VERSION_REGLAS y bloqueo explícito del FAR final

data/
  ejemplo_manual.dxf        réplica del ejercicio de acreditación CEV (plano)
  ejemplo_alzado.dxf        ejemplo de alzado para la pestaña de fachadas irregulares

tests/
  test_far.py               pruebas del motor sobre el ejemplo del manual
  crear_ejemplo_manual.py   script que regenera data/ejemplo_manual.dxf
  poligonos_ejemplo.json    polígonos de origen que lee crear_ejemplo_manual.py
```

**Mapa de responsabilidades:** la geometría y el cálculo viven en `core/`; `app.py` solo orquesta
estado, widgets, tablas y descargas. `core/` no importa Streamlit.

---

## 3. Estado actual (verificado en el código)

### Lo que ya funciona

- **Lectura de DXF** (`core/importador.py`): `LINE`, `LWPOLYLINE`/`POLYLINE` (con bulges), `CIRCLE`,
  `ARC`, `ELLIPSE`, `SPLINE`, `HATCH` e `INSERT` (bloques, vía entidades virtuales). Reconstruye
  contornos formados por líneas sueltas con `shapely.polygonize` por capa.
- **Nombre y altura automáticos**: un `TEXT`/`MTEXT` dentro del contorno da el nombre; la capa con
  sufijo `_H<altura>` (p. ej. `EDIFICIO_B_H15`) fija `altura_capa`.
- **Motor FAR** (`core/far.py`): semicírculo de 180° en el punto medio de la fachada, 5 divisiones de
  36°, barrido de rayos (`PASO_ANGULAR = 0.05°`), cálculo de **A, B y D** por obstrucción y división,
  tratamiento de una obstrucción en varias divisiones, resolución de **sobrepuestas** por mayor
  ángulo de elevación, y **fachada discontinua** con la Ecuación 5
  (`X = D·Área_b/(Área_a+Área_b)`).
- **Cotización absoluta**: A = cota del techo − cota del punto medio; la cota del punto medio es
  cota del terreno de la fachada + altura sobre ese terreno.
- **Modo 360°** (`fachadas_de_vivienda`): una fachada por cada arista real de la vivienda, ordenadas
  por azimut real; se descartan aristas menores a `largo_min = 0.5 m`.
- **Rotación del Norte**: el azimut real es el azimut del plano menos la rotación indicada; hay una
  prueba de invariancia a la rotación del dibujo.
- **Selección con clic** (`core/seleccion.py` + `app.py`): vivienda, obstrucciones y arista de
  fachada; incluye fallback con listas para versiones de Streamlit que no soportan `on_select`.
- **Alturas y terreno por obstrucción** en la ficha del objeto, con cota del techo y **A = techo −
  punto medio** mostradas en vivo; las obstrucciones sin altura se marcan en naranja.
- **Pestaña «Alzado e irregulares»**: centro de fachada irregular por paralelepípedo inscrito
  (cuerpos ingresados a mano, alzado regular o DXF de alzado, con exclusión de muros ≤ 1,6 m) y
  altura promedio de obstáculo variable (área sobre el punto medio / longitud de base).
- **Láminas** (`core/dibujo.py`): tres pasos del ejercicio (trazar divisiones, identificarlas,
  obstrucciones con cono de visión, B, D y recuadros con B/D/A), con vista ajustable y recuadros
  ocultables.
- **Exportación**: CSV de los datos a ingresar en la CEV y **JSON de trazabilidad** de una o varias
  fachadas con `version_reglas`, fecha, archivo, fachada, punto medio, criterio, tramos, omitidas,
  advertencias e `incluido_en_CEV`.
- **Pruebas** (`tests/test_far.py`): estructura por división del ejercicio, A, cifras de B y D
  cercanas al manual (tolerancias), invariancia a la rotación, obstrucción bajo el punto medio,
  Ecuación 5, numeración de divisiones, contornos de líneas sueltas, modo 360°, cotas absolutas,
  selección por clic y funciones de alzado.

### Lo que no está implementado

- **El factor FAR final**: `core/reglas.py::calcular_far` lanza `NotImplementedError` a propósito, y
  los JSON exportados dicen `"far_final": "No calculado: ecuación FAR(A,B,D) pendiente de validación
  con MINVU"`.
- **Exportación a PDF**: hoy solo existe el PNG que Plotly puede bajar desde la barra de la figura y
  las descargas CSV/JSON.
- **IFC**: el importador solo entiende DXF.
- **Criterio de desestimación**: el manual dice «se pueden desestimar» con `B/D < 0,1` y/o
  `B/A < 0,1`, lectura que suena invertida; por eso la app ofrece tres criterios y el evaluador
  decide. No hay una decisión automática tomada por la app.

---

## 4. Reglas inquebrantables

1. **El FAR final no se calcula.** La ecuación `FAR(A,B,D)` no está en el manual. `calcular_far` debe
   seguir lanzando `NotImplementedError` hasta validarla con MINVU. Nunca rellenar ese campo con una
   fórmula propia, un factor aproximado o un valor de ejemplo.
2. **`VERSION_REGLAS = "CEV_2025_Manual_6.8"`** identifica las reglas aplicadas y viaja en cada
   exportación. Si cambian las reglas, se cambia la versión de forma explícita.
3. **Convención de Norte y azimut:** Norte = +Y del DXF salvo que se indique rotación; azimut CEV
   0° = Norte, 90° = Este, sentido horario. El azimut real de la fachada es el del plano menos la
   rotación del Norte.
4. **Semicírculo fijo por fachada:** base en el centro de la fachada, eje = normal exterior de la
   fachada, 5 divisiones de 36° numeradas de izquierda a derecha para un observador dentro de la
   vivienda. El eje no depende de las obstrucciones.
5. **`core/` es independiente de Streamlit.** La lógica y los cálculos se prueban sin levantar la
   app; la interfaz vive en `app.py`.
6. **Desestimar es opcional y explícito.** La app informa los cocientes y solo marca tramos como
   desestimables si el evaluador eligió un criterio (`literal` o `invertido`); por defecto,
   `ninguno`.
7. **No inventar valores ni criterios del manual CEV.** Si el manual no define algo (la ecuación
   final, un criterio, una tolerancia), se deja bloqueado o se expone como opción del evaluador y se
   documenta; no se completa por conveniencia.
8. **Dejar trazabilidad en el JSON exportado.** Toda fachada exportada debe conservar
   `version_reglas`, archivo de origen, vivienda, fachada (orientación, azimut, punto medio y cómo se
   obtuvo), criterio de desestimación, cota del punto medio, tramos con A/B/D y sus cocientes,
   estado, notas, obstrucciones omitidas con su motivo, advertencias e `incluido_en_CEV`.

---

## 5. Hacia dónde vamos

Estado de cada objetivo, revisado contra el código actual:

| Objetivo | Estado | Evidencia |
|---|---|---|
| Reproducir los mismos dibujos del PDF del ejercicio de acreditación CEV, calcular todo y representarlo | **hecho** | `core/dibujo.py::figura_far` reproduce los 3 pasos (semicírculo y divisiones, rótulos, cono/B/D/recuadros B-D-A); `tests/test_far.py` compara la estructura y las cifras con el manual |
| Incluir el rigor de cada situación especial que indica el manual | **hecho** | Sobrepuestas por mayor ángulo, fachada discontinua (Ecuación 5), obstrucción partida o parcialmente oculta, obstáculo bajo el punto medio, altura promedio de obstáculo variable, muros interiores ≤ 1,6 m y terreno con desnivel |
| Elegir vivienda y obstrucciones con clic en el dibujo | **hecho** | `core/seleccion.py` + `grafico_clic` en `app.py` (con listas de respaldo si Streamlit < 1.35) |
| Altura del edificio y del terreno en ese punto, con la diferencia de altura | **hecho** | Ficha del objeto en `app.py`: altura, cota del terreno, cota del techo y `A = techo − punto medio`; `cota_punto_medio` en el cálculo |
| Pestaña para fachadas irregulares y alturas irregulares (alzado propio o subido) | **hecho** | Pestaña «Alzado e irregulares»: alzado regular, cuerpos a mano o DXF de alzado; altura promedio del obstáculo (`core/alzado.py`) |
| Múltiples obstáculos por fachada con JSON conjunto | **hecho** | `calcular_fachada` admite varias obstrucciones y `a_dict_multiple` exporta todas las fachadas en un solo JSON |
| Exportar PDF con imagen y tabla como memoria de cálculo | **pendiente** | No hay generación de PDF ni dependencia para ello; solo PNG de Plotly y descargas CSV/JSON |
| A futuro, soporte IFC | **pendiente** | `core/importador.py` solo lee DXF; `app.py` solo acepta `.dxf` |

---

## 6. Cómo trabajar aquí

- **Siempre en una rama aparte, nunca directo en `main`.** `main` alimenta la app desplegada.
- **Cambios pequeños.** Un objetivo por cambio, fácil de revisar y de revertir.
- **Mostrar el diff antes de dar algo por terminado.**
- **No agregar dependencias sin avisar** (y si se agregan, actualizar `requirements.txt`).
- **Lógica en `core/`, interfaz en `app.py`.** No meter Streamlit en `core/`.
- **Comentarios y mensajes en español.**

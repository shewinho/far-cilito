"""Motor geométrico del FAR (Manual CEV 2025, secciones 6.8 y 11.8).

Calcula, por fachada, la división, A, B y D de cada obstrucción. NO calcula el factor FAR final:
la ecuación que convierte A, B y D en FAR no figura en el manual (ver core/reglas.py).

Reglas implementadas (todas del manual, 6.8):
  * Semicírculo de 180° con base en el CENTRO de la fachada, orientado según la normal exterior de la
    fachada (fijo, no depende de los obstáculos), con 5 divisiones de 36° numeradas de izquierda a
    derecha para un observador ubicado dentro de la vivienda.
  * Una obstrucción que cae en más de una división se trata por separado en cada una.
  * A = altura del obstáculo - altura del punto medio de la fachada.
  * B = distancia del punto medio de la fachada al punto medio de la parte visible de la obstrucción
        dentro de la división (punto medio medido a lo largo de la cara visible).
  * D = ancho del bloqueo solar de esa parte visible, medido perpendicular a B y pasando por el
        punto donde termina B.
  * Obstrucciones sobrepuestas: en la sección sobrepuesta prevalece la que genera mayor ángulo
    respecto a la horizontal trazada desde el punto medio de la fachada; la otra se omite.
  * Punto medio de fachada discontinua: Ecuación 5, X = D * Área_b / (Área_a + Área_b).

Convención: azimut CEV (0° = Norte, 90° = Este, horario). En el plano del DXF se asume Norte = +Y,
salvo que se indique una rotación.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from shapely.geometry import Point, Polygon

N_DIVISIONES = 5
ANCHO_DIV = 36.0
ALTURA_PUNTO_MEDIO_DEFECTO = 1.5   # m (nota 3 del ejercicio del manual)
PASO_ANGULAR = 0.05                # grados, resolución del barrido de rayos
UMBRAL_DESESTIMAR = 0.1            # manual 6.8: cociente < 0,1

ORIENTACIONES = ["Norte", "Noreste", "Este", "Sureste", "Sur", "Suroeste", "Oeste", "Noroeste"]


# ------------------------------------------------------------------ utilidades
def azimut(dx: float, dy: float) -> float:
    return math.degrees(math.atan2(dx, dy)) % 360


def nombre_orientacion(az: float) -> str:
    return ORIENTACIONES[int(((az % 360) + 22.5) // 45) % 8]


def division_de_angulo(phi: float) -> int:
    """phi = ángulo relativo al eje de la fachada, en [-90, 90]. Devuelve 1..5 (0 si fuera del semicírculo)."""
    if phi < -90 - 1e-9 or phi > 90 + 1e-9:
        return 0
    return int(min(math.floor((phi + 90) / ANCHO_DIV + 1e-9), N_DIVISIONES - 1)) + 1


def limites_division(k: int) -> tuple[float, float]:
    return (-90 + (k - 1) * ANCHO_DIV, -90 + k * ANCHO_DIV)


# --------------------------------------------------------------------- fachada
@dataclass
class Fachada:
    nombre: str
    punto_medio: tuple[float, float]
    azimut_normal: float              # azimut CEV del eje ortogonal a la fachada (normal exterior)
    longitud: float = 0.0
    modo_punto_medio: str = "centro de la arista"
    detalle: dict = field(default_factory=dict)
    rotacion_norte: float = 0.0       # ° horario entre +Y del dibujo y el Norte real

    @property
    def azimut_real(self) -> float:
        """Azimut CEV real del eje ortogonal a la fachada (manual 11.8 b)."""
        return (self.azimut_normal - self.rotacion_norte) % 360

    @property
    def orientacion(self) -> str:
        return nombre_orientacion(self.azimut_real)


def _anillo_antihorario(puntos):
    pts = list(puntos)
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts = pts[:-1]
    area2 = sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1] for i in range(len(pts)))
    return pts if area2 > 0 else pts[::-1]


def aristas_vivienda(puntos, rotacion_norte: float = 0.0) -> list[dict]:
    """Aristas del polígono de la vivienda con punto medio y normal exterior.

    rotacion_norte: ángulo (° horario) entre el eje +Y del dibujo y el Norte real.
    El azimut real = azimut en el plano - rotacion_norte.
    """
    ring = _anillo_antihorario(puntos)
    out = []
    for i in range(len(ring)):
        p1, p2 = ring[i], ring[(i + 1) % len(ring)]
        ex, ey = p2[0] - p1[0], p2[1] - p1[1]
        L = math.hypot(ex, ey)
        if L < 1e-9:
            continue
        az_plano = azimut(ey, -ex)  # normal exterior = derecha del recorrido antihorario
        out.append({
            "indice": i, "p1": p1, "p2": p2, "longitud": L,
            "punto_medio": ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2),
            "azimut_plano": az_plano,
            "azimut": (az_plano - rotacion_norte) % 360,
        })
    return out


def fachada_desde_arista(ar: dict, nombre: str | None = None, rotacion_norte: float = 0.0) -> Fachada:
    return Fachada(nombre or f"Fachada {nombre_orientacion(ar['azimut'])}", ar["punto_medio"],
                   ar["azimut_plano"], ar["longitud"], "centro del ancho de la arista", rotacion_norte=rotacion_norte)


def fachadas_de_vivienda(puntos, rotacion_norte: float = 0.0, largo_min: float = 0.5) -> list[Fachada]:
    """Una fachada por cada arista real de la vivienda (modo 360°): el FAR se calcula por orientación de
    fachada existente, tomando como eje la normal exterior de cada una. Se ignoran aristas menores a largo_min."""
    out = []
    for a in aristas_vivienda(puntos, rotacion_norte):
        if a["longitud"] < largo_min:
            continue
        f = fachada_desde_arista(a, rotacion_norte=rotacion_norte)
        f.nombre = f"{nombre_orientacion(a['azimut'])} · arista {a['indice']}"
        f.detalle = {"arista": a["indice"]}
        out.append(f)
    return sorted(out, key=lambda f: f.azimut_real)


def punto_medio_discontinuo(ar_a: dict, ar_b: dict, area_a: float, area_b: float) -> tuple[tuple[float, float], dict]:
    """Ecuación 5 del manual: X = D * Área_b / (Área_a + Área_b).

    ar_a y ar_b son dos aristas paralelas con la misma orientación (planos distintos, retranqueo D).
    El centro del ancho es la mitad del ancho total (proyección sobre la tangente);
    la profundidad se desplaza X desde el plano a hacia el plano b.
    """
    if area_a + area_b <= 0:
        raise ValueError("Las áreas de fachada deben ser positivas.")
    n = np.array([math.sin(math.radians(ar_a["azimut_plano"])), math.cos(math.radians(ar_a["azimut_plano"]))])
    t = np.array([n[1], -n[0]])
    pts = np.array([ar_a["p1"], ar_a["p2"], ar_b["p1"], ar_b["p2"]], dtype=float)
    ct = (pts @ t).min() / 2 + (pts @ t).max() / 2
    base = np.array(ar_a["punto_medio"], dtype=float)
    D = float(n @ (np.array(ar_b["punto_medio"], dtype=float) - base))   # retranqueo con signo (sobre la normal de a)
    X = D * area_b / (area_a + area_b)
    p = base + t * (ct - float(t @ base)) + n * X
    return (float(p[0]), float(p[1])), {"D_retranqueo": D, "X": X, "area_a": area_a, "area_b": area_b}


# ---------------------------------------------------------------- obstrucciones
@dataclass
class Obstruccion:
    id: str
    nombre: str
    capa: str
    puntos: list
    altura: float                     # altura total sobre el terreno natural (m); si es variable, la promedio


@dataclass
class Tramo:
    division: int
    obstruccion_id: str
    nombre: str
    capa: str
    A: float
    B: float
    D: float
    altura_obstruccion: float
    angulo_elevacion: float           # grados sobre la horizontal del punto medio
    angulo_b: float                   # ángulo relativo al eje de la fachada (-90..90)
    punto_b: tuple
    p_d1: tuple
    p_d2: tuple
    cara_visible: list                # puntos de la cara visible (para dibujar el cono)
    phi_ini: float
    phi_fin: float
    estado: str = "considerada"       # considerada | desestimable | omitida
    notas: list = field(default_factory=list)

    @property
    def B_sobre_D(self):
        return self.B / self.D if self.D > 1e-9 else math.inf

    @property
    def B_sobre_A(self):
        return self.B / self.A if self.A > 1e-9 else math.inf

    @property
    def D_sobre_B(self):
        return self.D / self.B if self.B > 1e-9 else math.inf

    @property
    def A_sobre_B(self):
        return self.A / self.B if self.B > 1e-9 else math.inf


@dataclass
class ResultadoFachada:
    fachada: Fachada
    altura_punto_medio: float
    tramos: list[Tramo]               # tramos visibles (considerados o desestimables)
    omitidas: list[dict]              # obstrucciones/divisiones omitidas (sobrepuestas o más bajas que el punto medio)
    advertencias: list[str]
    criterio: str


# ------------------------------------------------------------------- algoritmo
def _impactos(origen, ux, uy, puntos):
    """Primer impacto de cada rayo con el contorno de un polígono. Devuelve (r, idx_arista); r=inf si no hay."""
    P = np.asarray(puntos, dtype=float)
    Q = np.roll(P, -1, axis=0)
    ex, ey = (Q[:, 0] - P[:, 0])[None, :], (Q[:, 1] - P[:, 1])[None, :]
    wx, wy = (P[:, 0] - origen[0])[None, :], (P[:, 1] - origen[1])[None, :]
    ux, uy = ux[:, None], uy[:, None]
    den = ux * ey - uy * ex
    with np.errstate(divide="ignore", invalid="ignore"):
        t = (wx * ey - wy * ex) / den
        s = (wx * uy - wy * ux) / den
    ok = (np.abs(den) > 1e-12) & (t > 1e-9) & (s >= -1e-9) & (s <= 1 + 1e-9)
    t = np.where(ok, t, np.inf)
    idx = np.argmin(t, axis=1)
    r = t[np.arange(t.shape[0]), idx]
    return r, idx


def _tramos_continuos(mask):
    idx = np.flatnonzero(mask)
    if idx.size == 0:
        return []
    cortes = np.flatnonzero(np.diff(idx) > 1)
    ini = np.r_[idx[0], idx[cortes + 1]]
    fin = np.r_[idx[cortes], idx[-1]]
    return list(zip(ini, fin))


def calcular_fachada(fachada: Fachada, obstrucciones: list[Obstruccion],
                     altura_punto_medio: float = ALTURA_PUNTO_MEDIO_DEFECTO,
                     criterio_desestimacion: str = "ninguno",
                     paso: float = PASO_ANGULAR) -> ResultadoFachada:
    """criterio_desestimacion: 'ninguno' | 'literal' (B/D<0,1 o B/A<0,1) | 'invertido' (D/B<0,1 o A/B<0,1)."""
    O = fachada.punto_medio
    phis = np.arange(-90.0, 90.0 + 1e-9, paso)
    az = np.radians(fachada.azimut_normal + phis)
    ux, uy = np.sin(az), np.cos(az)
    divs = np.minimum(np.floor((phis + 90) / ANCHO_DIV + 1e-9).astype(int), N_DIVISIONES - 1) + 1

    adv, omitidas = [], []
    activas, R, IDX, ELEV = [], [], [], []
    for o in obstrucciones:
        poly = Polygon(o.puntos)
        if not poly.is_valid:
            poly = poly.buffer(0)
            adv.append(f"«{o.nombre or o.id}»: polígono con autointersecciones, se corrigió con buffer(0).")
        if poly.contains(Point(O)) or poly.boundary.distance(Point(O)) < 1e-6:
            adv.append(f"«{o.nombre or o.id}» contiene o toca el punto medio de la fachada: se ignora.")
            continue
        A = o.altura - altura_punto_medio
        r, idx = _impactos(O, ux, uy, o.puntos)
        if A <= 0:
            if np.isfinite(r).any():
                omitidas.append({"obstruccion_id": o.id, "nombre": o.nombre or o.id, "division": None, "A": A,
                                 "motivo": f"A = {A:.2f} m ≤ 0: no supera la altura del punto medio de la fachada (no obstruye)."})
            continue
        elev = np.where(np.isfinite(r), np.arctan2(A, np.where(np.isfinite(r), r, 1.0)), -np.inf)
        activas.append(o); R.append(r); IDX.append(idx); ELEV.append(elev)

    tramos: list[Tramo] = []
    if activas:
        E = np.vstack(ELEV)
        dom = np.argmax(E, axis=0)
        valido = np.isfinite(E[dom, np.arange(E.shape[1])])
        for j, o in enumerate(activas):
            A = o.altura - altura_punto_medio
            for k in range(1, N_DIVISIONES + 1):
                en_div = divs == k
                golpea = en_div & np.isfinite(R[j])
                if not golpea.any():
                    continue
                domina = golpea & valido & (dom == j)
                if not domina.any():
                    quien = sorted({activas[int(d)].nombre or activas[int(d)].id for d in dom[golpea & valido]})
                    omitidas.append({"obstruccion_id": o.id, "nombre": o.nombre or o.id, "division": k, "A": A,
                                     "motivo": "Sobrepuesta: otra obstrucción genera mayor ángulo respecto a la horizontal ("
                                               + ", ".join(quien) + "); se omite (manual 6.8.2)."})
                    continue
                parcial = int(golpea.sum()) > int(domina.sum())
                runs = _tramos_continuos(domina)
                for n_run, (a, b) in enumerate(runs, 1):
                    sl = slice(a, b + 1)
                    pts = np.column_stack([O[0] + R[j][sl] * ux[sl], O[1] + R[j][sl] * uy[sl]])
                    edges = IDX[j][sl]
                    m = len(o.puntos)
                    # "Longitud" de la cara visible = ancho de su sombra perpendicular a la visual, de modo que las
                    # caras rasantes a la visual no desplazan el punto medio. Los saltos entre aristas no contiguas no suman.
                    if len(pts) > 1:
                        d = np.diff(pts, axis=0)
                        um = np.column_stack([(ux[sl][1:] + ux[sl][:-1]) / 2, (uy[sl][1:] + uy[sl][:-1]) / 2])
                        seg = np.abs(d[:, 0] * um[:, 1] - d[:, 1] * um[:, 0])
                        de = np.abs(np.diff(edges))
                        cont = (de <= 1) | (de == m - 1)
                        seg = np.where(cont, seg, 0.0)
                        cum = np.r_[0, np.cumsum(seg)]
                    else:
                        cum = np.array([0.0])
                    if cum[-1] > 1e-9:
                        s_med = cum[-1] / 2
                        # índice del punto más cercano en longitud acumulada, interpolando dentro del segmento continuo
                        i = int(np.searchsorted(cum, s_med))
                        i = min(max(i, 1), len(pts) - 1)
                        den = cum[i] - cum[i - 1]
                        f = 0.0 if den < 1e-12 else (s_med - cum[i - 1]) / den
                        pb = pts[i - 1] + f * (pts[i] - pts[i - 1])
                    else:
                        pb = pts[len(pts) // 2]
                    Bv = pb - np.array(O)
                    B = float(np.hypot(*Bv))
                    uB = Bv / B
                    v = np.array([-uB[1], uB[0]])
                    # D = ancho del bloqueo solar: cuerda de la perpendicular a B (por el punto donde termina B)
                    # dentro del cono de visión de la obstrucción en esa división (manual 6.8.2, Fig. 40).
                    phi_b = _rel(azimut(*Bv), fachada.azimut_normal)
                    d_ini = math.radians(float(phis[a]) - phi_b)
                    d_fin = math.radians(float(phis[b]) + paso - phi_b) if b < len(phis) - 1 else math.radians(float(phis[b]) - phi_b)
                    d_ini = math.radians(float(phis[a]) - paso / 2 - phi_b) if a > 0 else d_ini
                    d_fin = math.radians(float(phis[b]) + paso / 2 - phi_b) if b < len(phis) - 1 else d_fin
                    s1, s2 = -B * math.tan(d_ini), -B * math.tan(d_fin)      # posición sobre v (v = B girado +90°)
                    t = np.array([min(s1, s2), max(s1, s2)])
                    D = float(t.max() - t.min())
                    d1, d2 = pb + v * t.min(), pb + v * t.max()
                    notas = []
                    if parcial:
                        notas.append("Parcialmente oculta por otra obstrucción de mayor ángulo; se considera solo el tramo visible.")
                    if len(runs) > 1:
                        notas.append(f"Tramo {n_run} de {len(runs)} (la obstrucción queda partida por otra de mayor ángulo).")
                    if cum[-1] <= 1e-9:
                        notas.append("Tramo visible puntual: D se aproxima con la resolución angular.")
                    tr = Tramo(
                        division=k, obstruccion_id=o.id, nombre=o.nombre or o.id, capa=o.capa, A=A, B=B, D=D,
                        altura_obstruccion=o.altura, angulo_elevacion=math.degrees(math.atan2(A, B)),
                        angulo_b=float(_rel(azimut(*Bv), fachada.azimut_normal)),
                        punto_b=(float(pb[0]), float(pb[1])), p_d1=(float(d1[0]), float(d1[1])), p_d2=(float(d2[0]), float(d2[1])),
                        cara_visible=[(float(x), float(y)) for x, y in pts[:: max(1, len(pts) // 60)]] + [(float(pts[-1][0]), float(pts[-1][1]))],
                        phi_ini=float(phis[a]), phi_fin=float(phis[b]), notas=notas)
                    if criterio_desestimacion == "literal" and (tr.B_sobre_D < UMBRAL_DESESTIMAR or tr.B_sobre_A < UMBRAL_DESESTIMAR):
                        tr.estado = "desestimable"
                    elif criterio_desestimacion == "invertido" and (tr.D_sobre_B < UMBRAL_DESESTIMAR or tr.A_sobre_B < UMBRAL_DESESTIMAR):
                        tr.estado = "desestimable"
                    tramos.append(tr)
    tramos.sort(key=lambda t: (t.division, t.B))
    return ResultadoFachada(fachada, altura_punto_medio, tramos, omitidas, adv, criterio_desestimacion)


def _rel(az: float, eje: float) -> float:
    return (az - eje + 180) % 360 - 180


def resumen_por_division(res: ResultadoFachada) -> dict[int, list[Tramo]]:
    d = {k: [] for k in range(1, N_DIVISIONES + 1)}
    for t in res.tramos:
        d[t.division].append(t)
    return d

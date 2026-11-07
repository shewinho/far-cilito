import math
from shapely.geometry import Polygon, LineString, Point

VERSION_REGLAS = "CEV_2025_Oficial"

class ReglasFAR:
    @staticmethod
    def obtener_tramo_fachada(fachada_puntos, obstaculo_puntos):
        """
        Identifica el tramo o cara de la vivienda que mira hacia el obstáculo
        y obtiene su punto medio fijo y su ángulo normal exterior (Regla MINVU 6.8).
        """
        pts = list(fachada_puntos)
        if len(pts) >= 3 and pts[0] != pts[-1]:
            pts.append(pts[0])
            
        centro_obs = Polygon(obstaculo_puntos).centroid if len(obstaculo_puntos) >= 3 else Point(obstaculo_puntos[0])
        
        # Si es una sola línea (2 puntos), tomamos su punto medio directo
        if len(fachada_puntos) == 2:
            p1, p2 = fachada_puntos[0], fachada_puntos[1]
            pm = Point((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)
            dx, dy = p2[0] - p1[0], p2[1] - p1[1]
            # Vector normal que apunte hacia el obstáculo
            nx, ny = -dy, dx
            if (nx * (centro_obs.x - pm.x) + ny * (centro_obs.y - pm.y)) < 0:
                nx, ny = dy, -dx
            angulo_normal = math.atan2(ny, nx)
            return pm, angulo_normal

        # Si es el polígono de la vivienda, buscamos el muro específico que enfrenta al obstáculo
        poly_casa = Polygon(pts)
        mejor_pm = None
        mejor_normal = 0.0
        menor_dist = float('inf')

        coords = list(poly_casa.exterior.coords)
        centro_casa = poly_casa.centroid

        for i in range(len(coords) - 1):
            p1, p2 = coords[i], coords[i+1]
            seg = LineString([p1, p2])
            if seg.length < 0.1:
                continue
            pm = seg.interpolate(0.5, normalized=True)
            dx, dy = p2[0] - p1[0], p2[1] - p1[1]
            
            # Normal hacia afuera de la casa
            nx, ny = -dy, dx
            if (nx * (pm.x - centro_casa.x) + ny * (pm.y - centro_casa.y)) < 0:
                nx, ny = dy, -dx
                
            # Verificamos si el obstáculo está frente a este muro
            vec_obs_x = centro_obs.x - pm.x
            vec_obs_y = centro_obs.y - pm.y
            dot = nx * vec_obs_x + ny * vec_obs_y
            
            dist = pm.distance(centro_obs)
            if dot > 0 and dist < menor_dist:
                menor_dist = dist
                mejor_pm = pm
                mejor_normal = math.atan2(ny, nx)

        if mejor_pm is None:
            mejor_pm = poly_casa.exterior.interpolate(poly_casa.exterior.project(centro_obs))
            mejor_normal = math.atan2(centro_obs.y - mejor_pm.y, centro_obs.x - mejor_pm.x)

        return mejor_pm, mejor_normal

    @staticmethod
    def construir_sectores_cev(punto_fachada, angulo_normal_rad, radio=200.0):
        """
        Crea los 5 conos de 36° del semicírculo CEV (División 1 a 5 de izq a der mirando desde adentro).
        """
        # Mirando desde el interior hacia afuera:
        # Izquierda es +90° a +54° (Div 1), Derecha es -54° a -90° (Div 5)
        limites_cev = {
            1: (54, 90),
            2: (18, 54),
            3: (-18, 18),
            4: (-54, -18),
            5: (-90, -54)
        }
        sectores = {}
        for div, (ang_min, ang_max) in limites_cev.items():
            pts = [(punto_fachada.x, punto_fachada.y)]
            for paso in range(21):
                ang = ang_min + (ang_max - ang_min) * (paso / 20.0)
                rad = angulo_normal_rad + math.radians(ang)
                pts.append((punto_fachada.x + radio * math.cos(rad),
                            punto_fachada.y + radio * math.sin(rad)))
            pts.append((punto_fachada.x, punto_fachada.y))
            sectores[div] = Polygon(pts)
        return sectores

    @staticmethod
    def calcular_parametros_geometricos(fachada_puntos, obstaculo_puntos, obstaculo_capa="", h_fachada=1.5):
        poly_obs = Polygon(obstaculo_puntos)
        punto_fachada, angulo_normal = ReglasFAR.obtener_tramo_fachada(fachada_puntos, obstaculo_puntos)
        sectores = ReglasFAR.construir_sectores_cev(punto_fachada, angulo_normal)

        # Altura según capa por defecto (editable en la barra lateral)
        capa_up = obstaculo_capa.upper()
        h_obs = 15.0 if "EDIFICIO" in capa_up else (3.0 if "ELEMENTO" in capa_up else 5.0)
        altura_a = max(0.0, h_obs - h_fachada)

        divisiones_afectadas = []

        for div_num, poly_sector in sectores.items():
            recorte = poly_obs.intersection(poly_sector)
            if recorte.is_empty or recorte.area < 0.05:
                continue

            # Punto medio de la porción del obstáculo dentro de esta división (Figura 39 CEV)
            punto_obstaculo = recorte.centroid
            distancia_b = punto_fachada.distance(punto_obstaculo)

            # Dirección de la línea B
            dx = punto_obstaculo.x - punto_fachada.x
            dy = punto_obstaculo.y - punto_fachada.y
            angulo_b_rad = math.atan2(dy, dx)

            # Línea D: 90° perpendicular a la línea B pasando por el centro de la obstrucción (Figura 40 CEV)
            angulo_perp = angulo_b_rad + math.pi / 2
            largo = 150.0
            p1 = Point(punto_obstaculo.x - largo * math.cos(angulo_perp),
                       punto_obstaculo.y - largo * math.sin(angulo_perp))
            p2 = Point(punto_obstaculo.x + largo * math.cos(angulo_perp),
                       punto_obstaculo.y + largo * math.sin(angulo_perp))
            linea_perp = LineString([p1, p2])

            inter_d = linea_perp.intersection(recorte)
            if inter_d.is_empty:
                p_D1, p_D2 = punto_obstaculo, punto_obstaculo
                ancho_d = 0.0
            else:
                # Extraemos los puntos extremos del cruce perpendicular dentro de la división
                coords_d = []
                if hasattr(inter_d, 'geoms'):
                    for g in inter_d.geoms:
                        coords_d.extend(list(g.coords))
                else:
                    coords_d = list(inter_d.coords)
                p_D1 = Point(coords_d[0])
                p_D2 = Point(coords_d[-1])
                ancho_d = p_D1.distance(p_D2)

            # Ángulo relativo respecto a la normal de la fachada
            dif_ang = math.degrees(angulo_b_rad - angulo_normal)
            while dif_ang > 180: dif_ang -= 360
            while dif_ang < -180: dif_ang += 360

            divisiones_afectadas.append({
                "B": round(distancia_b, 2),
                "D": round(ancho_d, 2),
                "A": round(altura_a, 2),
                "division": div_num,
                "angulo": round(-dif_ang, 2),
                "punto_fachada": (punto_fachada.x, punto_fachada.y),
                "punto_obstaculo": (punto_obstaculo.x, punto_obstaculo.y),
                "p_D1": (p_D1.x, p_D1.y),
                "p_D2": (p_D2.x, p_D2.y),
                "angulo_rad_B": angulo_normal, # El semicírculo queda fijo mirando al frente de la fachada
                "todas_las_divisiones": divisiones_afectadas
            })

        # Si el obstáculo estaba detrás de la fachada o fuera del semicírculo de 180°
        if not divisiones_afectadas:
            po_fallback = poly_obs.centroid
            return {
                "B": round(punto_fachada.distance(po_fallback), 2),
                "D": 0.0,
                "A": round(altura_a, 2),
                "division": 3,
                "angulo": 0.0,
                "punto_fachada": (punto_fachada.x, punto_fachada.y),
                "punto_obstaculo": (po_fallback.x, po_fallback.y),
                "p_D1": (po_fallback.x, po_fallback.y),
                "p_D2": (po_fallback.x, po_fallback.y),
                "angulo_rad_B": angulo_normal,
                "todas_las_divisiones": []
            }

        # Devolvemos la división principal (y adentro lleva guardadas todas si cruza más de una)
        return divisiones_afectadas[0]

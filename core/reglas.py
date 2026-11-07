import math
from shapely.geometry import Polygon, LineString, Point

VERSION_REGLAS = "CEV_2025_Borrador"

class ReglasFAR:
    @staticmethod
    def calcular_centro_polilinea(puntos):
        x_vals = [p[0] for p in puntos]
        y_vals = [p[1] for p in puntos]
        return (sum(x_vals) / len(x_vals), sum(y_vals) / len(y_vals))

    @staticmethod
    def calcular_parametros_geometricos(fachada_puntos, obstaculo_puntos, obstaculo_capa=""):
        poly_casa = Polygon(fachada_puntos)
        poly_obs = Polygon(obstaculo_puntos)
        
        centro_obs = ReglasFAR.calcular_centro_polilinea(obstaculo_puntos)
        
        # 1. Punto medio de la fachada (borde de la casa más cercano al obstáculo)
        punto_fachada = poly_casa.exterior.interpolate(poly_casa.exterior.project(Point(centro_obs)))
        
        # 2. Punto de intersección en el obstáculo (borde más cercano)
        punto_obstaculo = poly_obs.exterior.interpolate(poly_obs.exterior.project(punto_fachada))
        
        # 3. Distancia B
        distancia_b = punto_fachada.distance(punto_obstaculo)
        
        # 4. Ángulo B y División (Calculado desde el punto de la fachada al obstáculo)
        dx = punto_obstaculo.x - punto_fachada.x
        dy = punto_obstaculo.y - punto_fachada.y
        angulo_rad = math.atan2(dy, dx)
        
        # Convertimos a grados CEV (Norte = 0, Este = 90)
        angulo_grados = math.degrees(angulo_rad)
        angulo_cev = 90 - angulo_grados
        if angulo_cev < -180: angulo_cev += 360
        if angulo_cev > 180: angulo_cev -= 360

        # Determinamos la división
        if -90 <= angulo_cev < -54: division = 1
        elif -54 <= angulo_cev < -18: division = 2
        elif -18 <= angulo_cev < 18: division = 3
        elif 18 <= angulo_cev < 54: division = 4
        elif 54 <= angulo_cev <= 90: division = 5
        else: division = 0

        # 5. Perpendicular D
        angulo_perp = angulo_rad + math.pi / 2
        largo_perp = 100
        p1 = Point(punto_obstaculo.x - largo_perp * math.cos(angulo_perp), 
                   punto_obstaculo.y - largo_perp * math.sin(angulo_perp))
        p2 = Point(punto_obstaculo.x + largo_perp * math.cos(angulo_perp), 
                   punto_obstaculo.y + largo_perp * math.sin(angulo_perp))
        linea_perp = LineString([p1, p2])
        
        interseccion = linea_perp.intersection(poly_obs.exterior)
        
        if interseccion.geom_type == 'MultiPoint':
            puntos_D = list(interseccion.geoms)
            p_D1, p_D2 = puntos_D[0], puntos_D[-1]
            ancho_d = p_D1.distance(p_D2)
        elif interseccion.geom_type == 'Point':
            p_D1, p_D2 = interseccion, interseccion
            ancho_d = 0
        else:
            p_D1, p_D2 = punto_obstaculo, punto_obstaculo
            ancho_d = 0

        altura_a = 15.0 if "EDIFICIO_B" in obstaculo_capa.upper() else (3.0 if "ELEMENTOS" in obstaculo_capa.upper() else 5.0)
            
        return {
            "B": round(distancia_b, 2),
            "D": round(ancho_d, 2),
            "A": altura_a,
            "division": division,
            "angulo": round(angulo_cev, 2),
            "punto_fachada": (punto_fachada.x, punto_fachada.y),
            "punto_obstaculo": (punto_obstaculo.x, punto_obstaculo.y),
            "p_D1": (p_D1.x, p_D1.y),
            "p_D2": (p_D2.x, p_D2.y),
            "angulo_rad_B": angulo_rad # Guardamos el ángulo en radianes para el gráfico
        }

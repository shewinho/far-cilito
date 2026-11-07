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
        """
        Calcula A, B, D y las coordenadas exactas de la línea B y la perpendicular D.
        """
        poly_casa = Polygon(fachada_puntos)
        poly_obs = Polygon(obstaculo_puntos)
        
        # 1. Centroide del obstáculo (para saber hacia dónde mirar)
        centro_obs = ReglasFAR.calcular_centro_polilinea(obstaculo_puntos)
        
        # 2. Punto medio de la fachada: 
        # Buscamos el punto del borde de la casa más cercano al obstáculo
        punto_fachada = poly_casa.exterior.interpolate(poly_casa.exterior.project(Point(centro_obs)))
        
        # 3. Punto de intersección en el obstáculo:
        # El punto del borde del obstáculo más cercano a la fachada
        punto_obstaculo = poly_obs.exterior.interpolate(poly_obs.exterior.project(punto_fachada))
        
        # 4. Calcular Distancia B
        distancia_b = punto_fachada.distance(punto_obstaculo)
        
        # 5. Calcular Perpendicular D:
        # Creamos una línea larga perpendicular a B, que pase por punto_obstaculo
        dx = punto_obstaculo.x - punto_fachada.x
        dy = punto_obstaculo.y - punto_fachada.y
        angulo = math.atan2(dy, dx)
        angulo_perp = angulo + math.pi / 2
        
        # Línea perpendicular temporal
        largo_perp = 100 # Más grande que cualquier edificio
        p1 = Point(punto_obstaculo.x - largo_perp * math.cos(angulo_perp), 
                   punto_obstaculo.y - largo_perp * math.sin(angulo_perp))
        p2 = Point(punto_obstaculo.x + largo_perp * math.cos(angulo_perp), 
                   punto_obstaculo.y + largo_perp * math.sin(angulo_perp))
        
        linea_perp = LineString([p1, p2])
        
        # Intersectamos la perpendicular con el obstáculo
        interseccion = linea_perp.intersection(poly_obs.exterior)
        
        # Si la línea cruza el obstáculo, tomamos los puntos extremos
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

        # Alturas (simuladas por capa)
        altura_a = 15.0 if "EDIFICIO_B" in obstaculo_capa.upper() else (3.0 if "ELEMENTOS" in obstaculo_capa.upper() else 5.0)
            
        return {
            "B": round(distancia_b, 2),
            "D": round(ancho_d, 2),
            "A": altura_a,
            "punto_fachada": (punto_fachada.x, punto_fachada.y),
            "punto_obstaculo": (punto_obstaculo.x, punto_obstaculo.y),
            "p_D1": (p_D1.x, p_D1.y),
            "p_D2": (p_D2.x, p_D2.y)
        }

    @staticmethod
    def calcular_division_obstaculo(fachada_puntos, obstaculo_puntos):
        # Usamos el centroide de la casa para el ángulo (simplificación)
        centro_fachada = ReglasFAR.calcular_centro_polilinea(fachada_puntos)
        centro_obstaculo = ReglasFAR.calcular_centro_polilinea(obstaculo_puntos)
        
        dx = centro_obstaculo[0] - centro_fachada[0]
        dy = centro_obstaculo[1] - centro_fachada[1]
        
        angulo_rad = math.atan2(dy, dx)
        angulo_grados = math.degrees(angulo_rad)
        angulo_cev = 90 - angulo_grados 
        
        if angulo_cev < -90: angulo_cev += 360
        elif angulo_cev > 180: angulo_cev -= 360
            
        if -90 <= angulo_cev < -54: return 1, round(angulo_cev, 2)
        elif -54 <= angulo_cev < -18: return 2, round(angulo_cev, 2)
        elif -18 <= angulo_cev < 18: return 3, round(angulo_cev, 2)
        elif 18 <= angulo_cev < 54: return 4, round(angulo_cev, 2)
        elif 54 <= angulo_cev <= 90: return 5, round(angulo_cev, 2)
        else: return 0, round(angulo_cev, 2)

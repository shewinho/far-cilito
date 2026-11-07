import math

VERSION_REGLAS = "CEV_2025_Borrador"

class ReglasFAR:
    @staticmethod
    def calcular_centro_polilinea(puntos):
        x_vals = [p[0] for p in puntos]
        y_vals = [p[1] for p in puntos]
        return (sum(x_vals) / len(x_vals), sum(y_vals) / len(y_vals))

    @staticmethod
    def calcular_parametros_geometricos(fachada_puntos, obstaculo_puntos, obstaculo_capa=""):
        centro_fachada = ReglasFAR.calcular_centro_polilinea(fachada_puntos)
        centro_obstaculo = ReglasFAR.calcular_centro_polilinea(obstaculo_puntos)
        
        distancia_b = math.dist(centro_fachada, centro_obstaculo)
        
        x_vals_obs = [p[0] for p in obstaculo_puntos]
        y_vals_obs = [p[1] for p in obstaculo_puntos]
        ancho_d = max(x_vals_obs) - min(x_vals_obs) 
        
        altura_a = 0.0
        capa_upper = obstaculo_capa.upper()
        
        if "EDIFICIO_B" in capa_upper:
            altura_a = 15.0
        elif "ELEMENTOS" in capa_upper:
            altura_a = 3.0
        else:
            altura_a = 5.0
            
        return {
            "B": round(distancia_b, 2),
            "D": round(ancho_d, 2),
            "A": altura_a
        }

    @staticmethod
    def calcular_division_obstaculo(fachada_puntos, obstaculo_puntos):
        centro_fachada = ReglasFAR.calcular_centro_polilinea(fachada_puntos)
        centro_obstaculo = ReglasFAR.calcular_centro_polilinea(obstaculo_puntos)
        
        dx = centro_obstaculo[0] - centro_fachada[0]
        dy = centro_obstaculo[1] - centro_fachada[1]
        
        angulo_rad = math.atan2(dy, dx)
        angulo_grados = math.degrees(angulo_rad)
        
        angulo_cev = 90 - angulo_grados 
        
        if angulo_cev < -90:
            angulo_cev += 360
        elif angulo_cev > 180:
            angulo_cev -= 360
            
        if -90 <= angulo_cev < -54:
            return 1, round(angulo_cev, 2)
        elif -54 <= angulo_cev < -18:
            return 2, round(angulo_cev, 2)
        elif -18 <= angulo_cev < 18:
            return 3, round(angulo_cev, 2)
        elif 18 <= angulo_cev < 54:
            return 4, round(angulo_cev, 2)
        elif 54 <= angulo_cev <= 90:
            return 5, round(angulo_cev, 2)
        else:
            return 0, round(angulo_cev, 2)

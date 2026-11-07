import math

VERSION_REGLAS = "CEV_2025_Borrador"

class ReglasFAR:
    @staticmethod
    def calcular_centro_polilinea(puntos):
        """Calcula el centro aproximado (caja contenedora) de una polilínea"""
        x_vals = [p[0] for p in puntos]
        y_vals = [p[1] for p in puntos]
        return (sum(x_vals) / len(x_vals), sum(y_vals) / len(y_vals))

    @staticmethod
    def calcular_parametros_geometricos(fachada_puntos, obstaculo_puntos):
        """
        Calcula A, B y D aproximados basándose en la geometría.
        ADVERTENCIA: Esta es una aproximación geométrica básica.
        La validación oficial requiere interpretar el manual CEV al pie de la letra.
        """
        centro_fachada = ReglasFAR.calcular_centro_polilinea(fachada_puntos)
        centro_obstaculo = ReglasFAR.calcular_centro_polilinea(obstaculo_puntos)
        
        # Distancia B (Distancia entre centros)
        distancia_b = math.dist(centro_fachada, centro_obstaculo)
        
        # Ancho D (Ancho máximo del obstáculo)
        x_vals_obs = [p[0] for p in obstaculo_puntos]
        y_vals_obs = [p[1] for p in obstaculo_puntos]
        ancho_d = max(x_vals_obs) - min(x_vals_obs) # Asumiendo que el ancho es en X
        
        # Altura A (El manual pide la diferencia de altura. Como el DXF es 2D, 
        # necesitamos que el usuario ingrese la altura real del edificio).
        # Por ahora, dejamos A como un valor que el usuario debe completar.
        
        return {
            "B": round(distancia_b, 2),
            "D": round(ancho_d, 2),
            "A": 0.0 # Pendiente de ingreso manual o lectura de IFC 3D
        }

    @staticmethod
    def calcular_far_final(parametros):
        raise NotImplementedError(
            "El cálculo final del FAR requiere la ecuación oficial validada por el MINVU."
        )

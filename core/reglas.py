import math

VERSION_REGLAS = "CEV_2025_Borrador"

class ReglasFAR:
    @staticmethod
    def calcular_centro_polilinea(puntos):
        """Calcula el centro (caja contenedora) de una polilínea"""
        x_vals = [p[0] for p in puntos]
        y_vals = [p[1] for p in puntos]
        return (sum(x_vals) / len(x_vals), sum(y_vals) / len(y_vals))

    @staticmethod
    def calcular_parametros_geometricos(fachada_puntos, obstaculo_puntos, obstaculo_capa=""):
        """
        Calcula A, B y D.
        """
        centro_fachada = ReglasFAR.calcular_centro_polilinea(fachada_puntos)
        centro_obstaculo = ReglasFAR.calcular_centro_polilinea(obstaculo_puntos)
        
        # Distancia B (Distancia entre centros)
        distancia_b = math.dist(centro_fachada, centro_obstaculo)
        
        # Ancho D (Ancho máximo del obstáculo)
        x_vals_obs = [p[0] for p in obstaculo_puntos]
        y_vals_obs = [p[1] for p in obstaculo_puntos]
        ancho_d = max(x_vals_obs) - min(x_vals_obs) 
        
        # --- LÓGICA DE ALTURA AUTOMÁTICA (Basada en la capa) ---
        altura_a = 0.0
        capa_upper = obstaculo_capa.upper()
        
        if "EDIFICIO_B" in capa_upper:
            altura_a = 15.0 # Altura del Edificio B
        elif "ELEMENTOS" in capa_upper:
            altura_a = 3.0  # Altura de los elementos
        else:
            altura_a = 5.0  # Altura por defecto si no se reconoce
            
        return {
            "B": round(distancia_b, 2),
            "D": round(ancho_d, 2),
            "A": altura_a
        }

    @staticmethod
    def calcular_far_final(parametros):
        raise NotImplementedError(
            "El cálculo final del FAR requiere la ecuación oficial validada por el MINVU."
        )

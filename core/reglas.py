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
    def calcular_division_obstaculo(fachada_puntos, obstaculo_puntos):
        """
        Calcula en qué división (1 a 5) cae el obstáculo.
        Asumimos que la fachada mira hacia el Norte (0°) para esta prueba.
        """
        import math
        
        centro_fachada = ReglasFAR.calcular_centro_polilinea(fachada_puntos)
        centro_obstaculo = ReglasFAR.calcular_centro_polilinea(obstaculo_puntos)
        
        # Calcular el ángulo entre la fachada y el obstáculo
        dx = centro_obstaculo[0] - centro_fachada[0]
        dy = centro_obstaculo[1] - centro_fachada[1]
        
        # Ángulo en radianes y luego a grados
        angulo_rad = math.atan2(dy, dx)
        angulo_grados = math.degrees(angulo_rad)
        
        # Ajustar para que el Norte (eje Y) sea 0°
        # Si el obstáculo está a la izquierda, ángulo positivo. A la derecha, negativo.
        angulo_cev = 90 - angulo_grados 
        
        # Si el ángulo sale negativo (derecha), lo convertimos a 0-180
        if angulo_cev < -90:
            angulo_cev += 360
        elif angulo_cev > 180:
            angulo_cev -= 360
            
        # Determinar división (de -90 a 90 grados, 5 divisiones de 36 grados)
        # División 1: -90 a -54
        # División 2: -54 a -18
        # División 3: -18 a +18
        # División 4: +18 a +54
        # División 5: +54 a +90
        
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
            return 0, round(angulo_cev, 2) # Fuera del semicírculo (ej. atrás)
    def calcular_far_final(parametros):
        raise NotImplementedError(
            "El cálculo final del FAR requiere la ecuación oficial validada por el MINVU."
        )

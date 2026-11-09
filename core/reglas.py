import math
from shapely.geometry import Polygon, LineString, Point
from collections import defaultdict

VERSION_REGLAS = "CEV_2025_Oficial_MultiDir"

class ReglasFAR:
    @staticmethod
    def asegurar_poligono(puntos):
        pts = list(puntos)
        if len(pts) < 3:
            return LineString(pts).buffer(0.05)
        if pts[0] != pts[-1]:
            pts.append(pts[0])
        poly = Polygon(pts)
        if not poly.is_valid:
            poly = poly.buffer(0)
        return poly

    @staticmethod
    def obtener_tramo_fachada(fachada_puntos, obstaculo_puntos=None, orientacion_fija=None):
        poly_casa = ReglasFAR.asegurar_poligono(fachada_puntos)
        centro_casa = poly_casa.centroid

        if orientacion_fija is not None:
            coords = list(poly_casa.exterior.coords)
            mejor_pm = None
            max_proy = -float('inf')
            nx = math.cos(math.radians(orientacion_fija))
            ny = math.sin(math.radians(orientacion_fija))
            
            for i in range(len(coords) - 1):
                p1, p2 = coords[i], coords[i+1]
                seg = LineString([p1, p2])
                if seg.length < 0.1: continue
                pm = seg.interpolate(0.5, normalized=True)
                proy = (pm.x - centro_casa.x) * nx + (pm.y - centro_casa.y) * ny
                if proy > max_proy:
                    max_proy = proy
                    mejor_pm = pm
            return mejor_pm, math.radians(orientacion_fija)

        poly_obs = ReglasFAR.asegurar_poligono(obstaculo_puntos)
        centro_obs = poly_obs.centroid
        mejor_pm = poly_casa.exterior.interpolate(poly_casa.exterior.project(centro_obs))
        mejor_normal = math.atan2(centro_obs.y - mejor_pm.y, centro_obs.x - mejor_pm.x)
        return mejor_pm, mejor_normal

    @staticmethod
    def construir_sectores_cev(punto_fachada, angulo_normal_rad, radio=500.0):
        limites_cev = {1: (54, 90), 2: (18, 54), 3: (-18, 18), 4: (-54, -18), 5: (-90, -54)}
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
    def calcular_parametros_geometricos(fachada_puntos, obstaculo_puntos, obstaculo_capa="", h_fachada=1.5, orientacion_fija=None, h_custom=None, radio_busqueda=500.0):
        poly_obs = ReglasFAR.asegurar_poligono(obstaculo_puntos)
        punto_fachada, angulo_normal = ReglasFAR.obtener_tramo_fachada(fachada_puntos, obstaculo_puntos, orientacion_fija)
        sectores = ReglasFAR.construir_sectores_cev(punto_fachada, angulo_normal, radio=radio_busqueda)

        if h_custom is not None:
            h_obs = h_custom
        else:
            capa_up = obstaculo_capa.upper()
            h_obs = 15.0 if "EDIFICIO" in capa_up else (3.0 if "ELEMENTO" in capa_up else 5.0)
            
        altura_a = max(0.0, h_obs - h_fachada)
        divisiones_afectadas = []

        for div_num, poly_sector in sectores.items():
            recorte = poly_obs.intersection(poly_sector)
            if recorte.is_empty or recorte.area < 0.05: continue

            poly_recorte = recorte if recorte.geom_type == 'Polygon' else max(recorte.geoms, key=lambda g: g.area)
            coords_ext = list(poly_recorte.exterior.coords)
            
            best_seg_mid = poly_recorte.centroid
            min_seg_dist = float('inf')
            for j in range(len(coords_ext) - 1):
                seg = LineString([coords_ext[j], coords_ext[j+1]])
                if seg.length < 0.01: continue
                pm_seg = seg.interpolate(0.5, normalized=True)
                d = Point(punto_fachada).distance(pm_seg)
                if d < min_seg_dist:
                    min_seg_dist = d
                    best_seg_mid = (pm_seg.x, pm_seg.y)

            punto_obstaculo = Point(best_seg_mid)
            distancia_b = punto_fachada.distance(punto_obstaculo)

            dx = punto_obstaculo.x - punto_fachada.x
            dy = punto_obstaculo.y - punto_fachada.y
            angulo_b_rad = math.atan2(dy, dx)

            angulo_perp = angulo_b_rad + math.pi / 2.0
            nx_perp = math.cos(angulo_perp)
            ny_perp = math.sin(angulo_perp)
            
            min_proy = float('inf')
            max_proy = -float('inf')
            
            for pt in coords_ext:
                proy = (pt[0] - punto_obstaculo.x) * nx_perp + (pt[1] - punto_obstaculo.y) * ny_perp
                if proy < min_proy: min_proy = proy
                if proy > max_proy: max_proy = proy
                
            ancho_d = max_proy - min_proy
            
            p_d1 = (punto_obstaculo.x + min_proy * nx_perp, punto_obstaculo.y + min_proy * ny_perp)
            p_d2 = (punto_obstaculo.x + max_proy * nx_perp, punto_obstaculo.y + max_proy * ny_perp)

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
                "p_D1": p_d1,
                "p_D2": p_d2,
                "angulo_rad_B": angulo_normal,
                "h_obs": h_obs
            })

        return divisiones_afectadas

    @staticmethod
    def escanear_entorno(fachada_puntos, lista_obstaculos, h_fachada=1.5, radio_busqueda=500.0):
        orientaciones = {
            "Norte": 90, "NE": 45, "Este": 0, "SE": -45,
            "Sur": -90, "SO": -135, "Oeste": 180, "NO": 135
        }
        resultados_totales = {}

        for nombre_ori, angulo_ori in orientaciones.items():
            divisiones_ori = defaultdict(list)
            for obs in lista_obstaculos:
                res_obs = ReglasFAR.calcular_parametros_geometricos(
                    fachada_puntos, obs['puntos'], obs['capa'], h_fachada, 
                    orientacion_fija=angulo_ori, radio_busqueda=radio_busqueda, h_custom=obs.get('h_custom')
                )
                for div in res_obs:
                    div['id_obs'] = obs['handle']
                    divisiones_ori[div['division']].append(div)
            
            resultado_filtrado = []
            for div_num, obstrucciones in divisiones_ori.items():
                if not obstrucciones: continue
                for ob in obstrucciones:
                    ob['elev_angle'] = math.atan(ob['A'] / ob['B']) if ob['B'] > 0 else (math.pi / 2)
                obs_ganadora = max(obstrucciones, key=lambda x: x['elev_angle'])
                resultado_filtrado.append(obs_ganadora)
                
            if resultado_filtrado:
                resultados_totales[nombre_ori] = resultado_filtrado

        return resultados_totales
        

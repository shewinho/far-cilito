import ezdxf

class ImportadorDXF:
    def __init__(self, ruta_archivo):
        self.doc = ezdxf.readfile(ruta_archivo)
        self.msp = self.doc.modelspace()
        self.entidades = []

    def extraer_geometria(self):
        for e in self.msp:
            if e.dxftype() == 'LINE':
                start = e.dxf.start
                end = e.dxf.end
                self.entidades.append({
                    'tipo': 'linea',
                    'handle': e.dxf.handle,
                    'capa': e.dxf.layer,
                    'puntos': [(start.x, start.y), (end.x, end.y)]
                })
            elif e.dxftype() == 'LWPOLYLINE':
                puntos = [(p[0], p[1]) for p in e.get_points()]
                self.entidades.append({
                    'tipo': 'polilinea',
                    'handle': e.dxf.handle,
                    'capa': e.dxf.layer,
                    'puntos': puntos
                })
        return self.entidades

"""Importador: contornos de líneas sueltas con ruido de redondeo y líneas realmente abiertas."""
import ezdxf
import pytest

from core.importador import ImportadorDXF

BASE_X, BASE_Y = 4.0e5, 1.7e5   # coordenadas grandes, como un plano georreferenciado
RUIDO = 1e-10                   # discrepancia típica entre extremos que deberían coincidir


def _rectangulo(msp, x0, y0, ancho=3.0, alto=1.5):
    """Cuatro LINE que dibujan un rectángulo; algunas esquinas con ruido de redondeo."""
    c = [(x0, y0), (x0 + ancho, y0), (x0 + ancho, y0 + alto), (x0, y0 + alto)]
    for k in range(4):
        a, b = c[k], c[(k + 1) % 4]
        if k % 2:                       # la mitad de los empalmes quedan desplazados ~1e-10
            a = (a[0] + RUIDO, a[1] + RUIDO)
        msp.add_line(a, b, dxfattribs={"layer": "OBSTRUCCIONES"})


@pytest.fixture()
def dxf(tmp_path):
    doc = ezdxf.new("R2010")
    doc.layers.add("OBSTRUCCIONES")
    doc.layers.add("ABIERTAS")
    msp = doc.modelspace()
    for k in range(4):
        _rectangulo(msp, BASE_X + 20.0 * k, BASE_Y)
    # rectángulo al que le falta un lado: no debe generar contorno, pero sí contarse
    x0, y0 = BASE_X, BASE_Y - 50.0
    msp.add_line((x0, y0), (x0 + 8.0, y0), dxfattribs={"layer": "ABIERTAS"})
    msp.add_line((x0 + 8.0, y0), (x0 + 8.0, y0 + 4.0), dxfattribs={"layer": "ABIERTAS"})
    msp.add_line((x0 + 8.0, y0 + 4.0), (x0, y0 + 4.0), dxfattribs={"layer": "ABIERTAS"})
    ruta = tmp_path / "grande.dxf"
    doc.saveas(ruta)
    return ruta


def test_cuatro_rectangulos_con_ruido(dxf):
    objetos = ImportadorDXF(dxf).extraer_objetos()
    obs = [o for o in objetos if o["capa"] == "OBSTRUCCIONES"]
    assert len(obs) == 4
    assert {o["id"] for o in obs} == {f"LN:OBSTRUCCIONES:{k}" for k in range(1, 5)}
    for o in obs:
        assert len(o["puntos"]) >= 3
        # el ruido de 1e-10 no altera el tamaño del rectángulo
        xs = [p[0] for p in o["puntos"]]
        ys = [p[1] for p in o["puntos"]]
        assert max(xs) - min(xs) == pytest.approx(3.0)
        assert max(ys) - min(ys) == pytest.approx(1.5)


def test_lineas_abiertas_no_forman_contorno_y_se_cuentan(dxf):
    imp = ImportadorDXF(dxf)
    objetos = imp.extraer_objetos()
    assert not any(o["capa"] == "ABIERTAS" for o in objetos)
    assert len(imp.lineas_sin_contorno["ABIERTAS"]) == 3
    assert "OBSTRUCCIONES" not in imp.lineas_sin_contorno

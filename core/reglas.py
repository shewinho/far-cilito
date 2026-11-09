"""Reglas CEV usadas por FARcilito.

La geometría (divisiones, A, B, D) vive en core/far.py. Este módulo conserva la versión de las reglas y el
punto bloqueado del cálculo final.
"""
VERSION_REGLAS = "CEV_2025_Manual_6.8"   # Manual de Procedimientos CEV (ed. 2025), secciones 6.8 y 11.8


def calcular_far(*_args, **_kwargs):
    """El manual NO incluye la ecuación que convierte A, B y D (por división) en el factor FAR.

    No se inventa: queda bloqueado hasta validar la ecuación oficial con MINVU.
    """
    raise NotImplementedError("Ecuación FAR(A, B, D) pendiente de validación con MINVU.")

"""Genera un dataset SINTÉTICO de ausentismo en turnos médicos.

No tenemos datos reales de un consultorio, así que se simula una población de
turnos usando supuestos razonables (basados en lo que describe el SRS):

* Cuantos más días pasan entre que se reserva y el turno, más probable es faltar.
* Quien ya faltó antes tiene más probabilidad de volver a faltar.
* Los horarios de primera y última hora y los lunes/viernes tienen más ausencias.
* A mayor edad, algo menos de ausentismo.

El resultado se guarda en ml/dataset_ausentismo.csv. Ejecutar desde la raíz:

    python ml/generar_dataset.py
"""
from pathlib import Path

import numpy as np
import pandas as pd

CARPETA = Path(__file__).resolve().parent
RUTA_CSV = CARPETA / "dataset_ausentismo.csv"

SEMILLA = 42
CANTIDAD = 6000


def generar(n=CANTIDAD, semilla=SEMILLA):
    rng = np.random.default_rng(semilla)

    dias_anticipacion = rng.integers(0, 61, n)        # días entre reserva y turno
    hora = rng.integers(9, 17, n)                     # hora del turno: 9 a 16
    dia_semana = rng.integers(0, 5, n)                # 0 = lunes ... 4 = viernes
    edad = np.clip(rng.normal(40, 20, n), 1, 90).round().astype(int)
    ausencias_previas = np.clip(rng.poisson(0.4, n), 0, 5)

    z = (
        -2.9
        + 0.028 * dias_anticipacion
        + 0.70 * ausencias_previas
        - 0.010 * (edad - 40)
        + 0.35 * (hora == 9)
        + 0.30 * (hora == 16)
        + 0.30 * np.isin(dia_semana, [0, 4])
    )
    probabilidad = 1 / (1 + np.exp(-z))
    ausente = (rng.random(n) < probabilidad).astype(int)

    return pd.DataFrame(
        {
            "dias_anticipacion": dias_anticipacion,
            "hora": hora,
            "dia_semana": dia_semana,
            "edad": edad,
            "ausencias_previas": ausencias_previas,
            "ausente": ausente,
        }
    )


if __name__ == "__main__":
    datos = generar()
    datos.to_csv(RUTA_CSV, index=False)
    print(f"Dataset sintético guardado en {RUTA_CSV}")
    print(f"Registros: {len(datos)} | tasa de ausentismo: {datos['ausente'].mean():.1%}")
"""Carga del modelo de IA y predicción de ausentismo en tiempo real.

El modelo (regresión logística de scikit-learn) se entrena antes con
ml/entrenar_modelo.py, se guarda con joblib y se carga UNA vez al iniciar la app.
"""
import json
import logging

import joblib
import pandas as pd

log = logging.getLogger(__name__)

# Umbrales de la probabilidad de ausencia para clasificar el riesgo.
UMBRAL_MEDIO = 0.15
UMBRAL_ALTO = 0.30


def nivel_riesgo(probabilidad):
    """Devuelve 'bajo', 'medio' o 'alto' (o None si no hay predicción)."""
    if probabilidad is None:
        return None
    if probabilidad >= UMBRAL_ALTO:
        return "alto"
    if probabilidad >= UMBRAL_MEDIO:
        return "medio"
    return "bajo"


class Predictor:
    def __init__(self):
        self.modelo = None
        self.columnas = []
        self.metricas = {}

    def init_app(self, app):
        try:
            self.modelo = joblib.load(app.config["MODELO_PATH"])
            self.columnas = list(self.modelo.feature_names_in_)
            log.info("Modelo de ausentismo cargado: %s", app.config["MODELO_PATH"])
        except Exception as error:  # modelo ausente o incompatible: la app sigue funcionando
            self.modelo = None
            self.columnas = []
            log.warning("No se pudo cargar el modelo de IA: %s", error)

        try:
            with open(app.config["METRICAS_PATH"], encoding="utf-8") as archivo:
                self.metricas = json.load(archivo)
        except (OSError, ValueError):
            self.metricas = {}

    @property
    def disponible(self):
        return self.modelo is not None

    def predecir(self, **datos):
        """Recibe las variables del modelo y devuelve la probabilidad de ausencia."""
        if not self.disponible:
            raise RuntimeError("El modelo de IA no está disponible.")
        fila = pd.DataFrame([[datos[c] for c in self.columnas]], columns=self.columnas)
        probabilidad = float(self.modelo.predict_proba(fila)[0][1])
        return {"probabilidad": round(probabilidad, 4), "nivel": nivel_riesgo(probabilidad)}


# Instancia única que usan la app y los servicios.
predictor = Predictor()
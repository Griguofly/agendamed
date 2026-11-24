"""Entrena el modelo de ausentismo y lo guarda con joblib.

Modelo: regresión logística (scikit-learn) que estima la probabilidad de que un
paciente NO se presente a un turno. Se guarda como Pipeline (escalado + modelo)
en ml/modelo_ausentismo.joblib; la app de Flask lo carga al iniciar.

Ejecutar desde la raíz del proyecto:

    python ml/entrenar_modelo.py
"""
import json
from pathlib import Path

import joblib
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from generar_dataset import RUTA_CSV, generar

CARPETA = Path(__file__).resolve().parent
RUTA_MODELO = CARPETA / "modelo_ausentismo.joblib"
RUTA_METRICAS = CARPETA / "metricas.json"

FEATURES = ["dias_anticipacion", "hora", "dia_semana", "edad", "ausencias_previas"]
OBJETIVO = "ausente"


def main():
    if RUTA_CSV.exists():
        datos = pd.read_csv(RUTA_CSV)
    else:
        datos = generar()
        datos.to_csv(RUTA_CSV, index=False)

    X = datos[FEATURES]
    y = datos[OBJETIVO]
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    modelo = Pipeline(
        [
            ("escalado", StandardScaler()),
            ("regresion_logistica", LogisticRegression(max_iter=1000)),
        ]
    )
    modelo.fit(X_train, y_train)

    probabilidades = modelo.predict_proba(X_test)[:, 1]
    predicciones = (probabilidades >= 0.5).astype(int)
    metricas = {
        "modelo": "Regresión logística (scikit-learn)",
        "registros_entrenamiento": int(len(X_train)),
        "registros_prueba": int(len(X_test)),
        "tasa_ausentismo": round(float(y.mean()), 4),
        "accuracy": round(float(accuracy_score(y_test, predicciones)), 4),
        # Accuracy de un "modelo" que siempre dice "va a asistir": sirve de referencia,
        # porque con 19 % de ausentismo la accuracy sola engaña.
        "accuracy_siempre_asiste": round(float(1 - y_test.mean()), 4),
        "roc_auc": round(float(roc_auc_score(y_test, probabilidades)), 4),
        "datos": "sintéticos (ver ml/generar_dataset.py)",
    }

    joblib.dump(modelo, RUTA_MODELO)
    RUTA_METRICAS.write_text(json.dumps(metricas, ensure_ascii=False, indent=2), encoding="utf-8")

    print(classification_report(y_test, predicciones, zero_division=0))
    print(json.dumps(metricas, ensure_ascii=False, indent=2))
    coeficientes = modelo.named_steps["regresion_logistica"].coef_[0]
    for nombre, coef in zip(FEATURES, coeficientes):
        print(f"  coeficiente {nombre:>18}: {coef:+.3f}")
    print(f"Modelo guardado en {RUTA_MODELO}")


if __name__ == "__main__":
    main()
"""Predicción de ausentismo: pantalla web y endpoint JSON."""
from flask import jsonify, render_template, request
from flask_login import current_user, login_required

from ..extensions import csrf
from . import bp
from .predictor import predictor

DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes"]

# (mínimo, máximo) permitido para cada variable: coincide con el rango de entrenamiento.
RANGOS = {
    "dias_anticipacion": (0, 60),
    "hora": (9, 16),
    "dia_semana": (0, 4),
    "edad": (0, 100),
    "ausencias_previas": (0, 10),
}
ETIQUETAS = {
    "dias_anticipacion": "Días de anticipación",
    "hora": "Hora del turno",
    "dia_semana": "Día de la semana",
    "edad": "Edad",
    "ausencias_previas": "Ausencias previas",
}


def validar(datos):
    """Convierte y valida los datos. Devuelve (valores, errores)."""
    valores, errores = {}, []
    for campo, (minimo, maximo) in RANGOS.items():
        try:
            valor = int(datos.get(campo))
        except (TypeError, ValueError):
            errores.append(f"{ETIQUETAS[campo]}: ingresá un número entero.")
            continue
        if not minimo <= valor <= maximo:
            errores.append(f"{ETIQUETAS[campo]}: tiene que estar entre {minimo} y {maximo}.")
            continue
        valores[campo] = valor
    return valores, errores


@bp.route("/predecir", methods=["GET", "POST"])
@login_required
def predecir():
    """Formulario donde el usuario envía datos y recibe la predicción al instante."""
    datos = {"dias_anticipacion": 14, "hora": 10, "dia_semana": 1, "edad": 35, "ausencias_previas": 0}
    resultado, errores = None, []
    if request.method == "POST":
        datos = request.form.to_dict()
        valores, errores = validar(datos)
        if not errores:
            if predictor.disponible:
                resultado = predictor.predecir(**valores)
            else:
                errores.append("El modelo de IA no está disponible en este momento.")
    return render_template(
        "ia/predecir.html",
        datos=datos,
        resultado=resultado,
        errores=errores,
        dias=DIAS,
        rangos=RANGOS,
        metricas=predictor.metricas,
    )


@bp.route("/api/predecir", methods=["POST"])
@csrf.exempt  # solo calcula una predicción: no modifica ningún dato
def api_predecir():
    """Endpoint JSON: {"dias_anticipacion":..,"hora":..,"dia_semana":..,"edad":..,"ausencias_previas":..}"""
    if not current_user.is_authenticated:
        return jsonify(error="Necesitás iniciar sesión."), 401
    valores, errores = validar(request.get_json(silent=True) or {})
    if errores:
        return jsonify(errores=errores), 400
    if not predictor.disponible:
        return jsonify(error="El modelo de IA no está disponible."), 503
    return jsonify(predictor.predecir(**valores))
"""AgendaMed: prototipo funcional en Flask (patrón App Factory + Blueprints)."""
import logging
from urllib.parse import parse_qs

from flask import Flask, render_template
from sqlalchemy.exc import SQLAlchemyError

from config import Config

from .extensions import bcrypt, csrf, db, login_manager
from .ia.predictor import predictor

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]


class MethodOverrideMiddleware:
    """Permite que un formulario HTML (que solo envía GET y POST) use PUT, PATCH y DELETE
    agregando ?metodo=PUT (o PATCH / DELETE) a la URL de acción."""

    PERMITIDOS = {"PUT", "PATCH", "DELETE"}

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        if environ.get("REQUEST_METHOD") == "POST":
            consulta = parse_qs(environ.get("QUERY_STRING", ""))
            metodo = consulta.get("metodo", [""])[0].upper()
            if metodo in self.PERMITIDOS:
                environ["REQUEST_METHOD"] = metodo
        return self.app(environ, start_response)


def create_app(config_object=Config):
    app = Flask(__name__)
    app.config.from_object(config_object)

    if not app.config.get("SECRET_KEY"):
        raise RuntimeError("Falta la variable de entorno SECRET_KEY (ver .env.example).")

    logging.basicConfig(level=logging.INFO)

    db.init_app(app)
    bcrypt.init_app(app)
    csrf.init_app(app)
    login_manager.init_app(app)
    predictor.init_app(app)  # carga el modelo de IA una sola vez, al iniciar
    app.wsgi_app = MethodOverrideMiddleware(app.wsgi_app)

    from .admin import bp as admin_bp
    from .auth import bp as auth_bp
    from .ia import bp as ia_bp
    from .main import bp as main_bp
    from .turnos import bp as turnos_bp

    for blueprint in (main_bp, auth_bp, turnos_bp, admin_bp, ia_bp):
        app.register_blueprint(blueprint)

    _registrar_filtros(app)
    _registrar_errores(app)

    with app.app_context():
        from . import models  # noqa: F401  (registra las tablas)
        from .seed import cargar_datos_iniciales

        try:
            db.create_all()
        except SQLAlchemyError:
            # Si dos procesos arrancan a la vez, el otro pudo crear las tablas primero.
            db.session.rollback()
            app.logger.warning("create_all() falló; se asume que las tablas ya existen.")
        if app.config.get("AUTO_SEED"):
            cargar_datos_iniciales(app.config)

    return app


def _registrar_filtros(app):
    @app.template_filter("fecha_es")
    def fecha_es(fecha):
        return f"{DIAS[fecha.weekday()]} {fecha.day} de {MESES[fecha.month - 1]}"

    @app.template_filter("dia_corto")
    def dia_corto(fecha):
        return DIAS[fecha.weekday()][:3].upper()

    @app.template_filter("hhmm")
    def hhmm(hora):
        return hora.strftime("%H:%M")

    @app.template_filter("porcentaje")
    def porcentaje(valor):
        return "—" if valor is None else f"{valor * 100:.0f} %"

    @app.template_filter("nivel_riesgo")
    def nivel(valor):
        from .ia.predictor import nivel_riesgo

        return nivel_riesgo(valor)


def _registrar_errores(app):
    textos = {
        403: ("Sin permiso", "No tenés permiso para ver esta página."),
        404: ("No encontrado", "La página que buscás no existe."),
        500: ("Algo salió mal", "Ocurrió un error inesperado. Probá de nuevo en un rato."),
    }

    def manejador(codigo):
        def _responder(error):
            titulo, mensaje = textos[codigo]
            return render_template("error.html", codigo=codigo, titulo=titulo, mensaje=mensaje), codigo

        return _responder

    for codigo in textos:
        app.register_error_handler(codigo, manejador(codigo))
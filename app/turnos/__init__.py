from flask import Blueprint

bp = Blueprint("turnos", __name__, url_prefix="/turnos")

from . import routes  # noqa: E402,F401
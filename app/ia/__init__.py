from flask import Blueprint

bp = Blueprint("ia", __name__, url_prefix="/ia")

from . import routes  # noqa: E402,F401
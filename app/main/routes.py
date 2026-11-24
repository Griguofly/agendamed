from flask import jsonify, render_template
from sqlalchemy import text

from ..extensions import db
from . import bp


@bp.route("/")
def index():
    return render_template("index.html")


@bp.route("/health")
def health():
    """Chequeo de salud (útil para Render): verifica que la base responda."""
    db.session.execute(text("SELECT 1"))
    return jsonify(estado="ok")
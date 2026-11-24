"""Panel del administrativo: ve todos los turnos con su riesgo de ausencia (IA)."""
from flask import flash, redirect, render_template, request, url_for

from ..decorators import admin_required
from ..extensions import db
from ..models import ESTADOS, Turno
from ..turnos import servicio
from ..turnos.servicio import TurnoError
from . import bp


@bp.route("/turnos")
@admin_required
def turnos():
    estado = request.args.get("estado", "")
    consulta = db.select(Turno).order_by(Turno.fecha.desc(), Turno.hora.desc())
    if estado in ESTADOS:
        consulta = consulta.where(Turno.estado == estado)
    lista = db.session.scalars(consulta).all()
    return render_template("admin/turnos.html", turnos=lista, estados=ESTADOS, filtro=estado)


@bp.route("/turnos/<int:turno_id>/estado", methods=["PATCH"])
@admin_required
def cambiar_estado(turno_id):
    turno = db.get_or_404(Turno, turno_id)
    try:
        servicio.marcar_estado(turno, request.form.get("estado", ""))
    except TurnoError as error:
        flash(str(error), "error")
    else:
        flash(f"Turno #{turno.id} marcado como {turno.estado}.", "success")
    return redirect(url_for("admin.turnos"), code=303)


@bp.route("/turnos/<int:turno_id>", methods=["DELETE"])
@admin_required
def eliminar(turno_id):
    turno = db.get_or_404(Turno, turno_id)
    try:
        servicio.eliminar_turno(turno)
    except TurnoError as error:
        flash(str(error), "error")
    else:
        flash("Turno eliminado definitivamente.", "info")
    return redirect(url_for("admin.turnos"), code=303)
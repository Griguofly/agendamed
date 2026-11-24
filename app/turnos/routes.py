"""CRUD de Turnos para el paciente (requisito principal: RF-02 · CU-01 · E2).

    Create  POST   /turnos/              solicitar turno (RF-02)
    Read    GET    /turnos/              mis turnos
    Update  PUT    /turnos/<id>          reprogramar (RF-04)
    Delete  DELETE /turnos/<id>          cancelar (RF-03)

Los formularios HTML solo envían GET y POST: para PUT y DELETE se agrega
?metodo=PUT / ?metodo=DELETE a la URL (ver MethodOverrideMiddleware en app/__init__.py).

El flujo de reserva sigue los 3 pasos del CU-01 (RNF-04):
    1) especialidad y médico  2) día y horario  3) confirmación
"""
from datetime import date, time, timedelta

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from ..decorators import paciente_required
from ..extensions import db
from ..models import Especialidad, Medico, Turno
from . import bp, servicio
from .servicio import TurnoError


# ---------- utilidades ----------
def _fecha(texto):
    try:
        return date.fromisoformat(texto or "")
    except ValueError:
        return None


def _hora(texto):
    try:
        return time.fromisoformat(texto or "")
    except ValueError:
        return None


def _turno_propio_o_403(turno_id):
    turno = db.get_or_404(Turno, turno_id)
    if turno.paciente_id != current_user.id:
        abort(403)
    return turno


def _medico_y_especialidad(args):
    """Lee y valida especialidad_id y medico_id de la URL (404 si no corresponden)."""
    especialidad = db.session.get(Especialidad, args.get("especialidad_id", type=int) or 0)
    medico = db.session.get(Medico, args.get("medico_id", type=int) or 0)
    if not especialidad or not medico or especialidad not in medico.especialidades:
        abort(404)
    return medico, especialidad


# ---------- READ: mis turnos ----------
@bp.route("/")
@paciente_required
def mis_turnos():
    todos = db.session.scalars(
        db.select(Turno)
        .where(Turno.paciente_id == current_user.id)
        .order_by(Turno.fecha, Turno.hora)
    ).all()
    proximos = [t for t in todos if t.es_activo and t.fecha >= servicio.hoy()]
    historial = [t for t in reversed(todos) if t not in proximos]
    return render_template("turnos/mis_turnos.html", proximos=proximos, historial=historial)


# ---------- Pasos 1 a 3 del flujo de reserva ----------
@bp.route("/nuevo")
@paciente_required
def nuevo():
    """Paso 1: elegir especialidad y médico."""
    especialidades = db.session.scalars(db.select(Especialidad).order_by(Especialidad.nombre)).all()
    especialidad = db.session.get(Especialidad, request.args.get("especialidad_id", type=int) or 0)
    medicos = sorted(especialidad.medicos, key=lambda m: m.apellido) if especialidad else []
    return render_template(
        "turnos/nuevo.html", especialidades=especialidades, especialidad=especialidad, medicos=medicos
    )


@bp.route("/nuevo/horarios")
@paciente_required
def horarios():
    """Paso 2: elegir día y horario libre del médico."""
    medico, especialidad = _medico_y_especialidad(request.args)
    fecha = _fecha(request.args.get("fecha"))
    libres = servicio.horarios_libres(medico.id, fecha) if fecha else []
    if fecha and not servicio.es_fecha_valida(fecha):
        flash("Esa fecha no es válida: se atiende de lunes a viernes, hasta 30 días adelante.", "error")
        fecha = None
    return render_template(
        "turnos/horarios.html",
        medico=medico,
        especialidad=especialidad,
        fecha=fecha,
        libres=libres,
        dias=servicio.proximos_dias_habiles(10),
        min_fecha=servicio.hoy(),
        max_fecha=servicio.hoy() + timedelta(days=servicio.DIAS_ADELANTE),
    )


@bp.route("/nuevo/confirmar")
@paciente_required
def confirmar():
    """Paso 3: resumen y confirmación."""
    medico, especialidad = _medico_y_especialidad(request.args)
    fecha, hora = _fecha(request.args.get("fecha")), _hora(request.args.get("hora"))
    if not fecha or not hora or hora not in servicio.horarios_libres(medico.id, fecha):
        flash("Ese horario ya no está disponible. Elegí otro.", "error")
        return redirect(
            url_for("turnos.horarios", especialidad_id=especialidad.id, medico_id=medico.id, fecha=fecha)
        )
    return render_template(
        "turnos/confirmar.html", medico=medico, especialidad=especialidad, fecha=fecha, hora=hora
    )


# ---------- CREATE ----------
@bp.route("/", methods=["POST"])
@paciente_required
def crear():
    medico, especialidad = _medico_y_especialidad(request.form)
    fecha, hora = _fecha(request.form.get("fecha")), _hora(request.form.get("hora"))
    try:
        if not fecha or not hora:
            raise TurnoError("Faltan la fecha o el horario del turno.")
        servicio.crear_turno(current_user, medico, especialidad, fecha, hora)
    except TurnoError as error:
        flash(str(error), "error")
        return redirect(
            url_for("turnos.horarios", especialidad_id=especialidad.id, medico_id=medico.id, fecha=fecha),
            code=303,
        )
    flash("¡Turno confirmado! Te vamos a avisar antes de la fecha.", "success")
    return redirect(url_for("turnos.mis_turnos"), code=303)


# ---------- UPDATE ----------
@bp.route("/<int:turno_id>/reprogramar")
@paciente_required
def reprogramar(turno_id):
    """Pantalla para elegir el nuevo día y horario."""
    turno = _turno_propio_o_403(turno_id)
    if not turno.es_activo:
        flash("Ese turno ya no se puede reprogramar.", "error")
        return redirect(url_for("turnos.mis_turnos"))
    fecha = _fecha(request.args.get("fecha"))
    if fecha and not servicio.es_fecha_valida(fecha):
        flash("Esa fecha no es válida: se atiende de lunes a viernes, hasta 30 días adelante.", "error")
        fecha = None
    libres = servicio.horarios_libres(turno.medico_id, fecha, excluir_turno_id=turno.id) if fecha else []
    return render_template(
        "turnos/reprogramar.html", turno=turno, fecha=fecha, libres=libres, dias=servicio.proximos_dias_habiles(10)
    )


@bp.route("/<int:turno_id>", methods=["PUT", "PATCH"])
@paciente_required
def actualizar(turno_id):
    turno = _turno_propio_o_403(turno_id)
    fecha, hora = _fecha(request.form.get("fecha")), _hora(request.form.get("hora"))
    try:
        if not fecha or not hora:
            raise TurnoError("Faltan la fecha o el horario nuevo.")
        servicio.reprogramar_turno(turno, fecha, hora)
    except TurnoError as error:
        flash(str(error), "error")
        return redirect(url_for("turnos.reprogramar", turno_id=turno.id, fecha=fecha), code=303)
    flash("Turno reprogramado.", "success")
    return redirect(url_for("turnos.mis_turnos"), code=303)


# ---------- DELETE ----------
@bp.route("/<int:turno_id>", methods=["DELETE"])
@paciente_required
def cancelar(turno_id):
    turno = _turno_propio_o_403(turno_id)
    try:
        servicio.cancelar_turno(turno)
    except TurnoError as error:
        flash(str(error), "error")
    else:
        flash("Turno cancelado. El horario quedó libre.", "info")
    return redirect(url_for("turnos.mis_turnos"), code=303)
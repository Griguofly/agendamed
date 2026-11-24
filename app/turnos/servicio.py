"""Reglas de negocio de los turnos (RF-02, RF-03 y RF-04).

Como el prototipo no incluye la entidad Disponibilidad, los médicos atienden con una
grilla fija: lunes a viernes, de 09:00 a 17:00, turnos de 30 minutos.
"""
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError

from ..extensions import db
from ..ia.predictor import predictor
from ..models import ESTADOS_ACTIVOS, Turno

ZONA = ZoneInfo("America/Argentina/Buenos_Aires")
HORA_INICIO = time(9, 0)
HORA_FIN = time(17, 0)
DURACION_MIN = 30
DIAS_ADELANTE = 30       # se puede reservar hasta 30 días hacia adelante
MARGEN_MIN = 30          # no se reserva con menos de 30 minutos de anticipación


class TurnoError(Exception):
    """Error de negocio con un mensaje listo para mostrarle al usuario."""


def ahora():
    return datetime.now(ZONA).replace(tzinfo=None)


def hoy():
    return ahora().date()


def todos_los_horarios():
    """Grilla del día: 09:00, 09:30 ... 16:30."""
    horarios, actual = [], datetime.combine(date.min, HORA_INICIO)
    fin = datetime.combine(date.min, HORA_FIN)
    while actual < fin:
        horarios.append(actual.time())
        actual += timedelta(minutes=DURACION_MIN)
    return horarios


def es_fecha_valida(fecha):
    """Día hábil, no pasado y dentro de los próximos DIAS_ADELANTE días."""
    return fecha.weekday() < 5 and hoy() <= fecha <= hoy() + timedelta(days=DIAS_ADELANTE)


def proximos_dias_habiles(cantidad=10):
    dias, dia = [], hoy()
    while len(dias) < cantidad and dia <= hoy() + timedelta(days=DIAS_ADELANTE):
        if dia.weekday() < 5:
            dias.append(dia)
        dia += timedelta(days=1)
    return dias


def _es_futuro(fecha, hora):
    return datetime.combine(fecha, hora) > ahora() + timedelta(minutes=MARGEN_MIN)


def horarios_libres(medico_id, fecha, excluir_turno_id=None):
    """Horarios del médico para ese día que no tienen un turno vigente."""
    if not es_fecha_valida(fecha):
        return []
    consulta = db.select(Turno.hora).where(
        Turno.medico_id == medico_id, Turno.fecha == fecha, Turno.estado != "Cancelado"
    )
    if excluir_turno_id:
        consulta = consulta.where(Turno.id != excluir_turno_id)
    ocupados = set(db.session.scalars(consulta))
    return [h for h in todos_los_horarios() if h not in ocupados and _es_futuro(fecha, h)]


def _validar_fecha_hora(fecha, hora):
    if not es_fecha_valida(fecha):
        raise TurnoError("La fecha elegida no es válida: se atiende de lunes a viernes, hasta 30 días adelante.")
    if hora not in todos_los_horarios():
        raise TurnoError("El horario elegido no existe en la agenda.")
    if not _es_futuro(fecha, hora):
        raise TurnoError("Ese horario ya pasó o es demasiado próximo.")


def _paciente_ocupado(paciente_id, fecha, hora, excluir_turno_id=None):
    consulta = db.select(Turno.id).where(
        Turno.paciente_id == paciente_id,
        Turno.fecha == fecha,
        Turno.hora == hora,
        Turno.estado.in_(ESTADOS_ACTIVOS),
    )
    if excluir_turno_id:
        consulta = consulta.where(Turno.id != excluir_turno_id)
    return db.session.scalar(consulta) is not None


def estimar_riesgo(paciente, fecha, hora):
    """Probabilidad de ausencia según el modelo de IA (None si no está disponible)."""
    if not predictor.disponible:
        return None
    resultado = predictor.predecir(
        dias_anticipacion=max((fecha - hoy()).days, 0),
        hora=hora.hour,
        dia_semana=fecha.weekday(),
        edad=paciente.edad if paciente.edad is not None else 40,
        ausencias_previas=paciente.ausencias_previas(),
    )
    return resultado["probabilidad"]


def crear_turno(paciente, medico, especialidad, fecha, hora):
    """CREATE: CU-01 Solicitar turno (pasos 5 a 7 del flujo principal)."""
    if especialidad not in medico.especialidades:
        raise TurnoError("El médico elegido no atiende esa especialidad.")
    _validar_fecha_hora(fecha, hora)
    if _paciente_ocupado(paciente.id, fecha, hora):
        raise TurnoError("Ya tenés un turno en ese día y horario.")

    turno = Turno(
        fecha=fecha,
        hora=hora,
        estado="Confirmado",
        paciente=paciente,
        medico=medico,
        especialidad=especialidad,
        prob_ausencia=estimar_riesgo(paciente, fecha, hora),
    )
    db.session.add(turno)
    try:
        db.session.commit()
    except IntegrityError:
        # Flujo alternativo A1: otro paciente tomó el horario mientras se confirmaba.
        db.session.rollback()
        raise TurnoError("Ese horario acaba de ser tomado por otro paciente. Elegí otro.")
    return turno


def reprogramar_turno(turno, fecha, hora):
    """UPDATE: RF-04 Reprogramar un turno a otra fecha u horario."""
    if not turno.es_activo:
        raise TurnoError("Solo se pueden reprogramar turnos confirmados o reprogramados.")
    if (fecha, hora) == (turno.fecha, turno.hora):
        raise TurnoError("Elegiste el mismo día y horario que ya tenías.")
    _validar_fecha_hora(fecha, hora)
    if _paciente_ocupado(turno.paciente_id, fecha, hora, excluir_turno_id=turno.id):
        raise TurnoError("Ya tenés otro turno en ese día y horario.")

    turno.fecha, turno.hora, turno.estado = fecha, hora, "Reprogramado"
    turno.prob_ausencia = estimar_riesgo(turno.paciente, fecha, hora)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise TurnoError("Ese horario acaba de ser tomado por otro paciente. Elegí otro.")
    return turno


def cancelar_turno(turno):
    """DELETE (baja lógica): RF-03 Cancelar un turno y liberar el horario."""
    if not turno.es_activo:
        raise TurnoError("Solo se pueden cancelar turnos confirmados o reprogramados.")
    turno.estado = "Cancelado"
    db.session.commit()
    return turno


def marcar_estado(turno, estado):
    """El administrativo marca si el paciente fue atendido o estuvo ausente."""
    if estado not in ("Atendido", "Ausente"):
        raise TurnoError("Estado no permitido.")
    if not turno.es_activo:
        raise TurnoError("Solo se pueden marcar turnos confirmados o reprogramados.")
    turno.estado = estado
    db.session.commit()
    return turno


def eliminar_turno(turno):
    """DELETE (baja física): el administrativo borra turnos ya cancelados."""
    if turno.estado != "Cancelado":
        raise TurnoError("Solo se pueden eliminar definitivamente turnos cancelados.")
    db.session.delete(turno)
    db.session.commit()
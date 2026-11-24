"""Datos iniciales: especialidades, médicos de ejemplo y usuario administrativo.

Se ejecuta al iniciar la app (si AUTO_SEED=1) y es idempotente: solo carga lo que falta.
Los médicos son ficticios, solo para poder probar el prototipo.
"""
import logging

from sqlalchemy.exc import IntegrityError

from .extensions import db
from .models import ROL_ADMIN, Especialidad, Medico, Paciente

log = logging.getLogger(__name__)

ESPECIALIDADES = [
    ("Clínica médica", "Atención general y control de salud."),
    ("Pediatría", "Atención de niños y adolescentes."),
    ("Cardiología", "Salud del corazón y la circulación."),
    ("Dermatología", "Cuidado de la piel."),
    ("Traumatología", "Huesos, músculos y articulaciones."),
]

# (título, nombre, apellido, matrícula, especialidades)
MEDICOS = [
    ("Dra.", "Laura", "Sosa", "MP 10231", ["Clínica médica"]),
    ("Dr.", "Martín", "Acuña", "MP 10874", ["Clínica médica", "Cardiología"]),
    ("Dra.", "Carla", "Gómez", "MP 11450", ["Clínica médica"]),
    ("Dra.", "Julieta", "Ramos", "MP 12096", ["Pediatría"]),
    ("Dr.", "Pablo", "Ferreyra", "MP 12688", ["Pediatría", "Clínica médica"]),
    ("Dr.", "Nicolás", "Benítez", "MP 13302", ["Cardiología"]),
    ("Dra.", "Valeria", "Núñez", "MP 13977", ["Dermatología"]),
    ("Dr.", "Diego", "Paredes", "MP 14515", ["Traumatología"]),
]


def cargar_catalogo():
    if db.session.scalar(db.select(Especialidad.id).limit(1)) is not None:
        return
    especialidades = {n: Especialidad(nombre=n, descripcion=d) for n, d in ESPECIALIDADES}
    db.session.add_all(especialidades.values())
    for titulo, nombre, apellido, matricula, nombres_esp in MEDICOS:
        medico = Medico(titulo=titulo, nombre=nombre, apellido=apellido, matricula=matricula)
        medico.email = f"{nombre}.{apellido}@agendamed.example".lower()
        medico.especialidades = [especialidades[n] for n in nombres_esp]
        db.session.add(medico)
    db.session.commit()
    log.info("Catálogo inicial cargado (%d especialidades, %d médicos).", len(ESPECIALIDADES), len(MEDICOS))


def cargar_admin(email, clave):
    if not email or not clave:
        return
    if db.session.scalar(db.select(Paciente.id).where(Paciente.email == email)) is not None:
        return
    admin = Paciente(nombre="Administración", apellido="AgendaMed", email=email, rol=ROL_ADMIN)
    admin.set_password(clave)
    db.session.add(admin)
    db.session.commit()
    log.info("Usuario administrativo creado: %s", email)


def cargar_datos_iniciales(config):
    """Tolera el caso en que dos procesos arrancan a la vez e intentan cargar lo mismo."""
    try:
        cargar_catalogo()
        cargar_admin(config.get("ADMIN_EMAIL"), config.get("ADMIN_PASSWORD"))
    except IntegrityError:
        db.session.rollback()
        log.info("Los datos iniciales ya habían sido cargados por otro proceso.")
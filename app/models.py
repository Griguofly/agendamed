"""Modelos de datos de AgendaMed.

Corresponden a las entidades del DER del SRS (versión recortada del prototipo):

    Paciente (D1)  ·  Turno (D2)  ·  Médico (D3)  ·  Especialidad (D6)

Quedan fuera del prototipo Consulta (D4) y Disponibilidad (D5): los horarios son
una grilla fija (ver app/turnos/servicio.py).
"""
from datetime import date, datetime, timezone

from flask_login import UserMixin
from sqlalchemy import Index, func

from .extensions import bcrypt, db, login_manager

# Dominio del elemento de datos "estado" del Diccionario de Datos.
ESTADOS = ("Confirmado", "Reprogramado", "Cancelado", "Atendido", "Ausente")
# Estados en los que el turno todavía ocupa el horario y puede modificarse.
ESTADOS_ACTIVOS = ("Confirmado", "Reprogramado")


def _ahora_utc():
    return datetime.now(timezone.utc).replace(tzinfo=None)


ROL_PACIENTE = "paciente"
ROL_ADMIN = "administrativo"

# Relación N:M Médico – Especialidad ("se especializa en").
medico_especialidad = db.Table(
    "medico_especialidad",
    db.Column("medico_id", db.Integer, db.ForeignKey("medico.id"), primary_key=True),
    db.Column("especialidad_id", db.Integer, db.ForeignKey("especialidad.id"), primary_key=True),
)


class Paciente(UserMixin, db.Model):
    """D1 Pacientes. También es la cuenta de acceso (email + contraseña cifrada)."""

    __tablename__ = "paciente"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(60), nullable=False)
    apellido = db.Column(db.String(60), nullable=False)
    dni = db.Column(db.String(10), unique=True)
    telefono = db.Column(db.String(25))
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    fecha_nacimiento = db.Column(db.Date)
    password_hash = db.Column(db.String(128), nullable=False)
    rol = db.Column(db.String(20), nullable=False, default=ROL_PACIENTE)
    creado_en = db.Column(db.DateTime, default=_ahora_utc)

    turnos = db.relationship("Turno", back_populates="paciente")

    # --- Contraseñas: siempre cifradas con Bcrypt, nunca en texto plano ---
    def set_password(self, clave):
        self.password_hash = bcrypt.generate_password_hash(clave).decode("utf-8")

    def check_password(self, clave):
        return bcrypt.check_password_hash(self.password_hash, clave)

    @property
    def es_admin(self):
        return self.rol == ROL_ADMIN

    @property
    def edad(self):
        if not self.fecha_nacimiento:
            return None
        hoy = date.today()
        cumplio = (hoy.month, hoy.day) >= (self.fecha_nacimiento.month, self.fecha_nacimiento.day)
        return hoy.year - self.fecha_nacimiento.year - (0 if cumplio else 1)

    @property
    def nombre_completo(self):
        return f"{self.nombre} {self.apellido}"

    def ausencias_previas(self):
        """Cantidad de turnos en los que el paciente figura como Ausente."""
        return db.session.scalar(
            db.select(func.count(Turno.id)).where(
                Turno.paciente_id == self.id, Turno.estado == "Ausente"
            )
        )


@login_manager.user_loader
def cargar_usuario(user_id):
    return db.session.get(Paciente, int(user_id))


class Especialidad(db.Model):
    """D6 Especialidades."""

    __tablename__ = "especialidad"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(80), unique=True, nullable=False)
    descripcion = db.Column(db.String(200))

    medicos = db.relationship("Medico", secondary=medico_especialidad, back_populates="especialidades")


class Medico(db.Model):
    """D3 Médicos."""

    __tablename__ = "medico"

    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(10), default="Dr.")
    nombre = db.Column(db.String(60), nullable=False)
    apellido = db.Column(db.String(60), nullable=False)
    matricula = db.Column(db.String(20), unique=True, nullable=False)
    email = db.Column(db.String(120))

    especialidades = db.relationship(
        "Especialidad", secondary=medico_especialidad, back_populates="medicos"
    )
    turnos = db.relationship("Turno", back_populates="medico")

    @property
    def nombre_completo(self):
        return f"{self.titulo} {self.nombre} {self.apellido}"


class Turno(db.Model):
    """D2 Turnos: es la entidad del requisito principal (RF-02, CU-01)."""

    __tablename__ = "turno"

    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.Date, nullable=False, index=True)
    hora = db.Column(db.Time, nullable=False)
    estado = db.Column(db.String(15), nullable=False, default="Confirmado")
    paciente_id = db.Column(db.Integer, db.ForeignKey("paciente.id"), nullable=False, index=True)
    medico_id = db.Column(db.Integer, db.ForeignKey("medico.id"), nullable=False)
    especialidad_id = db.Column(db.Integer, db.ForeignKey("especialidad.id"), nullable=False)
    # Probabilidad de ausencia estimada por el modelo de IA al reservar/reprogramar.
    prob_ausencia = db.Column(db.Float)
    creado_en = db.Column(db.DateTime, default=_ahora_utc)

    paciente = db.relationship("Paciente", back_populates="turnos")
    medico = db.relationship("Medico", back_populates="turnos")
    especialidad = db.relationship("Especialidad")

    __table_args__ = (
        # Un médico no puede tener dos turnos vigentes en el mismo día y horario.
        # Al cancelar, el turno deja de contar y el horario queda libre.
        Index(
            "uq_turno_medico_horario_vigente",
            "medico_id",
            "fecha",
            "hora",
            unique=True,
            sqlite_where=db.text("estado <> 'Cancelado'"),
            postgresql_where=db.text("estado <> 'Cancelado'"),
        ),
    )

    @property
    def es_activo(self):
        return self.estado in ESTADOS_ACTIVOS
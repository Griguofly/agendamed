"""Registro, inicio y cierre de sesión (RF-01, RNF-02)."""
import re
from datetime import date

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy.exc import IntegrityError

from ..extensions import db
from ..models import Paciente
from . import bp

RE_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
RE_DNI = re.compile(r"^\d{7,8}$")
RE_TELEFONO = re.compile(r"^[\d\s+\-()]{8,20}$")
CAMPOS = ("nombre", "apellido", "dni", "telefono", "email", "fecha_nacimiento")


def _destino_seguro(destino):
    """Solo se aceptan rutas internas, para evitar redirecciones a otros sitios."""
    if destino and destino.startswith("/") and not destino.startswith("//") and "\\" not in destino:
        return destino
    return None


def validar_registro(datos, clave, clave2):
    errores = []
    if not 2 <= len(datos["nombre"]) <= 60:
        errores.append("El nombre es obligatorio (hasta 60 caracteres).")
    if not 2 <= len(datos["apellido"]) <= 60:
        errores.append("El apellido es obligatorio (hasta 60 caracteres).")
    if not RE_DNI.match(datos["dni"]):
        errores.append("El DNI debe tener 7 u 8 números, sin puntos.")
    if not RE_TELEFONO.match(datos["telefono"]):
        errores.append("Ingresá un teléfono válido (solo números, +, -, espacios o paréntesis).")
    if not RE_EMAIL.match(datos["email"]) or len(datos["email"]) > 120:
        errores.append("Ingresá un email válido.")
    try:
        nacimiento = date.fromisoformat(datos["fecha_nacimiento"])
        if not date(1900, 1, 1) <= nacimiento <= date.today():
            raise ValueError
    except ValueError:
        errores.append("Ingresá una fecha de nacimiento válida.")
    if len(clave) < 8:
        errores.append("La contraseña debe tener al menos 8 caracteres.")
    elif clave != clave2:
        errores.append("Las contraseñas no coinciden.")
    return errores


@bp.route("/registro", methods=["GET", "POST"])
def registro():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    datos = {campo: "" for campo in CAMPOS}
    if request.method == "POST":
        datos = {campo: request.form.get(campo, "").strip() for campo in CAMPOS}
        datos["email"] = datos["email"].lower()
        clave = request.form.get("password", "")
        errores = validar_registro(datos, clave, request.form.get("password2", ""))

        if not errores:
            paciente = Paciente(
                nombre=datos["nombre"],
                apellido=datos["apellido"],
                dni=datos["dni"],
                telefono=datos["telefono"],
                email=datos["email"],
                fecha_nacimiento=date.fromisoformat(datos["fecha_nacimiento"]),
            )
            paciente.set_password(clave)  # se guarda el hash Bcrypt, no la contraseña
            db.session.add(paciente)
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                errores.append("Ya existe una cuenta con ese email o ese DNI.")
            else:
                login_user(paciente)
                flash("¡Cuenta creada! Ya podés pedir tu primer turno.", "success")
                return redirect(url_for("turnos.nuevo"))

        for error in errores:
            flash(error, "error")

    return render_template("auth/registro.html", datos=datos)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        paciente = db.session.scalar(db.select(Paciente).where(Paciente.email == email))
        if paciente and paciente.check_password(request.form.get("password", "")):
            login_user(paciente)
            destino = _destino_seguro(request.args.get("next"))
            return redirect(destino or url_for("main.index"))
        flash("Email o contraseña incorrectos.", "error")

    return render_template("auth/login.html")


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("Cerraste sesión.", "info")
    return redirect(url_for("main.index"))
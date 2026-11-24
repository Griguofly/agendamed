from functools import wraps

from flask import abort, redirect, url_for
from flask_login import current_user, login_required


def admin_required(vista):
    """Solo el usuario administrativo; cualquier otro recibe 403."""

    @wraps(vista)
    @login_required
    def envoltura(*args, **kwargs):
        if not current_user.es_admin:
            abort(403)
        return vista(*args, **kwargs)

    return envoltura


def paciente_required(vista):
    """Pantallas de paciente: el administrativo es derivado a su panel."""

    @wraps(vista)
    @login_required
    def envoltura(*args, **kwargs):
        if current_user.es_admin:
            return redirect(url_for("admin.turnos"))
        return vista(*args, **kwargs)

    return envoltura
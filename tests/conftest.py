from datetime import timedelta

import pytest

from app import create_app
from app.extensions import db
from app.models import Paciente
from app.seed import cargar_admin, cargar_catalogo
from app.turnos.servicio import hoy
from config import TestConfig


@pytest.fixture()
def app():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        cargar_catalogo()
        cargar_admin("admin@test.com", "ClaveAdmin123")
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


DATOS_REGISTRO = {
    "nombre": "Lucía",
    "apellido": "Pérez",
    "dni": "30123456",
    "telefono": "+54 11 5555-1234",
    "email": "lucia@test.com",
    "fecha_nacimiento": "1990-05-10",
    "password": "ClaveSegura1",
    "password2": "ClaveSegura1",
}


def registrar(client, **cambios):
    datos = {**DATOS_REGISTRO, **cambios}
    return client.post("/auth/registro", data=datos, follow_redirects=True)


def login(client, email, clave):
    return client.post("/auth/login", data={"email": email, "password": clave}, follow_redirects=True)


def proximo_dia_habil(dias_minimos=2):
    dia = hoy() + timedelta(days=dias_minimos)
    while dia.weekday() >= 5:
        dia += timedelta(days=1)
    return dia
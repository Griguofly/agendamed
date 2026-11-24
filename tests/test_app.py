from datetime import timedelta

import pytest

from app import create_app
from app.extensions import db
from app.models import Especialidad, Medico, Paciente, Turno
from app.turnos import servicio
from config import TestConfig, _url_base_de_datos

from conftest import DATOS_REGISTRO, login, proximo_dia_habil, registrar


# ---------- helpers ----------
def _medico_clinico():
    esp = db.session.scalar(db.select(Especialidad).where(Especialidad.nombre == "Clínica médica"))
    return esp.medicos[0], esp


def _reservar(client, medico, esp, fecha, hora="10:00"):
    return client.post(
        "/turnos/",
        data={"especialidad_id": esp.id, "medico_id": medico.id, "fecha": fecha.isoformat(), "hora": hora},
        follow_redirects=True,
    )


def _segundo_paciente(client_factory):
    otro = client_factory()
    registrar(otro, email="otro@test.com", dni="28999888")
    return otro


# ---------- autenticación ----------
def test_contrasena_se_guarda_cifrada_con_bcrypt(client, app):
    registrar(client)
    paciente = db.session.scalar(db.select(Paciente).where(Paciente.email == "lucia@test.com"))
    assert paciente is not None
    assert paciente.password_hash != DATOS_REGISTRO["password"]
    assert paciente.password_hash.startswith("$2")  # formato Bcrypt
    assert paciente.check_password("ClaveSegura1")
    assert not paciente.check_password("otra-clave")


def test_login_correcto_e_incorrecto(client):
    registrar(client)
    client.post("/auth/logout", follow_redirects=True)
    mal = login(client, "lucia@test.com", "incorrecta")
    assert "Email o contraseña incorrectos" in mal.get_data(as_text=True)
    bien = login(client, "lucia@test.com", "ClaveSegura1")
    assert "Salir (Lucía)" in bien.get_data(as_text=True)


def test_registro_valida_datos(client):
    corta = registrar(client, password="123", password2="123")
    assert "al menos 8 caracteres" in corta.get_data(as_text=True)
    registrar(client)
    client.post("/auth/logout")
    repetido = registrar(client)
    assert "Ya existe una cuenta" in repetido.get_data(as_text=True)


def test_rutas_protegidas_piden_login(client):
    r = client.get("/turnos/")
    assert r.status_code == 302 and "/auth/login" in r.headers["Location"]
    assert client.get("/admin/turnos").status_code == 302


def test_login_no_redirige_a_sitios_externos(client):
    registrar(client)
    client.post("/auth/logout")
    r = client.post("/auth/login?next=//evil.com", data={"email": "lucia@test.com", "password": "ClaveSegura1"})
    assert r.status_code == 302 and "evil.com" not in r.headers["Location"]


def test_csrf_activo_en_produccion(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "x")

    class ConCsrf(TestConfig):
        WTF_CSRF_ENABLED = True

    app = create_app(ConCsrf)
    with app.app_context():
        db.create_all()
        r = app.test_client().post("/auth/login", data={"email": "a@a.com", "password": "x"})
        assert r.status_code == 400


# ---------- CRUD de turnos ----------
def test_flujo_completo_de_reserva_en_3_pasos(client):
    registrar(client)
    medico, esp = _medico_clinico()
    fecha = proximo_dia_habil()

    paso1 = client.get(f"/turnos/nuevo?especialidad_id={esp.id}")
    assert medico.apellido in paso1.get_data(as_text=True)

    paso2 = client.get(f"/turnos/nuevo/horarios?especialidad_id={esp.id}&medico_id={medico.id}&fecha={fecha.isoformat()}")
    assert "10:00" in paso2.get_data(as_text=True)

    paso3 = client.get(
        f"/turnos/nuevo/confirmar?especialidad_id={esp.id}&medico_id={medico.id}&fecha={fecha.isoformat()}&hora=10:00"
    )
    assert "Confirmar turno" in paso3.get_data(as_text=True)

    r = _reservar(client, medico, esp, fecha)
    assert "Turno confirmado" in r.get_data(as_text=True)
    turno = db.session.scalar(db.select(Turno))
    assert turno.estado == "Confirmado"
    assert turno.fecha == fecha and turno.hora.hour == 10
    assert turno.prob_ausencia is not None and 0 <= turno.prob_ausencia <= 1  # la IA se integra al CRUD


def test_horario_tomado_deja_de_estar_libre_y_no_se_puede_duplicar(client, app):
    registrar(client)
    medico, esp = _medico_clinico()
    fecha = proximo_dia_habil()
    _reservar(client, medico, esp, fecha)
    assert all(h.hour != 10 or h.minute != 0 for h in servicio.horarios_libres(medico.id, fecha))

    client.post("/auth/logout")
    registrar(client, email="otro@test.com", dni="28999888")
    r = _reservar(client, medico, esp, fecha)  # flujo alternativo A1
    assert "Ese horario" in r.get_data(as_text=True) or "no está disponible" in r.get_data(as_text=True)
    assert len(db.session.scalars(db.select(Turno)).all()) == 1


def test_indice_unico_impide_doble_reserva_en_la_base(app, client):
    registrar(client)
    medico, esp = _medico_clinico()
    paciente = db.session.scalar(db.select(Paciente))
    fecha = proximo_dia_habil()
    from datetime import time

    db.session.add(Turno(fecha=fecha, hora=time(9, 0), paciente=paciente, medico=medico, especialidad=esp))
    db.session.commit()
    db.session.add(Turno(fecha=fecha, hora=time(9, 0), paciente=paciente, medico=medico, especialidad=esp))
    with pytest.raises(Exception):
        db.session.commit()
    db.session.rollback()


def test_reprogramar_con_put_libera_el_horario_anterior(client):
    registrar(client)
    medico, esp = _medico_clinico()
    fecha = proximo_dia_habil()
    _reservar(client, medico, esp, fecha, "10:00")
    turno = db.session.scalar(db.select(Turno))
    nueva = proximo_dia_habil(4)

    r = client.post(
        f"/turnos/{turno.id}?metodo=PUT",
        data={"fecha": nueva.isoformat(), "hora": "11:30"},
        follow_redirects=True,
    )
    assert "Turno reprogramado" in r.get_data(as_text=True)
    db.session.refresh(turno)
    assert turno.estado == "Reprogramado" and turno.fecha == nueva and turno.hora.hour == 11
    assert any(h.hour == 10 and h.minute == 0 for h in servicio.horarios_libres(medico.id, fecha))


def test_cancelar_con_delete_libera_el_horario(client):
    registrar(client)
    medico, esp = _medico_clinico()
    fecha = proximo_dia_habil()
    _reservar(client, medico, esp, fecha)
    turno = db.session.scalar(db.select(Turno))

    r = client.post(f"/turnos/{turno.id}?metodo=DELETE", follow_redirects=True)
    assert "Turno cancelado" in r.get_data(as_text=True)
    db.session.refresh(turno)
    assert turno.estado == "Cancelado"
    assert any(h.hour == 10 and h.minute == 0 for h in servicio.horarios_libres(medico.id, fecha))
    # y se puede volver a reservar ese horario
    _reservar(client, medico, esp, fecha)
    assert len(db.session.scalars(db.select(Turno).where(Turno.estado != "Cancelado")).all()) == 1


def test_un_paciente_no_toca_turnos_ajenos(client, app):
    registrar(client)
    medico, esp = _medico_clinico()
    _reservar(client, medico, esp, proximo_dia_habil())
    turno = db.session.scalar(db.select(Turno))
    client.post("/auth/logout")

    registrar(client, email="otro@test.com", dni="28999888")
    assert client.post(f"/turnos/{turno.id}?metodo=DELETE").status_code == 403
    assert client.post(f"/turnos/{turno.id}?metodo=PUT", data={"fecha": "2030-01-01", "hora": "10:00"}).status_code == 403
    assert client.get(f"/turnos/{turno.id}/reprogramar").status_code == 403


def test_no_se_reserva_fin_de_semana_ni_fuera_de_rango(client):
    registrar(client)
    medico, esp = _medico_clinico()
    sabado = servicio.hoy()
    while sabado.weekday() != 5:
        sabado += timedelta(days=1)
    assert servicio.horarios_libres(medico.id, sabado) == []
    r = _reservar(client, medico, esp, sabado)
    assert db.session.scalar(db.select(Turno)) is None
    assert "no es válida" in r.get_data(as_text=True)


# ---------- administrativo ----------
def test_panel_admin_solo_para_admin(client):
    registrar(client)
    assert client.get("/admin/turnos").status_code == 403
    client.post("/auth/logout")
    login(client, "admin@test.com", "ClaveAdmin123")
    r = client.get("/admin/turnos")
    assert r.status_code == 200 and "Turnos del consultorio" in r.get_data(as_text=True)


def test_admin_marca_ausente_y_elimina_cancelados(client):
    registrar(client)
    medico, esp = _medico_clinico()
    _reservar(client, medico, esp, proximo_dia_habil())
    turno = db.session.scalar(db.select(Turno))
    paciente = turno.paciente
    client.post("/auth/logout")

    login(client, "admin@test.com", "ClaveAdmin123")
    client.post(f"/admin/turnos/{turno.id}/estado?metodo=PATCH", data={"estado": "Ausente"})
    db.session.refresh(turno)
    assert turno.estado == "Ausente"
    assert paciente.ausencias_previas() == 1

    # un turno que no está cancelado no se puede borrar
    client.post(f"/admin/turnos/{turno.id}?metodo=DELETE")
    assert db.session.get(Turno, turno.id) is not None
    # uno cancelado sí
    turno.estado = "Cancelado"
    db.session.commit()
    client.post(f"/admin/turnos/{turno.id}?metodo=DELETE")
    assert db.session.get(Turno, turno.id) is None


# ---------- IA ----------
def test_modelo_cargado_y_prediccion_coherente(app):
    from app.ia.predictor import predictor

    assert predictor.disponible
    bajo = predictor.predecir(dias_anticipacion=1, hora=11, dia_semana=2, edad=50, ausencias_previas=0)
    alto = predictor.predecir(dias_anticipacion=55, hora=16, dia_semana=4, edad=22, ausencias_previas=3)
    assert 0 <= bajo["probabilidad"] <= 1
    assert alto["probabilidad"] > bajo["probabilidad"]
    assert bajo["nivel"] == "bajo" and alto["nivel"] == "alto"


def test_endpoint_json_de_prediccion(client):
    datos = {"dias_anticipacion": 30, "hora": 9, "dia_semana": 0, "edad": 25, "ausencias_previas": 1}
    assert client.post("/ia/api/predecir", json=datos).status_code == 401  # sin sesión
    registrar(client)
    r = client.post("/ia/api/predecir", json=datos)
    assert r.status_code == 200
    cuerpo = r.get_json()
    assert 0 <= cuerpo["probabilidad"] <= 1 and cuerpo["nivel"] in ("bajo", "medio", "alto")
    malo = client.post("/ia/api/predecir", json={**datos, "hora": 3})
    assert malo.status_code == 400


def test_pantalla_de_prediccion(client):
    registrar(client)
    assert client.get("/ia/predecir").status_code == 200
    r = client.post(
        "/ia/predecir",
        data={"dias_anticipacion": 20, "hora": 10, "dia_semana": 1, "edad": 35, "ausencias_previas": 0},
    )
    assert "Resultado" in r.get_data(as_text=True)


# ---------- configuración ----------
def test_url_de_base_de_datos(monkeypatch):
    # Render entrega "postgres://"; siempre se fuerza el driver psycopg2.
    monkeypatch.setenv("DATABASE_URL", "postgres://usuario:clave@host:5432/db")
    assert _url_base_de_datos() == "postgresql+psycopg2://usuario:clave@host:5432/db"
    monkeypatch.setenv("DATABASE_URL", "postgresql://usuario:clave@host:5432/db")
    assert _url_base_de_datos() == "postgresql+psycopg2://usuario:clave@host:5432/db"
    monkeypatch.setenv("DATABASE_URL", "")
    assert _url_base_de_datos().startswith("sqlite")


def test_sin_secret_key_no_arranca():
    class SinClave(TestConfig):
        SECRET_KEY = None

    with pytest.raises(RuntimeError):
        create_app(SinClave)


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.get_json() == {"estado": "ok"}
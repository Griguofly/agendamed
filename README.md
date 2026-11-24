# AgendaMed · Prototipo funcional (Segunda Entrega)

Versión mínima y recortada del sistema definido en el SRS de la primera entrega (*AgendaMed: gestión de turnos y pacientes para consultorios médicos*), hecha en **Flask** e integrando un **modelo de Machine Learning** (regresión logística con scikit-learn).

- **Materia:** Análisis y Metodología de Sistemas · Escuela Da Vinci · Comisión ACM4AV
- **Alumnos:** Ezequiel Sanzoni · Mateo Griguoli
- **Requisito principal que se implementa de punta a punta:** RF-02 *Solicitar un turno* (CU-01), junto con RF-03 *Cancelar* y RF-04 *Reprogramar*.

## Qué hace

| Rol | Qué puede hacer |
|---|---|
| Paciente | Registrarse e ingresar, pedir un turno en 3 pasos (especialidad y médico → día y horario → confirmación), ver sus turnos, reprogramarlos y cancelarlos. |
| Administrativo | Ver todos los turnos con el **riesgo de ausencia** que calculó la IA, marcar turnos como Atendido o Ausente, y eliminar turnos cancelados. |
| Cualquier usuario con sesión | Usar el **Predictor de ausentismo** (pantalla web y API JSON). |

## Qué se recortó respecto del SRS

| SRS | Prototipo |
|---|---|
| D4 Consultas (RF-09) | No incluido. |
| D5 Disponibilidad (RF-07) | Reemplazada por una grilla fija: lunes a viernes, 09:00 a 17:00, turnos de 30 minutos, hasta 30 días hacia adelante. |
| RF-05 y RF-06 (ABM de médicos y especialidades) | Se cargan solos al iniciar (8 médicos ficticios y 5 especialidades). |
| RF-10 Recordatorios, RF-11 Reportes | No incluidos. La IA de ausentismo apunta al mismo problema que ellos (reducir el ausentismo). |
| Roles Paciente / Médico / Administrativo | Dos roles: paciente y administrativo. |

## Tecnologías

Flask 3 (patrón **App Factory** + **Blueprints**) · SQLAlchemy (SQLite en desarrollo, **PostgreSQL** en producción) · Jinja2 · Flask-Login · **Bcrypt** · Flask-WTF (protección CSRF) · python-dotenv · scikit-learn + joblib · gunicorn.

## Estructura

```
run.py                  punto de entrada (gunicorn run:app)
config.py               configuración leída de variables de entorno (.env)
app/
  __init__.py           create_app() (App Factory)
  models.py             Paciente, Médico, Especialidad, Turno
  seed.py               datos iniciales
  auth/                 registro, login, logout
  turnos/               CRUD de turnos (routes.py) y reglas de negocio (servicio.py)
  admin/                panel del administrativo
  ia/                   carga del modelo y predicciones
  templates/ static/    plantillas Jinja2 y estilos
ml/                     dataset sintético, script de entrenamiento y modelo .joblib
tests/                  pruebas automáticas (pytest)
```

## Cómo correrlo en tu computadora

Se recomienda Python 3.13 (la misma versión que usa Render, ver `.python-version`). Desde la carpeta del proyecto:

```bash
python -m venv .venv
# Windows:   .venv\Scripts\activate
# Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env        # en Windows: copy .env.example .env
# editar .env: poner un SECRET_KEY largo y la clave del administrativo

python run.py
```

Abrir http://127.0.0.1:5000. Al iniciar se crean las tablas y los datos iniciales. Para entrar como administrativo se usan `ADMIN_EMAIL` y `ADMIN_PASSWORD` del `.env`; los pacientes se registran desde la pantalla *Registrarme*.

Para generar una clave secreta: `python -c "import secrets; print(secrets.token_hex(32))"`.

### Pruebas automáticas

```bash
pip install -r requirements-dev.txt
pytest
```

Por defecto las pruebas usan SQLite en memoria. Con un PostgreSQL local se pueden correr contra él definiendo `TEST_DATABASE_URL` (por ejemplo `postgresql://usuario@localhost:5432/agendamed_test`, con la base creada en UTF8).

## Modelo de IA

- **Qué predice:** la probabilidad de que un paciente **no se presente** a un turno (ausentismo, el problema central del SRS).
- **Modelo:** regresión logística de scikit-learn dentro de un `Pipeline` con `StandardScaler`.
- **Variables:** días entre la reserva y el turno, hora, día de la semana, edad y ausencias previas del paciente.
- **Datos:** **sintéticos** (`ml/generar_dataset.py`), porque no disponemos de datos reales de un consultorio. Se generaron con supuestos razonables (más días de anticipación y más ausencias previas aumentan la probabilidad de faltar), así que el modelo sirve para demostrar la integración, no para usar con pacientes reales.
- **Métricas (datos de prueba):** AUC 0,69. La accuracy (0,81) es igual a la de un modelo que siempre dice "va a asistir" (0,81), por eso el modelo se usa para estimar una probabilidad y un nivel de riesgo (bajo / medio / alto), no para decir sí o no. Están en `ml/metricas.json`.
- **Entrenamiento:** `python ml/entrenar_modelo.py` guarda `ml/modelo_ausentismo.joblib`, que la app carga **una sola vez al iniciar**.
- **Dónde se usa:**
  - al reservar o reprogramar un turno se calcula y guarda su riesgo (`Turno.prob_ausencia`), que ve el administrativo;
  - `GET/POST /ia/predecir`: pantalla donde el usuario ingresa datos y recibe la predicción al instante;
  - `POST /ia/api/predecir`: lo mismo en JSON, con sesión iniciada.

  ```json
  {"dias_anticipacion": 30, "hora": 9, "dia_semana": 0, "edad": 25, "ausencias_previas": 1}
  ```

## Rutas principales

| Método | Ruta | Qué hace | Requisito |
|---|---|---|---|
| GET/POST | `/auth/registro` | Registrar paciente (contraseña con Bcrypt) | RF-01 |
| GET/POST | `/auth/login` · POST `/auth/logout` | Iniciar y cerrar sesión | RNF-02 |
| GET | `/turnos/nuevo` · `/turnos/nuevo/horarios` · `/turnos/nuevo/confirmar` | Los 3 pasos de la reserva | RF-02 |
| **POST** | `/turnos/` | **Create:** crear el turno | RF-02 |
| **GET** | `/turnos/` | **Read:** listar mis turnos | RF-02 |
| **PUT/PATCH** | `/turnos/<id>` | **Update:** reprogramar | RF-04 |
| **DELETE** | `/turnos/<id>` | **Delete:** cancelar y liberar el horario | RF-03 |
| GET | `/admin/turnos` | Panel del administrativo con riesgo de ausencia | — |
| PATCH / DELETE | `/admin/turnos/<id>/estado` · `/admin/turnos/<id>` | Marcar Atendido/Ausente · eliminar un turno cancelado | — |

Los formularios HTML solo envían GET y POST, así que para PUT, PATCH y DELETE se agrega `?metodo=PUT` (o `PATCH` / `DELETE`) a la URL del formulario. Un pequeño middleware (`MethodOverrideMiddleware` en `app/__init__.py`) lo convierte en el método real antes de que Flask enrute la petición.

**Sobre Delete:** en el SRS (E3) cancelar un turno lo pasa a estado *Cancelado* y libera el horario, sin borrar el registro, para poder medir el ausentismo. Por eso `DELETE /turnos/<id>` hace esa baja lógica. El borrado físico existe del lado del administrativo: `DELETE /admin/turnos/<id>`, solo para turnos ya cancelados.

## Trazabilidad del requisito principal (RF-02 · Solicitar turno)

| Capa | Elemento |
|---|---|
| Requisito | RF-02: solicitar un turno eligiendo especialidad, médico, fecha y horario |
| Acontecimiento | E2: el paciente solicita un turno |
| DFD | Proceso 2.0 *Gestionar turnos* → almacenes D1 Pacientes, D2 Turnos, D3 Médicos, D6 Especialidades (D5 Disponibilidad: grilla fija en el prototipo) |
| Caso de uso | CU-01 *Solicitar turno*: 8 pasos del flujo principal y flujos alternativos A1 a A4 |
| DER | Entidades Paciente, Turno, Médico, Especialidad (relaciones `solicita`, `atiende`, `clasifica`, `se especializa en`) |
| Base de datos | Tablas `paciente`, `turno`, `medico`, `especialidad`, `medico_especialidad` (`app/models.py`) |
| Regla de negocio | `crear_turno()` en `app/turnos/servicio.py` |
| Ruta (backend) | `POST /turnos/` → `crear()` en `app/turnos/routes.py` |
| Interfaz | `nuevo.html` → `horarios.html` → `confirmar.html` → `mis_turnos.html` |

Cómo se resuelven los flujos del CU-01:

- **A1, horario ya tomado:** un índice único en la base impide dos turnos vigentes del mismo médico en el mismo horario. Si dos pacientes confirman a la vez, el segundo recibe el aviso y vuelve a elegir horario.
- **A2, paciente sin sesión:** todas las rutas de turnos piden iniciar sesión.
- **A3, el paciente abandona:** no se registra nada hasta el paso de confirmación.
- **A4, sin disponibilidad:** la pantalla de horarios lo informa y sugiere otro día o médico.

Balanceo: los almacenes D1, D2, D3 y D6 del DFD corresponden a las tablas `paciente`, `turno`, `medico` y `especialidad`, con los mismos atributos del Diccionario de Datos (la lista de especialidades de D3 es la tabla `medico_especialidad`).

## Seguridad y buenas prácticas

- Contraseñas con **Bcrypt**; nunca se guardan en texto plano.
- **Sin secretos en el código:** `SECRET_KEY`, `DATABASE_URL` y las credenciales del administrativo salen de variables de entorno (`.env`, incluido en `.gitignore`). El repositorio solo trae `.env.example`.
- Protección **CSRF** en todos los formularios, cookies de sesión `HttpOnly` y `SameSite=Lax` (y `Secure` con `COOKIE_SECURE=1`).
- Cada paciente solo puede ver y modificar **sus** turnos; el panel admin devuelve 403 a quien no es administrativo.
- La redirección posterior al login solo acepta rutas internas.

## Despliegue en Render (GitHub + PostgreSQL)

1. **Subir el código a GitHub** (repositorio público). El `.env` no se sube: lo evita el `.gitignore`.
2. En Render: **New → PostgreSQL**. Nombre `agendamed-db`, plan **Free**. Cuando esté lista, copiar la **Internal Database URL**.
3. En Render: **New → Web Service** y conectar el repositorio de GitHub.
   - **Runtime:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn run:app`
   - **Instance type:** Free
4. En **Environment** del Web Service cargar las variables:

   | Variable | Valor |
   |---|---|
   | `SECRET_KEY` | un texto largo y aleatorio (se puede generar con el comando de arriba) |
   | `DATABASE_URL` | la Internal Database URL de PostgreSQL |
   | `ADMIN_EMAIL` | el email del administrativo |
   | `ADMIN_PASSWORD` | una contraseña segura |
   | `COOKIE_SECURE` | `1` |

5. **Deploy.** La versión de Python se fija con el archivo `.python-version` (3.13), la misma con la que se entrenó el modelo. Al iniciar, la app crea las tablas en PostgreSQL y carga los datos iniciales.
6. Cada `git push` a la rama principal vuelve a desplegar automáticamente.

Notas del plan gratuito de Render: la base PostgreSQL free **vence a los 30 días de creada**, y el servicio web se duerme tras un rato sin visitas, por lo que el primer ingreso puede tardar en cargar.

El endpoint `GET /health` responde `{"estado": "ok"}` si la app y la base están funcionando.
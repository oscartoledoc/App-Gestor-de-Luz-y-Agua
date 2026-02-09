# =======================================================
# Archivo 1: api/index.py
# Código principal de la aplicación Flask (Versión Final con Filtros, Lógica Temporal y Popup de Detalle)
# =======================================================

from flask import Flask, render_template_string, request, redirect, url_for, session, make_response
from datetime import datetime, timedelta
import json
import os
import firebase_admin
from firebase_admin import credentials, firestore
from firebase_admin.exceptions import FirebaseError

# Asegúrate de que el objeto de la app se llame 'app'
app = Flask(__name__)
app.secret_key = os.urandom(24) # Clave secreta para las sesiones
app.permanent_session_lifetime = timedelta(minutes=30) # Duración de la sesión: 30 minutos

# =======================================================
# Configuración y conexión a Firestore
# =======================================================
try:
    if os.environ.get('FIREBASE_CREDENTIALS'):
        cred_json = json.loads(os.environ.get('FIREBASE_CREDENTIALS'))
        cred = credentials.Certificate(cred_json)
    else:
        # Esto es solo para pruebas locales
        cred = credentials.Certificate("firebase-service-account.json")
    
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
    db = firestore.client()
    print("DEBUG: Conexión a Firebase exitosa.")

except Exception as e:
    print(f"ERROR: Error al inicializar Firebase: {e}")
    db = None

# Parámetros por defecto
NUM_FAMILIAS = 5
COSTO_KWH_DEFECTO = 0.6018
COSTO_M3_DEFECTO = 1.86
IGV_PORCENTAJE = 0.18  # 18% IGV
LOGIN_USER = "admin"
LOGIN_PASS = "123"

# Colecciones de Firestore
FAMILIAS_COLLECTION = "familias"
CONSUMOS_COLLECTION = "consumos"
CONFIG_DOC = "config"
LOGIN_DOC = "login"

# =======================================================
# Lógica de carga y guardado de datos con Firestore
# =======================================================
def cargar_datos_desde_firebase():
    """Carga los datos iniciales o existentes de las familias, consumos y configuración."""
    if db is None:
        return {
            "familias": [{"id": f"familia_{i}", "nombre": f"Familia {i}"} for i in range(1, NUM_FAMILIAS + 1)],
            "consumos": [],
            "config": {"costo_kwh": COSTO_KWH_DEFECTO, "costo_m3": COSTO_M3_DEFECTO, "igv_porcentaje": IGV_PORCENTAJE},
            "login": {"usuario": LOGIN_USER, "contrasena": LOGIN_PASS}
        }
        
    try:
        # Cargar configuración y login
        config_ref = db.collection(CONFIG_DOC).document(LOGIN_DOC)
        config_data = config_ref.get().to_dict()
        if not config_data:
            config_data = {
                "costo_kwh": COSTO_KWH_DEFECTO, "costo_m3": COSTO_M3_DEFECTO, 
                "igv_porcentaje": IGV_PORCENTAJE, "usuario": LOGIN_USER, "contrasena": LOGIN_PASS
            }
            config_ref.set(config_data)
        else:
            if 'igv_porcentaje' not in config_data:
                config_data['igv_porcentaje'] = IGV_PORCENTAJE
                config_ref.update({'igv_porcentaje': IGV_PORCENTAJE})

        # Cargar familias
        familias = []
        familias_ref = db.collection(FAMILIAS_COLLECTION).order_by("id")
        familias_docs = list(familias_ref.stream())
        if not familias_docs:
            for i in range(1, NUM_FAMILIAS + 1):
                familia_id = f"familia_{i}"
                familia_data = {"id": familia_id, "nombre": f"Familia {i}"}
                db.collection(FAMILIAS_COLLECTION).document(familia_id).set(familia_data)
                familias.append(familia_data)
        else:
            familias = [doc.to_dict() for doc in familias_docs]

        # Cargar consumos
        consumos = []
        consumos_ref = db.collection(CONSUMOS_COLLECTION)
        consumos_docs = consumos_ref.stream()
        
        igv_porcentaje = config_data.get('igv_porcentaje', IGV_PORCENTAJE)
        
        for doc in consumos_docs:
            consumo_data = doc.to_dict()
            if 'servicio' not in consumo_data or 'consumo' not in consumo_data or 'lectura' not in consumo_data:
                continue
            consumo_data['id'] = doc.id
            consumos.append(consumo_data)
        
        return {
            "familias": familias,
            "consumos": consumos,
            "config": {
                "costo_kwh": config_data.get("costo_kwh"),
                "costo_m3": config_data.get("costo_m3"),
                "igv_porcentaje": igv_porcentaje
            },
            "login": {
                "usuario": config_data.get("usuario"),
                "contrasena": config_data.get("contrasena")
            }
        }
    except Exception as e:
        print(f"ERROR: Error al leer datos: {e}")
        return {
            "familias": [{"id": f"familia_{i}", "nombre": f"Familia {i}"} for i in range(1, NUM_FAMILIAS + 1)],
            "consumos": [],
            "config": {"costo_kwh": COSTO_KWH_DEFECTO, "costo_m3": COSTO_M3_DEFECTO, "igv_porcentaje": IGV_PORCENTAJE},
            "login": {"usuario": LOGIN_USER, "contrasena": LOGIN_PASS}
        }

def guardar_consumo_en_firebase(nuevo_consumo):
    if db is None: return False
    try:
        nuevo_consumo['timestamp'] = firestore.SERVER_TIMESTAMP
        db.collection(CONSUMOS_COLLECTION).add(nuevo_consumo)
        return True
    except Exception as e:
        print(f"ERROR: Error al guardar: {e}")
        return False

def actualizar_familias_y_costos(familias_data, costos_data):
    if db is None: return False
    try:
        for familia in familias_data:
            db.collection(FAMILIAS_COLLECTION).document(familia['id']).update({"nombre": familia['nombre']})
        db.collection(CONFIG_DOC).document(LOGIN_DOC).update(costos_data)
        return True
    except Exception as e:
        print(f"ERROR: Error al actualizar config: {e}")
        return False

def eliminar_consumo_en_firebase(consumo_id):
    if db is None: return False
    try:
        db.collection(CONSUMOS_COLLECTION).document(consumo_id).delete()
        return True
    except FirebaseError:
        return False

def obtener_consumo_por_id(consumo_id):
    if db is None: return None
    try:
        doc = db.collection(CONSUMOS_COLLECTION).document(consumo_id).get()
        if doc.exists:
            consumo = doc.to_dict()
            consumo['id'] = doc.id
            return consumo
        return None
    except FirebaseError:
        return None

def actualizar_consumo_en_firebase(consumo_id, nuevos_datos):
    if db is None: return False
    try:
        nuevos_datos['timestamp'] = firestore.SERVER_TIMESTAMP
        db.collection(CONSUMOS_COLLECTION).document(consumo_id).update(nuevos_datos)
        return True
    except FirebaseError:
        return False

# =======================================================
# FUNCIÓN CORE: CALCULAR LECTURA ANTERIOR (TIME-AWARE)
# =======================================================
def calcular_lectura_anterior(familia_id, servicio, fecha_corte, excluir_id=None):
    """
    Busca la lectura más reciente que sea estrictamente ANTERIOR a la fecha_corte.
    """
    lectura_anterior = 0
    if db is None: return 0

    try:
        # 1. Traer todos los consumos de esa familia y servicio
        consumos_ref = db.collection(CONSUMOS_COLLECTION)\
                         .where("familia_id", "==", familia_id)\
                         .where("servicio", "==", servicio)
        
        docs = consumos_ref.stream()
        
        candidatos = []
        for doc in docs:
            # Si estamos editando, saltar el documento actual para no compararlo consigo mismo
            if excluir_id and doc.id == excluir_id:
                continue
            
            data = doc.to_dict()
            # 2. FILTRO CLAVE: Solo registros con fecha MENOR a la actual
            if data.get('fecha', '9999-99-99') < fecha_corte:
                candidatos.append(data)
        
        # 3. Ordenar: El más reciente de los pasados va primero
        if candidatos:
            candidatos.sort(key=lambda x: x.get('fecha', '0'), reverse=True)
            lectura_anterior = candidatos[0].get('lectura', 0)
            print(f"DEBUG: Lectura anterior encontrada ({candidatos[0]['fecha']}): {lectura_anterior}")
        else:
            print("DEBUG: No hay lecturas previas a esta fecha. Se inicia en 0.")

    except Exception as e:
        print(f"ERROR: Fallo al calcular lectura anterior: {e}")
    
    return lectura_anterior

# =======================================================
# Rutas de la aplicación
# =======================================================

@app.before_request
def verificar_login():
    if 'usuario' not in session and request.endpoint not in ['login', 'static']:
        return redirect(url_for('login'))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        usuario = request.form.get("usuario")
        contrasena = request.form.get("contrasena")
        datos = cargar_datos_desde_firebase()
        
        if usuario == datos["login"]["usuario"] and contrasena == datos["login"]["contrasena"]:
            session.permanent = True # Activa los 30 minutos
            session['usuario'] = usuario
            return redirect(url_for('index'))
        else:
            return render_template_string(LOGIN_HTML, error="Usuario o contraseña incorrectos.")
    return render_template_string(LOGIN_HTML)

@app.route("/logout")
def logout():
    session.pop('usuario', None)
    return redirect(url_for('login'))

@app.route("/", methods=["GET", "POST"])
def index():
    datos = cargar_datos_desde_firebase()
    mensaje = ""

    if request.method == "POST":
        try:
            familia_id = request.form["familia"]
            servicio = request.form["servicio"]
            fecha = request.form["fecha"]
            lectura_actual = float(request.form["lectura"])
        except (ValueError, KeyError):
            mensaje = "Error: Por favor, introduce datos válidos."
            return render_template_string(INDEX_HTML, familias=datos["familias"], historial=datos["consumos"], config=datos["config"], mensaje=mensaje)

        familia_nombre = [f['nombre'] for f in datos['familias'] if f['id'] == familia_id][0]
        
        # === USO DE LA NUEVA LÓGICA ===
        lectura_anterior = calcular_lectura_anterior(familia_id, servicio, fecha)
        # ==============================

        consumo = max(0, lectura_actual - lectura_anterior)
        
        if servicio == "Luz":
            costo_unidad = datos["config"]["costo_kwh"]
            unidad = "kWh"
        else:
            costo_unidad = datos["config"]["costo_m3"]
            unidad = "m³"

        subtotal = consumo * costo_unidad
        igv_porcentaje = datos["config"]["igv_porcentaje"]
        igv_monto = subtotal * igv_porcentaje
        costo_total = subtotal + igv_monto
        
        nuevo_consumo = {
            "fecha": fecha,
            "familia_id": familia_id,
            "familia_nombre": familia_nombre,
            "servicio": servicio,
            "lectura": lectura_actual,
            "lectura_anterior": lectura_anterior,
            "consumo": consumo,
            "unidad": unidad,
            "subtotal": subtotal,
            "igv_monto": igv_monto,
            "costo_total": costo_total
        }
        
        if guardar_consumo_en_firebase(nuevo_consumo):
            mensaje = "Datos guardados correctamente."
        else:
            mensaje = "Error al guardar los datos."
        
        return redirect(url_for('index', mensaje=mensaje))
    
    historial = sorted(datos["consumos"], key=lambda x: x.get("timestamp") or x.get("fecha", '0'), reverse=True)
    return render_template_string(INDEX_HTML, familias=datos["familias"], historial=historial, config=datos["config"], mensaje=request.args.get('mensaje', ''))


@app.route("/configuracion", methods=["GET", "POST"])
def configuracion():
    datos = cargar_datos_desde_firebase()
    mensaje = ""
    if request.method == "POST":
        try:
            familias_actualizadas = []
            for familia in datos["familias"]:
                nuevo_nombre = request.form.get(f"familia_nombre_{familia['id']}")
                familias_actualizadas.append({"id": familia['id'], "nombre": nuevo_nombre})
            
            costos_actualizados = {
                "costo_kwh": float(request.form["costo_kwh"]),
                "costo_m3": float(request.form["costo_m3"]),
                "igv_porcentaje": float(request.form["igv_porcentaje"])
            }
            
            if actualizar_familias_y_costos(familias_actualizadas, costos_actualizados):
                mensaje = "Configuración guardada correctamente."
            else:
                mensaje = "Error al guardar la configuración."
        except (ValueError, KeyError):
            mensaje = "Error: Datos inválidos."
    
    datos = cargar_datos_desde_firebase()
    return render_template_string(CONFIG_HTML, familias=datos["familias"], config=datos["config"], mensaje=mensaje)

@app.route("/eliminar/<string:consumo_id>", methods=["POST"])
def eliminar_consumo(consumo_id):
    if eliminar_consumo_en_firebase(consumo_id):
        return redirect(url_for('index', mensaje="Registro eliminado correctamente."))
    else:
        return redirect(url_for('index', mensaje="Error al eliminar el registro."))

@app.route("/editar/<string:consumo_id>", methods=["GET"])
def editar_consumo(consumo_id):
    consumo = obtener_consumo_por_id(consumo_id)
    if not consumo:
        return redirect(url_for('index', mensaje="Registro no encontrado."))
    datos = cargar_datos_desde_firebase()
    return render_template_string(EDIT_HTML, consumo=consumo, familias=datos["familias"], mensaje=request.args.get('mensaje', ''))

@app.route("/actualizar/<string:consumo_id>", methods=["POST"])
def actualizar_consumo(consumo_id):
    datos_globales = cargar_datos_desde_firebase()
    mensaje = ""
    try:
        familia_id = request.form["familia"]
        servicio = request.form["servicio"]
        fecha = request.form["fecha"]
        lectura_actual = float(request.form["lectura"])

        familia_nombre = [f['nombre'] for f in datos_globales['familias'] if f['id'] == familia_id][0]
        
        # === USO DE LA NUEVA LÓGICA (CON EXCLUSIÓN DEL ID ACTUAL) ===
        lectura_anterior = calcular_lectura_anterior(familia_id, servicio, fecha, excluir_id=consumo_id)
        # ============================================================

        consumo_valor = max(0, lectura_actual - lectura_anterior)
        
        if servicio == "Luz":
            costo_unidad = datos_globales["config"]["costo_kwh"]
            unidad = "kWh"
        else:
            costo_unidad = datos_globales["config"]["costo_m3"]
            unidad = "m³"
        
        igv_porcentaje = datos_globales["config"]["igv_porcentaje"]
        subtotal = consumo_valor * costo_unidad
        igv_monto = subtotal * igv_porcentaje
        costo_total = subtotal + igv_monto
        
        nuevos_datos = {
            "fecha": fecha,
            "familia_id": familia_id,
            "familia_nombre": familia_nombre,
            "servicio": servicio,
            "lectura": lectura_actual,
            "lectura_anterior": lectura_anterior,
            "consumo": consumo_valor,
            "unidad": unidad,
            "subtotal": subtotal,
            "igv_monto": igv_monto,
            "costo_total": costo_total
        }
        
        if actualizar_consumo_en_firebase(consumo_id, nuevos_datos):
            mensaje = "Registro actualizado correctamente."
        else:
            mensaje = "Error al actualizar el registro."
    
    except (ValueError, KeyError):
        mensaje = "Error: Por favor, introduce datos válidos."

    return redirect(url_for('index', mensaje=mensaje))


# =======================================================
# HTML de la aplicación (plantillas)
# =======================================================

LOGIN_HTML = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Login - App de Consumo</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style> body { font-family: 'Inter', sans-serif; } </style>
</head>
<body class="bg-gray-100 flex items-center justify-center h-screen">
    <div class="bg-white p-8 rounded-2xl shadow-xl w-full max-w-md">
        <h2 class="text-3xl font-bold text-center mb-6 text-gray-800">Iniciar Sesión</h2>
        {% if error %}
        <p class="bg-red-100 border-l-4 border-red-500 text-red-700 p-4 mb-4 rounded-xl">{{ error }}</p>
        {% endif %}
        <form action="{{ url_for('login') }}" method="POST">
            <div class="mb-4">
                <label for="usuario" class="block text-gray-700 text-sm font-semibold mb-2">Usuario</label>
                <input type="text" id="usuario" name="usuario" class="shadow appearance-none border rounded-xl w-full py-3 px-4 text-gray-700 leading-tight focus:outline-none focus:shadow-outline transition duration-200" required>
            </div>
            <div class="mb-6">
                <label for="contrasena" class="block text-gray-700 text-sm font-semibold mb-2">Contraseña</label>
                <input type="password" id="contrasena" name="contrasena" class="shadow appearance-none border rounded-xl w-full py-3 px-4 text-gray-700 mb-3 leading-tight focus:outline-none focus:shadow-outline transition duration-200" required>
            </div>
            <div class="flex items-center justify-between">
                <button type="submit" class="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-3 px-4 rounded-xl focus:outline-none focus:shadow-outline transition-all duration-300">Entrar</button>
            </div>
        </form>
    </div>
</body>
</html>
"""

INDEX_HTML = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>App de Consumo</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        body { font-family: 'Inter', sans-serif; }
        .tooltip-container { position: relative; display: inline-block; }
        .tooltip { visibility: hidden; width: 140px; background-color: #333; color: #fff; text-align: center; border-radius: 6px; padding: 5px 0; position: absolute; z-index: 10; bottom: 125%; left: 50%; margin-left: -70px; opacity: 0; transition: opacity 0.3s; }
        .tooltip::after { content: ""; position: absolute; top: 100%; left: 50%; margin-left: -5px; border-width: 5px; border-style: solid; border-color: #333 transparent transparent transparent; }
        .tooltip-container:hover .tooltip { visibility: visible; opacity: 1; }
    </style>
</head>
<body class="bg-gray-100 min-h-screen p-4 md:p-8">
    <div class="container mx-auto">
        <div class="bg-white rounded-2xl shadow-xl p-6 mb-8 flex flex-col md:flex-row items-center justify-between">
            <h1 class="text-3xl font-bold text-gray-800 mb-4 md:mb-0">Gestor de Consumos</h1>
            <nav class="flex space-x-4">
                <a href="{{ url_for('index') }}" class="py-2 px-4 text-gray-700 font-semibold rounded-lg hover:bg-blue-100 transition-colors duration-200">Inicio</a>
                <a href="{{ url_for('configuracion') }}" class="py-2 px-4 text-gray-700 font-semibold rounded-lg hover:bg-blue-100 transition-colors duration-200">Configuración</a>
                <a href="{{ url_for('logout') }}" class="py-2 px-4 text-gray-700 font-semibold rounded-lg hover:bg-red-100 transition-colors duration-200">Cerrar Sesión</a>
            </nav>
        </div>

        {% if mensaje %}
        <div class="bg-green-100 border-l-4 border-green-500 text-green-700 p-4 rounded-xl mb-6 shadow-md">{{ mensaje }}</div>
        {% endif %}

        <div class="bg-white rounded-2xl shadow-xl p-6 md:p-8 mb-8">
            <h2 class="text-2xl font-bold mb-6 text-gray-800">Ingresar Lectura</h2>
            <form action="{{ url_for('index') }}" method="POST" class="space-y-6">
                <div>
                    <label for="familia" class="block text-sm font-medium text-gray-700 mb-2">Seleccionar Familia:</label>
                    <select id="familia" name="familia" class="mt-1 block w-full pl-3 pr-10 py-2 text-base border-gray-300 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm rounded-xl shadow-sm transition duration-200" required>
                        <option value="" disabled selected>-- Selecciona una familia --</option>
                        {% for familia in familias %}
                        <option value="{{ familia.id }}">{{ familia.nombre }}</option>
                        {% endfor %}
                    </select>
                </div>
                <div>
                    <label for="servicio" class="block text-sm font-medium text-gray-700 mb-2">Seleccionar Servicio:</label>
                    <select id="servicio" name="servicio" class="mt-1 block w-full pl-3 pr-10 py-2 text-base border-gray-300 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm rounded-xl shadow-sm transition duration-200">
                        <option value="Luz">Luz (kWh)</option>
                        <option value="Agua">Agua (m³)</option>
                    </select>
                </div>
                <div>
                    <label for="fecha" class="block text-sm font-medium text-gray-700 mb-2">Fecha:</label>
                    <input type="date" id="fecha" name="fecha" class="mt-1 block w-full shadow-sm sm:text-sm border-gray-300 rounded-xl py-2 px-3 focus:ring-blue-500 focus:border-blue-500 transition duration-200" required>
                </div>
                <div>
                    <label for="lectura" class="block text-sm font-medium text-gray-700 mb-2">Ingresar Lectura del Medidor:</label>
                    <option value="" disabled selected>-- Ingrese aquí --</option>
                    <input type="number" step="0.01" id="lectura" name="lectura" class="mt-1 block w-full shadow-sm sm:text-sm border-gray-300 rounded-xl py-2 px-3 focus:ring-blue-500 focus:border-blue-500 transition duration-200" required>
                </div>
                <div class="flex justify-end">
                    <button type="submit" class="inline-flex items-center px-6 py-3 border border-transparent text-sm font-medium rounded-xl shadow-sm text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 transition-all duration-300 transform hover:scale-105">Guardar Lectura</button>
                </div>
            </form>
        </div>
        
        <div class="bg-white rounded-2xl shadow-xl p-6 md:p-8">
            <div class="flex flex-col md:flex-row justify-between items-center mb-6">
                <h2 class="text-2xl font-bold text-gray-800 mb-4 md:mb-0">Historial de Consumos</h2>
                
                <div class="flex flex-col md:flex-row gap-4 w-full md:w-auto">
                    <select id="filtroFamilia" onchange="aplicarFiltros()" class="border-gray-300 focus:outline-none focus:ring-blue-500 focus:border-blue-500 rounded-xl shadow-sm text-sm py-2 px-3">
                        <option value="">Todas las Familias</option>
                        {% for familia in familias %}
                        <option value="{{ familia.nombre }}">{{ familia.nombre }}</option>
                        {% endfor %}
                    </select>
                    <select id="filtroServicio" onchange="aplicarFiltros()" class="border-gray-300 focus:outline-none focus:ring-blue-500 focus:border-blue-500 rounded-xl shadow-sm text-sm py-2 px-3">
                        <option value="">Todos los Servicios</option>
                        <option value="Luz">Luz</option>
                        <option value="Agua">Agua</option>
                    </select>
                </div>
            </div>

            <div class="overflow-x-auto">
                <table class="min-w-full divide-y divide-gray-200 rounded-xl">
                    <thead class="bg-gray-50">
                        <tr>
                            <th scope="col" class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Fecha</th>
                            <th scope="col" class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Familia</th>
                            <th scope="col" class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Servicio</th>
                            <th scope="col" class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Lectura Anterior</th>
                            <th scope="col" class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Lectura Actual</th>
                            <th scope="col" class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Consumo</th>
                            <th scope="col" class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Costo Total</th>
                            <th scope="col" class="relative px-6 py-3"><span class="sr-only">Editar</span></th>
                            <th scope="col" class="relative px-6 py-3"><span class="sr-only">Eliminar</span></th>
                        </tr>
                    </thead>
                    <tbody class="bg-white divide-y divide-gray-200">
                        {% for consumo in historial %}
                        <tr class="hover:bg-gray-100 transition-colors duration-100 fila-dato cursor-pointer" 
                            onclick="abrirModal(this)"
                            data-fecha="{{ consumo.fecha }}"
                            data-familia="{{ consumo.familia_nombre }}"
                            data-servicio="{{ consumo.servicio }}"
                            data-lectura-ant="{{ '%.2f'|format(consumo.lectura_anterior) }} {{ consumo.unidad }}"
                            data-lectura-act="{{ '%.2f'|format(consumo.lectura) }} {{ consumo.unidad }}"
                            data-consumo="{{ '%.2f'|format(consumo.consumo) }} {{ consumo.unidad }}"
                            data-subtotal="S/ {{ '%.2f'|format(consumo.subtotal) }}"
                            data-igv="S/ {{ '%.2f'|format(consumo.igv_monto) }}"
                            data-total="S/ {{ '%.2f'|format(consumo.costo_total) }}">
                            
                            <td class="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">{{ consumo.fecha }}</td>
                            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500 celda-familia">{{ consumo.familia_nombre }}</td>
                            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500 celda-servicio">{{ consumo.servicio }}</td>
                            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">{{ "%.2f"|format(consumo.lectura_anterior) }} {{ consumo.unidad }}</td>
                            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">{{ "%.2f"|format(consumo.lectura) }} {{ consumo.unidad }}</td>
                            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">{{ "%.2f"|format(consumo.consumo) }} {{ consumo.unidad }}</td>
                            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                                S/ {{ "%.2f"|format(consumo.costo_total) }}
                            </td>
                            <td class="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                                <a href="{{ url_for('editar_consumo', consumo_id=consumo.id) }}" class="text-blue-600 hover:text-blue-900" onclick="event.stopPropagation()">Editar</a>
                            </td>
                            <td class="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                                <form action="{{ url_for('eliminar_consumo', consumo_id=consumo.id) }}" method="POST" onsubmit="return confirm('¿Estás seguro de que deseas eliminar este registro?');" onclick="event.stopPropagation()">
                                    <button type="submit" class="text-red-600 hover:text-red-900">Eliminar</button>
                                </form>
                            </td>
                        </tr>
                        {% else %}
                        <tr>
                            <td colspan="9" class="px-6 py-4 text-center text-sm text-gray-500">No hay datos de consumo registrados aún.</td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>
    </div>

    <div id="modalDetalle" class="fixed inset-0 bg-gray-600 bg-opacity-50 overflow-y-auto h-full w-full hidden z-50 flex items-center justify-center">
        <div class="relative p-5 border w-96 shadow-lg rounded-2xl bg-white">
            <div class="mt-3 text-center">
                <h3 class="text-2xl leading-6 font-bold text-gray-900 mb-4" id="modalTitulo">Detalle de Consumo</h3>
                <div class="mt-2 text-left space-y-3 px-4">
                    <p class="text-sm text-gray-500"><strong>Fecha:</strong> <span id="mFecha"></span></p>
                    <p class="text-sm text-gray-500"><strong>Familia:</strong> <span id="mFamilia"></span></p>
                    <p class="text-sm text-gray-500"><strong>Servicio:</strong> <span id="mServicio"></span></p>
                    <hr>
                    <p class="text-sm text-gray-500"><strong>Lectura Anterior:</strong> <span id="mLecturaAnt"></span></p>
                    <p class="text-sm text-gray-500"><strong>Lectura Actual:</strong> <span id="mLecturaAct"></span></p>
                    <p class="text-sm text-gray-500 font-semibold"><strong>Consumo:</strong> <span id="mConsumo" class="text-blue-600"></span></p>
                    <hr>
                    <p class="text-sm text-gray-500"><strong>Subtotal:</strong> <span id="mSubtotal"></span></p>
                    <p class="text-sm text-gray-500"><strong>IGV (18%):</strong> <span id="mIgv"></span></p>
                    <p class="text-lg text-gray-800 font-bold mt-2"><strong>Total:</strong> <span id="mTotal" class="text-green-600"></span></p>
                </div>
                <div class="items-center px-4 py-3 mt-4">
                    <button id="ok-btn" onclick="cerrarModal()" class="px-4 py-2 bg-blue-600 text-white text-base font-medium rounded-xl w-full shadow-sm hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-300">
                        Cerrar
                    </button>
                </div>
            </div>
        </div>
    </div>

    <script>
        window.addEventListener('DOMContentLoaded', (event) => {
            const today = new Date();
            const year = today.getFullYear();
            const month = String(today.getMonth() + 1).padStart(2, '0');
            const day = String(today.getDate()).padStart(2, '0');
            const formattedDate = `${year}-${month}-${day}`;
            const fechaInput = document.getElementById('fecha');
            if (fechaInput) { fechaInput.value = formattedDate; }
        });

        // === LÓGICA DE FILTRADO JS ===
        function aplicarFiltros() {
            const filtroFamilia = document.getElementById('filtroFamilia').value.toLowerCase();
            const filtroServicio = document.getElementById('filtroServicio').value.toLowerCase();
            const filas = document.querySelectorAll('.fila-dato');

            filas.forEach(fila => {
                const textoFamilia = fila.querySelector('.celda-familia').textContent.toLowerCase();
                const textoServicio = fila.querySelector('.celda-servicio').textContent.toLowerCase();

                const coincideFamilia = filtroFamilia === "" || textoFamilia.includes(filtroFamilia);
                const coincideServicio = filtroServicio === "" || textoServicio.includes(filtroServicio);

                if (coincideFamilia && coincideServicio) {
                    fila.style.display = '';
                } else {
                    fila.style.display = 'none';
                }
            });
        }

        // === LÓGICA DEL MODAL POPUP ===
        function abrirModal(fila) {
            // Leer datos del dataset de la fila
            document.getElementById('mFecha').textContent = fila.dataset.fecha;
            document.getElementById('mFamilia').textContent = fila.dataset.familia;
            document.getElementById('mServicio').textContent = fila.dataset.servicio;
            document.getElementById('mLecturaAnt').textContent = fila.dataset.lecturaAnt;
            document.getElementById('mLecturaAct').textContent = fila.dataset.lecturaAct;
            document.getElementById('mConsumo').textContent = fila.dataset.consumo;
            document.getElementById('mSubtotal').textContent = fila.dataset.subtotal;
            document.getElementById('mIgv').textContent = fila.dataset.igv;
            document.getElementById('mTotal').textContent = fila.dataset.total;

            // Mostrar el modal
            document.getElementById('modalDetalle').classList.remove('hidden');
        }

        function cerrarModal() {
            document.getElementById('modalDetalle').classList.add('hidden');
        }
        
        // Cerrar modal si se hace clic fuera del contenido
        window.onclick = function(event) {
            const modal = document.getElementById('modalDetalle');
            if (event.target == modal) {
                cerrarModal();
            }
        }
    </script>
</body>
</html>
"""

EDIT_HTML = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Editar Consumo - App de Consumo</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style> body { font-family: 'Inter', sans-serif; } </style>
</head>
<body class="bg-gray-100 min-h-screen p-4 md:p-8">
    <div class="container mx-auto">
        <div class="bg-white rounded-2xl shadow-xl p-6 mb-8 flex flex-col md:flex-row items-center justify-between">
            <h1 class="text-3xl font-bold text-gray-800 mb-4 md:mb-0">Gestor de Consumos</h1>
            <nav class="flex space-x-4">
                <a href="{{ url_for('index') }}" class="py-2 px-4 text-gray-700 font-semibold rounded-lg hover:bg-blue-100 transition-colors duration-200">Inicio</a>
                <a href="{{ url_for('configuracion') }}" class="py-2 px-4 text-gray-700 font-semibold rounded-lg hover:bg-blue-100 transition-colors duration-200">Configuración</a>
                <a href="{{ url_for('logout') }}" class="py-2 px-4 text-gray-700 font-semibold rounded-lg hover:bg-red-100 transition-colors duration-200">Cerrar Sesión</a>
            </nav>
        </div>
        
        {% if mensaje %}
        <div class="bg-red-100 border-l-4 border-red-500 text-red-700 p-4 rounded-xl mb-6 shadow-md">{{ mensaje }}</div>
        {% endif %}

        <div class="bg-white rounded-2xl shadow-xl p-6 md:p-8 mb-8">
            <h2 class="text-2xl font-bold mb-6 text-gray-800">Editar Consumo</h2>
            <form action="{{ url_for('actualizar_consumo', consumo_id=consumo.id) }}" method="POST" class="space-y-6">
                <div>
                    <label for="familia" class="block text-sm font-medium text-gray-700 mb-2">Seleccionar Familia:</label>
                    <select id="familia" name="familia" class="mt-1 block w-full pl-3 pr-10 py-2 text-base border-gray-300 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm rounded-xl shadow-sm transition duration-200">
                        {% for familia in familias %}
                        <option value="{{ familia.id }}" {% if consumo.familia_id == familia.id %}selected{% endif %}>{{ familia.nombre }}</option>
                        {% endfor %}
                    </select>
                </div>
                <div>
                    <label for="servicio" class="block text-sm font-medium text-gray-700 mb-2">Seleccionar Servicio:</label>
                    <select id="servicio" name="servicio" class="mt-1 block w-full pl-3 pr-10 py-2 text-base border-gray-300 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm rounded-xl shadow-sm transition duration-200">
                        <option value="Luz" {% if consumo.servicio == 'Luz' %}selected{% endif %}>Luz (kWh)</option>
                        <option value="Agua" {% if consumo.servicio == 'Agua' %}selected{% endif %}>Agua (m³)</option>
                    </select>
                </div>
                <div>
                    <label for="fecha" class="block text-sm font-medium text-gray-700 mb-2">Fecha:</label>
                    <input type="date" id="fecha" name="fecha" value="{{ consumo.fecha }}" class="mt-1 block w-full shadow-sm sm:text-sm border-gray-300 rounded-xl py-2 px-3 focus:ring-blue-500 focus:border-blue-500 transition duration-200" required>
                </div>
                <div>
                    <label for="lectura" class="block text-sm font-medium text-gray-700 mb-2">Ingresar Lectura del Medidor:</label>
                    <input type="number" step="0.01" id="lectura" name="lectura" value="{{ consumo.lectura }}" class="mt-1 block w-full shadow-sm sm:text-sm border-gray-300 rounded-xl py-2 px-3 focus:ring-blue-500 focus:border-blue-500 transition duration-200" required>
                </div>
                <div class="flex justify-end space-x-4">
                    <a href="{{ url_for('index') }}" class="inline-flex items-center px-6 py-3 border border-gray-300 text-sm font-medium rounded-xl text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 transition-all duration-300">Cancelar</a>
                    <button type="submit" class="inline-flex items-center px-6 py-3 border border-transparent text-sm font-medium rounded-xl shadow-sm text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 transition-all duration-300 transform hover:scale-105">Guardar Cambios</button>
                </div>
            </form>
        </div>
    </div>
</body>
</html>
"""

CONFIG_HTML = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Configuración - App de Consumo</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style> body { font-family: 'Inter', sans-serif; } </style>
</head>
<body class="bg-gray-100 min-h-screen p-4 md:p-8">
    <div class="container mx-auto">
        <div class="bg-white rounded-2xl shadow-xl p-6 mb-8 flex flex-col md:flex-row items-center justify-between">
            <h1 class="text-3xl font-bold text-gray-800 mb-4 md:mb-0">Gestor de Consumos</h1>
            <nav class="flex space-x-4">
                <a href="{{ url_for('index') }}" class="py-2 px-4 text-gray-700 font-semibold rounded-lg hover:bg-blue-100 transition-colors duration-200">Inicio</a>
                <a href="{{ url_for('configuracion') }}" class="py-2 px-4 text-gray-700 font-semibold rounded-lg hover:bg-blue-100 transition-colors duration-200">Configuración</a>
                <a href="{{ url_for('logout') }}" class="py-2 px-4 text-gray-700 font-semibold rounded-lg hover:bg-red-100 transition-colors duration-200">Cerrar Sesión</a>
            </nav>
        </div>
        
        {% if mensaje %}
        <div class="bg-green-100 border-l-4 border-green-500 text-green-700 p-4 rounded-xl mb-6 shadow-md">{{ mensaje }}</div>
        {% endif %}

        <div class="bg-white rounded-2xl shadow-xl p-6 md:p-8">
            <h2 class="text-2xl font-bold mb-6 text-gray-800">Ajustar Configuración</h2>
            <form action="{{ url_for('configuracion') }}" method="POST" class="space-y-6">
                <div class="space-y-4">
                    <h3 class="text-xl font-semibold text-gray-700">Nombres de Familias</h3>
                    {% for familia in familias %}
                    <div>
                        <label for="familia_nombre_{{ familia.id }}" class="block text-sm font-medium text-gray-700 mb-1">{{ familia.nombre }}:</label>
                        <input type="text" id="familia_nombre_{{ familia.id }}" name="familia_nombre_{{ familia.id }}" value="{{ familia.nombre }}" class="mt-1 block w-full shadow-sm sm:text-sm border-gray-300 rounded-xl py-2 px-3 focus:ring-blue-500 focus:border-blue-500 transition duration-200">
                    </div>
                    {% endfor %}
                </div>
                
                <hr class="my-6 border-gray-200">

                <div class="space-y-4">
                    <h3 class="text-xl font-semibold text-gray-700">Costos por Unidad (S/)</h3>
                    <div>
                        <label for="costo_kwh" class="block text-sm font-medium text-gray-700 mb-1">Costo por kWh (Luz):</label>
                        <input type="number" step="0.01" id="costo_kwh" name="costo_kwh" value="{{ config.costo_kwh }}" class="mt-1 block w-full shadow-sm sm:text-sm border-gray-300 rounded-xl py-2 px-3 focus:ring-blue-500 focus:border-blue-500 transition duration-200">
                    </div>
                    <div>
                        <label for="costo_m3" class="block text-sm font-medium text-gray-700 mb-1">Costo por m³ (Agua):</label>
                        <input type="number" step="0.01" id="costo_m3" name="costo_m3" value="{{ config.costo_m3 }}" class="mt-1 block w-full shadow-sm sm:text-sm border-gray-300 rounded-xl py-2 px-3 focus:ring-blue-500 focus:border-blue-500 transition duration-200">
                    </div>
                    <div>
                        <label for="igv_porcentaje" class="block text-sm font-medium text-gray-700 mb-1">Porcentaje de IGV (ej: 0.18 para 18%):</label>
                        <input type="number" step="0.01" id="igv_porcentaje" name="igv_porcentaje" value="{{ config.igv_porcentaje }}" class="mt-1 block w-full shadow-sm sm:text-sm border-gray-300 rounded-xl py-2 px-3 focus:ring-blue-500 focus:border-blue-500 transition duration-200">
                    </div>
                </div>

                <div class="flex justify-end">
                    <button type="submit" class="inline-flex items-center px-6 py-3 border border-transparent text-sm font-medium rounded-xl shadow-sm text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 transition-all duration-300 transform hover:scale-105">Guardar Configuración</button>
                </div>
            </form>
        </div>
    </div>
</body>
</html>
"""

if __name__ == '__main__':
    print("DEBUG: Iniciando la aplicación Flask en modo de desarrollo.")
    app.run(debug=True)
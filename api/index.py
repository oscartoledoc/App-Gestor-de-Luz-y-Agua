# =======================================================
# Archivo 1: api/index.py
# Código principal de la aplicación Flask
# =======================================================

from flask import Flask, render_template_string, request, redirect, url_for, session, make_response
from datetime import datetime
import json
import os
import firebase_admin
from firebase_admin import credentials, firestore
from firebase_admin.exceptions import FirebaseError

# Asegúrate de que el objeto de la app se llame 'app'
app = Flask(__name__)
app.secret_key = os.urandom(24) # Clave secreta para las sesiones

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

# Parámetros por defecto (se almacenarán en la base de datos)
NUM_FAMILIAS = 5
COSTO_KWH_DEFECTO = 0.50
COSTO_M3_DEFECTO = 2.00
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
    """
    Carga los datos iniciales o existentes de las familias, consumos y configuración
    desde Firestore.
    """
    if db is None:
        print("DEBUG: La conexión a Firebase falló. Usando datos por defecto.")
        # Retorna datos por defecto si Firebase no está disponible
        return {
            "familias": [{"id": f"familia_{i}", "nombre": f"Familia {i}"} for i in range(1, NUM_FAMILIAS + 1)],
            "consumos": [],
            "config": {
                "costo_kwh": COSTO_KWH_DEFECTO,
                "costo_m3": COSTO_M3_DEFECTO,
                "igv_porcentaje": IGV_PORCENTAJE
            },
            "login": {
                "usuario": LOGIN_USER,
                "contrasena": LOGIN_PASS
            }
        }
        
    try:
        # Cargar configuración y login
        config_ref = db.collection(CONFIG_DOC).document(LOGIN_DOC)
        config_data = config_ref.get().to_dict()
        if not config_data:
            config_data = {
                "costo_kwh": COSTO_KWH_DEFECTO,
                "costo_m3": COSTO_M3_DEFECTO,
                "igv_porcentaje": IGV_PORCENTAJE,
                "usuario": LOGIN_USER,
                "contrasena": LOGIN_PASS
            }
            config_ref.set(config_data)
            print("DEBUG: Se inicializó la configuración en Firestore.")
        else:
            # Asegurar que el campo del IGV exista en la configuración
            if 'igv_porcentaje' not in config_data:
                config_data['igv_porcentaje'] = IGV_PORCENTAJE
                config_ref.update({'igv_porcentaje': IGV_PORCENTAJE})


        # Cargar familias
        familias = []
        familias_ref = db.collection(FAMILIAS_COLLECTION).order_by("id")
        familias_docs = list(familias_ref.stream())
        if not familias_docs:
            print("DEBUG: No se encontraron familias. Inicializando 5 familias.")
            for i in range(1, NUM_FAMILIAS + 1):
                familia_id = f"familia_{i}"
                familia_data = {"id": familia_id, "nombre": f"Familia {i}"}
                db.collection(FAMILIAS_COLLECTION).document(familia_id).set(familia_data)
                familias.append(familia_data)
        else:
            familias = [doc.to_dict() for doc in familias_docs]
            print(f"DEBUG: Se cargaron {len(familias)} familias.")

        # Cargar consumos
        consumos = []
        print("DEBUG: Intentando cargar consumos desde la colección 'consumos'.")
        consumos_ref = db.collection(CONSUMOS_COLLECTION).order_by("fecha", direction=firestore.Query.DESCENDING)
        consumos_docs = consumos_ref.stream()
        
        igv_porcentaje = config_data.get('igv_porcentaje', IGV_PORCENTAJE)
        
        for doc in consumos_docs:
            consumo = doc.to_dict()
            
            # Verificación de claves para evitar errores
            if 'servicio' not in consumo or 'consumo' not in consumo:
                print(f"ADVERTENCIA: Documento de consumo incompleto, se saltará: {doc.id}")
                continue # Saltar este documento y continuar con el siguiente
            
            # Calcular subtotal, IGV y costo_total
            if consumo['servicio'] == 'Luz':
                costo_unidad = config_data.get('costo_kwh', COSTO_KWH_DEFECTO)
            else:
                costo_unidad = config_data.get('costo_m3', COSTO_M3_DEFECTO)
            
            subtotal = consumo['consumo'] * costo_unidad
            igv_monto = subtotal * igv_porcentaje
            costo_total = subtotal + igv_monto
            
            consumo['costo_total'] = costo_total
            consumo['subtotal'] = subtotal
            consumo['igv_monto'] = igv_monto
            consumo['id'] = doc.id
            consumos.append(consumo)
        
        print(f"DEBUG: Se cargaron {len(consumos)} registros de consumo.")
        
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
        print(f"ERROR: Error al leer/inicializar datos en Firestore: {e}")
        return {
            "familias": [{"id": f"familia_{i}", "nombre": f"Familia {i}"} for i in range(1, NUM_FAMILIAS + 1)],
            "consumos": [],
            "config": {
                "costo_kwh": COSTO_KWH_DEFECTO,
                "costo_m3": COSTO_M3_DEFECTO,
                "igv_porcentaje": IGV_PORCENTAJE
            },
            "login": {
                "usuario": LOGIN_USER,
                "contrasena": LOGIN_PASS
            }
        }

def guardar_consumo_en_firebase(nuevo_consumo):
    """Guarda un nuevo registro de consumo en Firestore."""
    if db is None:
        print("DEBUG: No se pudo guardar. La conexión a Firebase falló.")
        return False
    
    try:
        print("DEBUG: Intentando guardar un nuevo consumo.")
        db.collection(CONSUMOS_COLLECTION).add(nuevo_consumo)
        print("DEBUG: Consumo guardado exitosamente.")
        return True
    except Exception as e:
        print(f"ERROR: Error al escribir en Firestore: {e}")
        return False

def actualizar_familias_y_costos(familias_data, costos_data):
    """Actualiza los nombres de familias y costos en Firestore."""
    if db is None:
        print("DEBUG: No se pudo actualizar. La conexión a Firebase falló.")
        return False
        
    try:
        print("DEBUG: Intentando actualizar familias y costos.")
        # Actualizar nombres de familias
        for familia in familias_data:
            db.collection(FAMILIAS_COLLECTION).document(familia['id']).update({"nombre": familia['nombre']})
        
        # Actualizar costos
        db.collection(CONFIG_DOC).document(LOGIN_DOC).update(costos_data)
        print("DEBUG: Configuración actualizada exitosamente.")
        return True
    except Exception as e:
        print(f"ERROR: Error al actualizar la configuración en Firestore: {e}")
        return False

def eliminar_consumo_en_firebase(consumo_id):
    """Elimina un documento de consumo de Firestore."""
    if db is None:
        return False
    try:
        db.collection(CONSUMOS_COLLECTION).document(consumo_id).delete()
        print(f"DEBUG: Consumo con ID {consumo_id} eliminado exitosamente.")
        return True
    except FirebaseError as e:
        print(f"ERROR: No se pudo eliminar el consumo: {e}")
        return False

def obtener_consumo_por_id(consumo_id):
    """Obtiene un único documento de consumo de Firestore por su ID."""
    if db is None:
        return None
    try:
        doc_ref = db.collection(CONSUMOS_COLLECTION).document(consumo_id)
        doc = doc_ref.get()
        if doc.exists:
            consumo = doc.to_dict()
            consumo['id'] = doc.id
            return consumo
        else:
            print(f"ERROR: No se encontró el consumo con ID {consumo_id}.")
            return None
    except FirebaseError as e:
        print(f"ERROR: No se pudo obtener el consumo por ID: {e}")
        return None

def actualizar_consumo_en_firebase(consumo_id, nuevos_datos):
    """Actualiza un documento de consumo existente en Firestore."""
    if db is None:
        return False
    try:
        doc_ref = db.collection(CONSUMOS_COLLECTION).document(consumo_id)
        doc_ref.update(nuevos_datos)
        print(f"DEBUG: Consumo con ID {consumo_id} actualizado exitosamente.")
        return True
    except FirebaseError as e:
        print(f"ERROR: No se pudo actualizar el consumo: {e}")
        return False

# =======================================================
# Rutas de la aplicación
# =======================================================

@app.before_request
def verificar_login():
    """Redirige al login si el usuario no ha iniciado sesión, excepto en la ruta de login."""
    if 'usuario' not in session and request.endpoint not in ['login', 'static']:
        return redirect(url_for('login'))

@app.route("/login", methods=["GET", "POST"])
def login():
    """Maneja el inicio de sesión."""
    if request.method == "POST":
        usuario = request.form.get("usuario")
        contrasena = request.form.get("contrasena")
        datos = cargar_datos_desde_firebase()
        
        if usuario == datos["login"]["usuario"] and contrasena == datos["login"]["contrasena"]:
            session['usuario'] = usuario
            return redirect(url_for('index'))
        else:
            return render_template_string(LOGIN_HTML, error="Usuario o contraseña incorrectos.")
    
    return render_template_string(LOGIN_HTML)

@app.route("/logout")
def logout():
    """Cierra la sesión del usuario."""
    session.pop('usuario', None)
    return redirect(url_for('login'))

@app.route("/", methods=["GET", "POST"])
def index():
    """Página principal para ingresar datos y ver el historial."""
    datos = cargar_datos_desde_firebase()
    mensaje = ""

    if request.method == "POST":
        try:
            familia_id = request.form["familia"]
            servicio = request.form["servicio"]
            fecha = request.form["fecha"]
            consumo = float(request.form["consumo"])
        except (ValueError, KeyError):
            mensaje = "Error: Por favor, introduce datos válidos."
            return render_template_string(INDEX_HTML, 
                                          familias=datos["familias"], 
                                          historial=datos["consumos"],
                                          config=datos["config"],
                                          mensaje=mensaje)

        familia_nombre = [f['nombre'] for f in datos['familias'] if f['id'] == familia_id][0]
        
        if servicio == "Luz":
            costo_unidad = datos["config"]["costo_kwh"]
            unidad = "kWh"
        else: # "Agua"
            costo_unidad = datos["config"]["costo_m3"]
            unidad = "m³"

        # Cálculo con IGV
        subtotal = consumo * costo_unidad
        igv_porcentaje = datos["config"]["igv_porcentaje"]
        igv_monto = subtotal * igv_porcentaje
        costo_total = subtotal + igv_monto
        
        nuevo_consumo = {
            "fecha": fecha,
            "familia_id": familia_id,
            "familia_nombre": familia_nombre,
            "servicio": servicio,
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

        return redirect(url_for('index'))
    
    historial = sorted(datos["consumos"], key=lambda x: x["fecha"], reverse=True)
    print(f"DEBUG: Pasando {len(historial)} registros al template.")
    
    return render_template_string(INDEX_HTML, 
                                  familias=datos["familias"], 
                                  historial=historial,
                                  config=datos["config"],
                                  mensaje=request.args.get('mensaje', ''))


@app.route("/configuracion", methods=["GET", "POST"])
def configuracion():
    """Página para editar nombres de familias y costos."""
    datos = cargar_datos_desde_firebase()
    mensaje = ""

    if request.method == "POST":
        try:
            # Recopilar datos de familias
            familias_actualizadas = []
            for familia in datos["familias"]:
                nuevo_nombre = request.form.get(f"familia_nombre_{familia['id']}")
                familias_actualizadas.append({"id": familia['id'], "nombre": nuevo_nombre})
            
            # Recopilar datos de costos
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
            mensaje = "Error: Por favor, introduce datos válidos para la configuración."
    
    # Volver a cargar los datos para reflejar los cambios
    datos = cargar_datos_desde_firebase()
    
    return render_template_string(CONFIG_HTML, 
                                  familias=datos["familias"], 
                                  config=datos["config"],
                                  mensaje=mensaje)

@app.route("/eliminar/<string:consumo_id>", methods=["POST"])
def eliminar_consumo(consumo_id):
    """Ruta para eliminar un registro de consumo."""
    if eliminar_consumo_en_firebase(consumo_id):
        return redirect(url_for('index', mensaje="Registro eliminado correctamente."))
    else:
        return redirect(url_for('index', mensaje="Error al eliminar el registro."))

@app.route("/editar/<string:consumo_id>", methods=["GET"])
def editar_consumo(consumo_id):
    """Ruta para mostrar el formulario de edición."""
    consumo = obtener_consumo_por_id(consumo_id)
    if not consumo:
        return redirect(url_for('index', mensaje="Registro no encontrado."))
    
    datos = cargar_datos_desde_firebase()
    
    return render_template_string(EDIT_HTML,
                                  consumo=consumo,
                                  familias=datos["familias"],
                                  mensaje=request.args.get('mensaje', ''))

@app.route("/actualizar/<string:consumo_id>", methods=["POST"])
def actualizar_consumo(consumo_id):
    """Ruta para procesar la actualización del formulario."""
    datos_globales = cargar_datos_desde_firebase()
    mensaje = ""
    try:
        familia_id = request.form["familia"]
        servicio = request.form["servicio"]
        fecha = request.form["fecha"]
        consumo_valor = float(request.form["consumo"])

        familia_nombre = [f['nombre'] for f in datos_globales['familias'] if f['id'] == familia_id][0]
        
        if servicio == "Luz":
            costo_unidad = datos_globales["config"]["costo_kwh"]
            unidad = "kWh"
        else: # "Agua"
            costo_unidad = datos_globales["config"]["costo_m3"]
            unidad = "m³"
        
        # Recalcular con IGV
        igv_porcentaje = datos_globales["config"]["igv_porcentaje"]
        subtotal = consumo_valor * costo_unidad
        igv_monto = subtotal * igv_porcentaje
        costo_total = subtotal + igv_monto
        
        nuevos_datos = {
            "fecha": fecha,
            "familia_id": familia_id,
            "familia_nombre": familia_nombre,
            "servicio": servicio,
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
    <style>
        body { font-family: 'Inter', sans-serif; }
    </style>
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
                <button type="submit" class="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-3 px-4 rounded-xl focus:outline-none focus:shadow-outline transition-all duration-300">
                    Entrar
                </button>
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
        .tooltip-container {
            position: relative;
            display: inline-block;
        }
        .tooltip {
            visibility: hidden;
            width: 140px;
            background-color: #333;
            color: #fff;
            text-align: center;
            border-radius: 6px;
            padding: 5px 0;
            position: absolute;
            z-index: 10;
            bottom: 125%;
            left: 50%;
            margin-left: -70px;
            opacity: 0;
            transition: opacity 0.3s;
        }
        .tooltip::after {
            content: "";
            position: absolute;
            top: 100%;
            left: 50%;
            margin-left: -5px;
            border-width: 5px;
            border-style: solid;
            border-color: #333 transparent transparent transparent;
        }
        .tooltip-container:hover .tooltip {
            visibility: visible;
            opacity: 1;
        }
    </style>
</head>
<body class="bg-gray-100 min-h-screen p-4 md:p-8">
    <div class="container mx-auto">
        <!-- Encabezado y Navegación -->
        <div class="bg-white rounded-2xl shadow-xl p-6 mb-8 flex flex-col md:flex-row items-center justify-between">
            <h1 class="text-3xl font-bold text-gray-800 mb-4 md:mb-0">Gestor de Consumos</h1>
            <nav class="flex space-x-4">
                <a href="{{ url_for('index') }}" class="py-2 px-4 text-gray-700 font-semibold rounded-lg hover:bg-blue-100 transition-colors duration-200">Inicio</a>
                <a href="{{ url_for('configuracion') }}" class="py-2 px-4 text-gray-700 font-semibold rounded-lg hover:bg-blue-100 transition-colors duration-200">Configuración</a>
                <a href="{{ url_for('logout') }}" class="py-2 px-4 text-gray-700 font-semibold rounded-lg hover:bg-red-100 transition-colors duration-200">Cerrar Sesión</a>
            </nav>
        </div>

        <!-- Mensajes de la aplicación -->
        {% if mensaje %}
        <div class="bg-green-100 border-l-4 border-green-500 text-green-700 p-4 rounded-xl mb-6 shadow-md">{{ mensaje }}</div>
        {% endif %}

        <div class="bg-white rounded-2xl shadow-xl p-6 md:p-8 mb-8">
            <h2 class="text-2xl font-bold mb-6 text-gray-800">Ingresar Consumo</h2>
            <form action="{{ url_for('index') }}" method="POST" class="space-y-6">

                <!-- Select de Familia -->
                <div>
                    <label for="familia" class="block text-sm font-medium text-gray-700 mb-2">Seleccionar Familia:</label>
                    <select id="familia" name="familia" class="mt-1 block w-full pl-3 pr-10 py-2 text-base border-gray-300 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm rounded-xl shadow-sm transition duration-200">
                        {% for familia in familias %}
                        <option value="{{ familia.id }}">{{ familia.nombre }}</option>
                        {% endfor %}
                    </select>
                </div>

                <!-- Select de Servicio -->
                <div>
                    <label for="servicio" class="block text-sm font-medium text-gray-700 mb-2">Seleccionar Servicio:</label>
                    <select id="servicio" name="servicio" class="mt-1 block w-full pl-3 pr-10 py-2 text-base border-gray-300 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm rounded-xl shadow-sm transition duration-200">
                        <option value="Luz">Luz (kWh)</option>
                        <option value="Agua">Agua (m³)</option>
                    </select>
                </div>

                <!-- Campo de Fecha -->
                <div>
                    <label for="fecha" class="block text-sm font-medium text-gray-700 mb-2">Fecha:</label>
                    <input type="date" id="fecha" name="fecha" class="mt-1 block w-full shadow-sm sm:text-sm border-gray-300 rounded-xl py-2 px-3 focus:ring-blue-500 focus:border-blue-500 transition duration-200" required>
                </div>

                <!-- Campo de Consumo -->
                <div>
                    <label for="consumo" class="block text-sm font-medium text-gray-700 mb-2">Ingresar Consumo:</label>
                    <input type="number" step="0.01" id="consumo" name="consumo" class="mt-1 block w-full shadow-sm sm:text-sm border-gray-300 rounded-xl py-2 px-3 focus:ring-blue-500 focus:border-blue-500 transition duration-200" required>
                </div>

                <div class="flex justify-end">
                    <button type="submit" class="inline-flex items-center px-6 py-3 border border-transparent text-sm font-medium rounded-xl shadow-sm text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 transition-all duration-300 transform hover:scale-105">
                        Guardar Consumo
                    </button>
                </div>
            </form>
        </div>
        
        <!-- Historial de Consumos -->
        <div class="bg-white rounded-2xl shadow-xl p-6 md:p-8">
            <h2 class="text-2xl font-bold mb-6 text-gray-800">Historial de Consumos</h2>
            <div class="overflow-x-auto">
                <table class="min-w-full divide-y divide-gray-200 rounded-xl">
                    <thead class="bg-gray-50">
                        <tr>
                            <th scope="col" class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Fecha</th>
                            <th scope="col" class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Familia</th>
                            <th scope="col" class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Servicio</th>
                            <th scope="col" class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Consumo</th>
                            <th scope="col" class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Costo Total</th>
                            <th scope="col" class="relative px-6 py-3"><span class="sr-only">Editar</span></th>
                            <th scope="col" class="relative px-6 py-3"><span class="sr-only">Eliminar</span></th>
                        </tr>
                    </thead>
                    <tbody class="bg-white divide-y divide-gray-200">
                        {% for consumo in historial %}
                        <tr class="hover:bg-gray-50 transition-colors duration-100">
                            <td class="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">{{ consumo.fecha }}</td>
                            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">{{ consumo.familia_nombre }}</td>
                            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">{{ consumo.servicio }}</td>
                            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">{{ "%.2f"|format(consumo.consumo) }} {{ consumo.unidad }}</td>
                            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                                <div class="tooltip-container">
                                    S/ {{ "%.2f"|format(consumo.costo_total) }}
                                    <span class="tooltip">
                                        Subtotal: S/ {{ "%.2f"|format(consumo.subtotal) }}<br>
                                        IGV (18%): S/ {{ "%.2f"|format(consumo.igv_monto) }}<br>
                                        Total: S/ {{ "%.2f"|format(consumo.costo_total) }}
                                    </span>
                                </div>
                            </td>
                            <!-- Botón de Editar -->
                            <td class="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                                <a href="{{ url_for('editar_consumo', consumo_id=consumo.id) }}" class="text-blue-600 hover:text-blue-900">Editar</a>
                            </td>
                            <!-- Botón de Eliminar (con formulario POST para mayor seguridad) -->
                            <td class="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                                <form action="{{ url_for('eliminar_consumo', consumo_id=consumo.id) }}" method="POST" onsubmit="return confirm('¿Estás seguro de que deseas eliminar este registro?');">
                                    <button type="submit" class="text-red-600 hover:text-red-900">Eliminar</button>
                                </form>
                            </td>
                        </tr>
                        {% else %}
                        <tr>
                            <td colspan="7" class="px-6 py-4 text-center text-sm text-gray-500">No hay datos de consumo registrados aún.</td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>
    </div>
    <!-- Script para establecer la fecha actual -->
    <script>
        window.addEventListener('DOMContentLoaded', (event) => {
            const today = new Date();
            const year = today.getFullYear();
            const month = String(today.getMonth() + 1).padStart(2, '0');
            const day = String(today.getDate()).padStart(2, '0');
            const formattedDate = `${year}-${month}-${day}`;
            const fechaInput = document.getElementById('fecha');
            if (fechaInput) {
                fechaInput.value = formattedDate;
            }
        });
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
    <style>
        body { font-family: 'Inter', sans-serif; }
    </style>
</head>
<body class="bg-gray-100 min-h-screen p-4 md:p-8">
    <div class="container mx-auto">
        <!-- Encabezado y Navegación -->
        <div class="bg-white rounded-2xl shadow-xl p-6 mb-8 flex flex-col md:flex-row items-center justify-between">
            <h1 class="text-3xl font-bold text-gray-800 mb-4 md:mb-0">Gestor de Consumos</h1>
            <nav class="flex space-x-4">
                <a href="{{ url_for('index') }}" class="py-2 px-4 text-gray-700 font-semibold rounded-lg hover:bg-blue-100 transition-colors duration-200">Inicio</a>
                <a href="{{ url_for('configuracion') }}" class="py-2 px-4 text-gray-700 font-semibold rounded-lg hover:bg-blue-100 transition-colors duration-200">Configuración</a>
                <a href="{{ url_for('logout') }}" class="py-2 px-4 text-gray-700 font-semibold rounded-lg hover:bg-red-100 transition-colors duration-200">Cerrar Sesión</a>
            </nav>
        </div>
        
        <!-- Mensajes de la aplicación -->
        {% if mensaje %}
        <div class="bg-red-100 border-l-4 border-red-500 text-red-700 p-4 rounded-xl mb-6 shadow-md">{{ mensaje }}</div>
        {% endif %}

        <div class="bg-white rounded-2xl shadow-xl p-6 md:p-8 mb-8">
            <h2 class="text-2xl font-bold mb-6 text-gray-800">Editar Consumo</h2>
            <form action="{{ url_for('actualizar_consumo', consumo_id=consumo.id) }}" method="POST" class="space-y-6">

                <!-- Select de Familia -->
                <div>
                    <label for="familia" class="block text-sm font-medium text-gray-700 mb-2">Seleccionar Familia:</label>
                    <select id="familia" name="familia" class="mt-1 block w-full pl-3 pr-10 py-2 text-base border-gray-300 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm rounded-xl shadow-sm transition duration-200">
                        {% for familia in familias %}
                        <option value="{{ familia.id }}" {% if consumo.familia_id == familia.id %}selected{% endif %}>{{ familia.nombre }}</option>
                        {% endfor %}
                    </select>
                </div>

                <!-- Select de Servicio -->
                <div>
                    <label for="servicio" class="block text-sm font-medium text-gray-700 mb-2">Seleccionar Servicio:</label>
                    <select id="servicio" name="servicio" class="mt-1 block w-full pl-3 pr-10 py-2 text-base border-gray-300 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm rounded-xl shadow-sm transition duration-200">
                        <option value="Luz" {% if consumo.servicio == 'Luz' %}selected{% endif %}>Luz (kWh)</option>
                        <option value="Agua" {% if consumo.servicio == 'Agua' %}selected{% endif %}>Agua (m³)</option>
                    </select>
                </div>

                <!-- Campo de Fecha -->
                <div>
                    <label for="fecha" class="block text-sm font-medium text-gray-700 mb-2">Fecha:</label>
                    <input type="date" id="fecha" name="fecha" value="{{ consumo.fecha }}" class="mt-1 block w-full shadow-sm sm:text-sm border-gray-300 rounded-xl py-2 px-3 focus:ring-blue-500 focus:border-blue-500 transition duration-200" required>
                </div>

                <!-- Campo de Consumo -->
                <div>
                    <label for="consumo" class="block text-sm font-medium text-gray-700 mb-2">Ingresar Consumo:</label>
                    <input type="number" step="0.01" id="consumo" name="consumo" value="{{ consumo.consumo }}" class="mt-1 block w-full shadow-sm sm:text-sm border-gray-300 rounded-xl py-2 px-3 focus:ring-blue-500 focus:border-blue-500 transition duration-200" required>
                </div>

                <div class="flex justify-end space-x-4">
                    <a href="{{ url_for('index') }}" class="inline-flex items-center px-6 py-3 border border-gray-300 text-sm font-medium rounded-xl text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 transition-all duration-300">
                        Cancelar
                    </a>
                    <button type="submit" class="inline-flex items-center px-6 py-3 border border-transparent text-sm font-medium rounded-xl shadow-sm text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 transition-all duration-300 transform hover:scale-105">
                        Guardar Cambios
                    </button>
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
    <style>
        body { font-family: 'Inter', sans-serif; }
    </style>
</head>
<body class="bg-gray-100 min-h-screen p-4 md:p-8">
    <div class="container mx-auto">
        <!-- Encabezado y Navegación -->
        <div class="bg-white rounded-2xl shadow-xl p-6 mb-8 flex flex-col md:flex-row items-center justify-between">
            <h1 class="text-3xl font-bold text-gray-800 mb-4 md:mb-0">Gestor de Consumos</h1>
            <nav class="flex space-x-4">
                <a href="{{ url_for('index') }}" class="py-2 px-4 text-gray-700 font-semibold rounded-lg hover:bg-blue-100 transition-colors duration-200">Inicio</a>
                <a href="{{ url_for('configuracion') }}" class="py-2 px-4 text-gray-700 font-semibold rounded-lg hover:bg-blue-100 transition-colors duration-200">Configuración</a>
                <a href="{{ url_for('logout') }}" class="py-2 px-4 text-gray-700 font-semibold rounded-lg hover:bg-red-100 transition-colors duration-200">Cerrar Sesión</a>
            </nav>
        </div>
        
        <!-- Mensajes de la aplicación -->
        {% if mensaje %}
        <div class="bg-green-100 border-l-4 border-green-500 text-green-700 p-4 rounded-xl mb-6 shadow-md">{{ mensaje }}</div>
        {% endif %}

        <div class="bg-white rounded-2xl shadow-xl p-6 md:p-8">
            <h2 class="text-2xl font-bold mb-6 text-gray-800">Ajustar Configuración</h2>
            <form action="{{ url_for('configuracion') }}" method="POST" class="space-y-6">
                <!-- Nombres de Familias -->
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

                <!-- Costos por Unidad -->
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
                    <button type="submit" class="inline-flex items-center px-6 py-3 border border-transparent text-sm font-medium rounded-xl shadow-sm text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 transition-all duration-300 transform hover:scale-105">
                        Guardar Configuración
                    </button>
                </div>
            </form>
        </div>
    </div>
</body>
</html>
"""


if __name__ == '__main__':
    # Esto es solo para pruebas locales, Vercel no lo usará
    print("DEBUG: Iniciando la aplicación Flask en modo de desarrollo.")
    app.run(debug=True)

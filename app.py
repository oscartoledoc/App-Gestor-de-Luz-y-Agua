import json
import os
from flask import Flask, render_template_string, request, redirect, url_for, session
from datetime import datetime

# --- Configuración de la aplicación ---
app = Flask(__name__)
app.secret_key = "tu_clave_secreta_aqui"  # Cambia esto por una clave secreta segura

# Parámetros por defecto (pueden ser cambiados en la configuración)
IGV = 0.18
COSTO_KWH_DEFECTO = 0.50
COSTO_M3_DEFECTO = 2.00
NUM_FAMILIAS = 4

# --- Funciones de manejo de datos ---

def cargar_datos():
    """Carga los datos de las familias y la configuración desde un archivo JSON."""
    if not os.path.exists('data.json') or os.path.getsize('data.json') == 0:
        # Inicializa el archivo si no existe o está vacío
        datos_iniciales = {
            "familias": [{"nombre": f"Familia {i+1}"} for i in range(NUM_FAMILIAS)],
            "consumos": [],
            "config": {
                "costo_kwh": COSTO_KWH_DEFECTO,
                "costo_m3": COSTO_M3_DEFECTO,
                "igv": IGV
            },
            "login": {
                "usuario": "admin",
                "contrasena": "admin"
            }
        }
        with open('data.json', 'w') as f:
            json.dump(datos_iniciales, f, indent=4)
        return datos_iniciales
    
    with open('data.json', 'r') as f:
        return json.load(f)

def guardar_datos(datos):
    """Guarda los datos en el archivo JSON."""
    with open('data.json', 'w') as f:
        json.dump(datos, f, indent=4)

def parse_date(date_str):
    """
    Función auxiliar para parsear fechas, manejando formatos antiguos y nuevos.
    Intenta el formato con hora primero, y si falla, el formato solo con fecha.
    """
    try:
        return datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return datetime.strptime(date_str, "%Y-%m-%d")

# --- Rutas de la aplicación ---

@app.before_request
def verificar_login():
    """Redirige al login si el usuario no ha iniciado sesión, excepto en la ruta de login."""
    if 'usuario' not in session and request.endpoint != 'login':
        return redirect(url_for('login'))

@app.route("/login", methods=["GET", "POST"])
def login():
    """Maneja el inicio de sesión."""
    if request.method == "POST":
        usuario = request.form["usuario"]
        contrasena = request.form["contrasena"]
        datos = cargar_datos()
        
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
    datos = cargar_datos()
    mensaje = ""

    if request.method == "POST":
        familia_id = int(request.form["familia"])
        servicio = request.form["servicio"]
        lectura_actual = float(request.form["lectura"])
        
        # Obtenemos la acción del formulario (añadir o editar)
        accion = request.form.get("accion", "añadir")
        consumo_id = int(request.form.get("consumo_id", -1))

        familia_nombre = datos["familias"][familia_id]["nombre"]
        
        # Obtener la lectura del mes anterior para el cálculo diferencial
        lectura_anterior = 0
        consumos_familia = [c for c in datos["consumos"] if c["familia_nombre"] == familia_nombre]
        
        # Eliminar el consumo actual si se está editando para no considerarlo en el cálculo
        if accion == "editar" and consumo_id != -1:
            consumos_familia = [c for c in consumos_familia if c != datos["consumos"][consumo_id]]

        if consumos_familia:
            consumos_familia.sort(key=lambda x: parse_date(x["fecha"]), reverse=True)
            for consumo_anterior in consumos_familia:
                if consumo_anterior["servicio"] == servicio:
                    # Usar .get() para evitar el error si el campo no existe
                    lectura_anterior = consumo_anterior.get("lectura_actual", 0)
                    break
        
        diferencial_consumo = lectura_actual - lectura_anterior
        
        if servicio == "Luz":
            costo_unidad = datos["config"]["costo_kwh"]
            unidad = "kWh"
        else: # "Agua"
            costo_unidad = datos["config"]["costo_m3"]
            unidad = "m³"

        subtotal = diferencial_consumo * costo_unidad
        igv_monto = subtotal * datos["config"]["igv"]
        costo_total = subtotal + igv_monto
        
        # Calcular la diferencia con el mes anterior
        diferencia_consumo = 0
        diferencia_costo = 0
        
        if consumos_familia:
            for consumo_anterior in consumos_familia:
                if consumo_anterior["servicio"] == servicio:
                    # Usar .get() para evitar el error si el campo no existe
                    diferencia_consumo = diferencial_consumo - consumo_anterior.get("diferencial_consumo", 0)
                    diferencia_costo = costo_total - consumo_anterior.get("costo_total", 0)
                    break
        
        nuevo_consumo = {
            "fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "familia_id": familia_id,
            "familia_nombre": familia_nombre,
            "servicio": servicio,
            "lectura_anterior": lectura_anterior,
            "lectura_actual": lectura_actual,
            "diferencial_consumo": diferencial_consumo,
            "unidad": unidad,
            "costo_total": costo_total,
            "diferencia_consumo": diferencia_consumo,
            "diferencia_costo": diferencia_costo
        }
        
        if accion == "editar" and consumo_id != -1:
            datos["consumos"][consumo_id] = nuevo_consumo
            mensaje = "Registro actualizado correctamente."
        else:
            datos["consumos"].append(nuevo_consumo)
            mensaje = "Datos guardados correctamente."

        guardar_datos(datos)
        
    # Preparar el historial para la tabla
    historial = sorted(datos["consumos"], key=lambda x: parse_date(x["fecha"]), reverse=True)
    
    # Renderizar la página principal
    return render_template_string(INDEX_HTML, 
                                  familias=datos["familias"], 
                                  historial=historial,
                                  mensaje=mensaje)

@app.route("/eliminar_consumo/<int:consumo_id>", methods=["POST"])
def eliminar_consumo(consumo_id):
    """Ruta para eliminar un registro de consumo."""
    datos = cargar_datos()
    if 0 <= consumo_id < len(datos["consumos"]):
        del datos["consumos"][consumo_id]
        guardar_datos(datos)
        return redirect(url_for('index'))
    return "Error: Registro no encontrado.", 404

@app.route("/configuracion", methods=["GET", "POST"])
def configuracion():
    """Página para editar nombres de familias y costos."""
    datos = cargar_datos()
    mensaje = ""

    if request.method == "POST":
        # Actualizar nombres de familias
        for i in range(len(datos["familias"])):
            nuevo_nombre = request.form.get(f"familia_nombre_{i}")
            if nuevo_nombre:
                datos["familias"][i]["nombre"] = nuevo_nombre
        
        # Actualizar costos
        datos["config"]["costo_kwh"] = float(request.form["costo_kwh"])
        datos["config"]["costo_m3"] = float(request.form["costo_m3"])
        
        guardar_datos(datos)
        mensaje = "Configuración guardada correctamente."

    return render_template_string(CONFIG_HTML, 
                                  familias=datos["familias"], 
                                  config=datos["config"],
                                  mensaje=mensaje)

# --- HTML de la aplicación (plantillas) ---

LOGIN_HTML = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Login - App de Consumo</title>
    <link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
    <style>
        body { font-family: 'Inter', sans-serif; background-color: #f3f4f6; }
    </style>
</head>
<body class="bg-gray-100 flex items-center justify-center h-screen">
    <div class="bg-white p-8 rounded-2xl shadow-xl w-full max-w-md">
        <h2 class="text-3xl font-bold text-center mb-6 text-gray-800">Iniciar Sesión</h2>
        {% if error %}
        <p class="bg-red-100 border-l-4 border-red-500 text-red-700 p-4 mb-4 rounded">{{ error }}</p>
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
    <link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0-beta3/css/all.min.css" rel="stylesheet">
    <style>
        body { font-family: 'Inter', sans-serif; background-color: #f3f4f6; }
        .tab-button.active {
            border-bottom: 2px solid #3b82f6;
            color: #3b82f6;
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
            <h2 id="form-title" class="text-2xl font-bold mb-6 text-gray-800">Ingresar Consumo Mensual</h2>
            
            <form id="consumo-form" action="{{ url_for('index') }}" method="POST" class="space-y-6">
                <input type="hidden" name="accion" id="accion" value="añadir">
                <input type="hidden" name="consumo_id" id="consumo_id" value="-1">

                <!-- Select de Familia -->
                <div>
                    <label for="familia" class="block text-sm font-medium text-gray-700 mb-2">Seleccionar Familia:</label>
                    <select id="familia" name="familia" class="mt-1 block w-full pl-3 pr-10 py-2 text-base border-gray-300 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm rounded-xl shadow-sm transition duration-200">
                        {% for familia in familias %}
                        <option value="{{ loop.index0 }}">{{ familia.nombre }}</option>
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

                <!-- Campo de Lectura -->
                <div>
                    <label for="lectura" class="block text-sm font-medium text-gray-700 mb-2">Ingresar Lectura del Medidor:</label>
                    <input type="number" step="0.01" id="lectura" name="lectura" class="mt-1 block w-full shadow-sm sm:text-sm border-gray-300 rounded-xl py-2 px-3 focus:ring-blue-500 focus:border-blue-500 transition duration-200" required>
                </div>

                <div class="flex justify-end space-x-4">
                    <button type="submit" class="inline-flex items-center px-6 py-3 border border-transparent text-sm font-medium rounded-xl shadow-sm text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 transition-all duration-300 transform hover:scale-105">
                        <span id="submit-text">Guardar Consumo</span>
                    </button>
                    <button type="button" id="cancelar-edicion" class="hidden inline-flex items-center px-6 py-3 border border-gray-300 text-sm font-medium rounded-xl text-gray-700 bg-white hover:bg-gray-50 focus:outline-none transition-all duration-300">
                        Cancelar
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
                            <th scope="col" class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Lectura Anterior</th>
                            <th scope="col" class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Lectura Actual</th>
                            <th scope="col" class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Consumo (Diferencial)</th>
                            <th scope="col" class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Costo Total</th>
                            <th scope="col" class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Cambio Consumo</th>
                            <th scope="col" class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Cambio Costo</th>
                            <th scope="col" class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Acciones</th>
                        </tr>
                    </thead>
                    <tbody class="bg-white divide-y divide-gray-200">
                        {% for consumo in historial %}
                        <tr class="hover:bg-gray-50 transition-colors duration-100">
                            <td class="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">{{ consumo.fecha }}</td>
                            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">{{ consumo.familia_nombre }}</td>
                            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">{{ consumo.servicio }}</td>
                            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                                {{ "%.2f"|format(consumo.get("lectura_anterior", 0)) }}
                            </td>
                            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                                {{ "%.2f"|format(consumo.get("lectura_actual", 0)) }}
                            </td>
                            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                                {{ "%.2f"|format(consumo.diferencial_consumo) }} {{ consumo.unidad }}
                            </td>
                            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                                S/ {{ "%.2f"|format(consumo.costo_total) }}
                            </td>
                            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                                {% if consumo.get("diferencia_consumo", 0) > 0 %}
                                    <span class="text-red-500 font-bold">
                                        <i class="fas fa-arrow-up"></i> +{{ "%.2f"|format(consumo.diferencia_consumo) }}
                                    </span>
                                {% elif consumo.get("diferencia_consumo", 0) < 0 %}
                                    <span class="text-green-500 font-bold">
                                        <i class="fas fa-arrow-down"></i> {{ "%.2f"|format(consumo.diferencia_consumo) }}
                                    </span>
                                {% else %}
                                    <span>-</span>
                                {% endif %}
                            </td>
                            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                                {% if consumo.get("diferencia_costo", 0) > 0 %}
                                    <span class="text-red-500 font-bold">
                                        <i class="fas fa-arrow-up"></i> +S/ {{ "%.2f"|format(consumo.diferencia_costo) }}
                                    </span>
                                {% elif consumo.get("diferencia_costo", 0) < 0 %}
                                    <span class="text-green-500 font-bold">
                                        <i class="fas fa-arrow-down"></i> S/ {{ "%.2f"|format(consumo.diferencia_costo) }}
                                    </span>
                                {% else %}
                                    <span>-</span>
                                {% endif %}
                            </td>
                            <td class="px-6 py-4 whitespace-nowrap text-sm font-medium">
                                <button onclick="editarConsumo({{ loop.index0 }})" class="text-blue-600 hover:text-blue-900 mr-4">
                                    <i class="fas fa-edit"></i> Editar
                                </button>
                                <form action="{{ url_for('eliminar_consumo', consumo_id=loop.index0) }}" method="POST" class="inline" onsubmit="return confirm('¿Estás seguro de que quieres eliminar este registro?');">
                                    <button type="submit" class="text-red-600 hover:text-red-900">
                                        <i class="fas fa-trash-alt"></i> Eliminar
                                    </button>
                                </form>
                            </td>
                        </tr>
                        {% else %}
                        <tr>
                            <td colspan="10" class="px-6 py-4 text-center text-sm text-gray-500">No hay datos de consumo registrados aún.</td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>
    </div>

    <script>
        function editarConsumo(id) {
            const historial = {{ historial | tojson }};
            const consumo = historial[id];
            
            // Llenar el formulario con los datos del registro, usando 0 como valor predeterminado si el campo no existe
            document.getElementById('familia').value = consumo.familia_id;
            document.getElementById('servicio').value = consumo.servicio;
            document.getElementById('lectura').value = consumo.lectura_actual;
            
            // Cambiar el formulario a modo de edición
            document.getElementById('form-title').innerText = 'Editar Consumo';
            document.getElementById('accion').value = 'editar';
            document.getElementById('consumo_id').value = id;
            document.getElementById('submit-text').innerText = 'Actualizar Consumo';
            document.getElementById('cancelar-edicion').classList.remove('hidden');

            // Mover el scroll al formulario
            window.scrollTo({ top: 0, behavior: 'smooth' });
        }

        document.getElementById('cancelar-edicion').addEventListener('click', () => {
            // Restaurar el formulario a modo de añadir
            document.getElementById('consumo-form').reset();
            document.getElementById('form-title').innerText = 'Ingresar Consumo Mensual';
            document.getElementById('accion').value = 'añadir';
            document.getElementById('consumo_id').value = '-1';
            document.getElementById('submit-text').innerText = 'Guardar Consumo';
            document.getElementById('cancelar-edicion').classList.add('hidden');
        });
    </script>
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
    <link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
    <style>
        body { font-family: 'Inter', sans-serif; background-color: #f3f4f6; }
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
                        <label for="familia_nombre_{{ loop.index0 }}" class="block text-sm font-medium text-gray-700 mb-1">Familia {{ loop.index0 + 1 }}:</label>
                        <input type="text" id="familia_nombre_{{ loop.index0 }}" name="familia_nombre_{{ loop.index0 }}" value="{{ familia.nombre }}" class="mt-1 block w-full shadow-sm sm:text-sm border-gray-300 rounded-xl py-2 px-3 focus:ring-blue-500 focus:border-blue-500 transition duration-200">
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
                    <div class="text-sm text-gray-500">
                        Nota: El IGV es del 18% y se aplica automáticamente en los cálculos.
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

if __name__ == "__main__":
    app.run(debug=True)

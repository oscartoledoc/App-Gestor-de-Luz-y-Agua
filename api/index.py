# =======================================================
# Archivo 1: api/index.py
# Este es el código principal de tu aplicación Flask,
# modificado para usar Firestore.
# =======================================================

from flask import Flask, render_template_string, request, redirect, url_for, session
from datetime import datetime
import json
import os
import firebase_admin
from firebase_admin import credentials, firestore

# Asegúrate de que el objeto de la app se llame 'app'
app = Flask(__name__)
app.secret_key = os.urandom(24) # Clave secreta para las sesiones

# =======================================================
# Configuración y conexión a Firestore
# =======================================================
# Para Vercel, se debe establecer la variable de entorno
# FIREBASE_CREDENTIALS con el contenido del JSON de la
# clave de servicio de Firebase.
# Para pruebas locales, puedes tener el archivo en tu
# proyecto y referenciarlo aquí.
try:
    if os.environ.get('FIREBASE_CREDENTIALS'):
        # Leer el contenido de la variable de entorno en Vercel
        cred_json = json.loads(os.environ.get('FIREBASE_CREDENTIALS'))
        cred = credentials.Certificate(cred_json)
    else:
        # Esto es solo para pruebas locales si tienes un archivo de credenciales
        # Nota: Vercel ignora esta parte.
        cred = credentials.Certificate("path/to/your/service-account-key.json")
    
    # Inicializar la app de Firebase si no está inicializada
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
    db = firestore.client()

except Exception as e:
    # Si hay un error al conectar a Firebase, lo imprimirá aquí.
    print(f"Error al inicializar Firebase: {e}")
    db = None

# =======================================================
# Lógica de carga y guardado de datos con Firestore
# =======================================================
def get_consumos():
    """Lee todos los documentos de la colección 'consumos'."""
    if db is None:
        return {}
    
    try:
        # Suponemos una colección 'consumos' donde cada documento es un registro
        docs = db.collection('consumos').stream()
        consumos_data = {doc.id: doc.to_dict() for doc in docs}
        return consumos_data
    except Exception as e:
        print(f"Error al leer de Firestore: {e}")
        return {}

def save_consumo(new_consumo):
    """Guarda un nuevo registro de consumo en Firestore."""
    if db is None:
        print("Error: db object is None. Firebase not initialized.")
        return False
    
    try:
        # Añadir un nuevo documento a la colección 'consumos'
        db.collection('consumos').add(new_consumo)
        return True
    except Exception as e:
        # Esta es la nueva línea que nos dará el error exacto
        print(f"Error al escribir en Firestore: {e}")
        return False

# =======================================================
# Rutas de la aplicación (adaptadas a Firestore)
# =======================================================

@app.route('/')
def home():
    if 'usuario' not in session:
        return redirect(url_for('login'))
    
    # Obtener los datos de consumo de Firestore
    consumos = get_consumos()
    
    # Calcular el total de consumo y el costo
    total_consumo = sum(float(c.get('consumo', 0)) for c in consumos.values())
    total_costo = sum(float(c.get('costo', 0)) for c in consumos.values())
    
    # Renderizar el HTML de la página principal
    html_content = """
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Control de Consumo</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700&display=swap" rel="stylesheet">
        <style>
            body { font-family: 'Inter', sans-serif; }
        </style>
    </head>
    <body class="bg-gray-100 p-8">
        <div class="max-w-4xl mx-auto bg-white p-8 rounded-xl shadow-lg">
            <h1 class="text-3xl font-bold mb-6 text-center text-gray-800">Control de Consumo Eléctrico</h1>
            <div class="mb-8 p-6 bg-blue-50 rounded-xl shadow-md flex justify-around items-center">
                <div class="text-center">
                    <p class="text-gray-600 font-medium">Consumo Total (kWh)</p>
                    <p class="text-4xl font-bold text-blue-600">{{ "%.2f"|format(total_consumo) }}</p>
                </div>
                <div class="text-center">
                    <p class="text-gray-600 font-medium">Costo Total ($)</p>
                    <p class="text-4xl font-bold text-green-600">{{ "%.2f"|format(total_costo) }}</p>
                </div>
            </div>

            <form action="/agregar_consumo" method="post" class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-8">
                <div>
                    <label for="consumo" class="block text-gray-700 font-medium mb-1">Consumo (kWh)</label>
                    <input type="number" id="consumo" name="consumo" step="0.01" class="w-full p-3 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 transition duration-200" required>
                </div>
                <div>
                    <label for="costo" class="block text-gray-700 font-medium mb-1">Costo ($)</label>
                    <input type="number" id="costo" name="costo" step="0.01" class="w-full p-3 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 transition duration-200" required>
                </div>
                <div class="md:col-span-2">
                    <label for="fecha" class="block text-gray-700 font-medium mb-1">Fecha</label>
                    <input type="date" id="fecha" name="fecha" class="w-full p-3 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 transition duration-200" required>
                </div>
                <div class="md:col-span-2">
                    <button type="submit" class="w-full bg-blue-600 text-white font-bold p-3 rounded-md hover:bg-blue-700 transition duration-200">Agregar Consumo</button>
                </div>
            </form>
            
            <h2 class="text-2xl font-bold mb-4 text-gray-800">Registros</h2>
            <div class="bg-gray-50 p-4 rounded-xl shadow-inner overflow-x-auto">
                <table class="min-w-full divide-y divide-gray-200">
                    <thead class="bg-gray-100">
                        <tr>
                            <th class="px-6 py-3 text-left text-xs font-bold text-gray-500 uppercase tracking-wider">Fecha</th>
                            <th class="px-6 py-3 text-left text-xs font-bold text-gray-500 uppercase tracking-wider">Consumo (kWh)</th>
                            <th class="px-6 py-3 text-left text-xs font-bold text-gray-500 uppercase tracking-wider">Costo ($)</th>
                        </tr>
                    </thead>
                    <tbody class="bg-white divide-y divide-gray-200">
                        <!-- Loop para mostrar los consumos -->
                        {% for consumo in consumos.values() %}
                        <tr>
                            <td class="px-6 py-4 whitespace-nowrap">
                                <div class="text-sm text-gray-900">{{ consumo['fecha'] }}</div>
                            </td>
                            <td class="px-6 py-4 whitespace-nowrap">
                                <div class="text-sm text-gray-900">{{ "%.2f"|format(consumo['consumo']) }}</div>
                            </td>
                            <td class="px-6 py-4 whitespace-nowrap">
                                <div class="text-sm text-gray-900">{{ "%.2f"|format(consumo['costo']) }}</div>
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>

            <div class="flex justify-end mt-8">
                <a href="/logout" class="bg-red-500 text-white font-bold py-2 px-4 rounded-md hover:bg-red-600 transition duration-200">Cerrar Sesión</a>
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
                document.getElementById('fecha').value = formattedDate;
            });
        </script>
    </body>
    </html>
    """
    return render_template_string(html_content, total_consumo=total_consumo, total_costo=total_costo, consumos=consumos)

@app.route('/agregar_consumo', methods=['POST'])
def agregar_consumo():
    if 'usuario' not in session:
        return redirect(url_for('login'))
        
    fecha = request.form['fecha']
    consumo = float(request.form['consumo'])
    costo = float(request.form['costo'])
    
    new_consumo = {
        'fecha': fecha,
        'consumo': consumo,
        'costo': costo
    }
    
    if save_consumo(new_consumo):
        return redirect(url_for('home'))
    else:
        # Modificado para no mostrar un error genérico
        return "Error al guardar el consumo. Revisa los logs de Vercel para más detalles.", 500

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form['password'] == '123':
            session['usuario'] = 'admin'
            return redirect(url_for('home'))
        else:
            return "Contraseña incorrecta", 401
    html_content = """
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Login</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700&display=swap" rel="stylesheet">
        <style>
            body { font-family: 'Inter', sans-serif; }
        </style>
    </head>
    <body class="bg-gray-100 flex items-center justify-center min-h-screen">
        <div class="w-full max-w-md p-8 bg-white rounded-xl shadow-lg">
            <h1 class="text-3xl font-bold mb-6 text-center text-gray-800">Login</h1>
            <form action="/login" method="post" class="space-y-4">
                <div>
                    <label for="password" class="block text-gray-700 font-medium mb-1">Contraseña</label>
                    <input type="password" id="password" name="password" class="w-full p-3 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 transition duration-200" required>
                </div>
                <button type="submit" class="w-full bg-blue-600 text-white font-bold p-3 rounded-md hover:bg-blue-700 transition duration-200">Ingresar</button>
            </form>
        </div>
    </body>
    </html>
    """
    return render_template_string(html_content)

@app.route('/logout')
def logout():
    session.pop('usuario', None)
    return redirect(url_for('login'))

if __name__ == '__main__':
    # Esto es solo para pruebas locales, Vercel no lo usará
    app.run(debug=True)

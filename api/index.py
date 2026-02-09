# =======================================================
# Archivo 1: api/index.py
# Código principal de la aplicación Flask (Versión Final: Filtros + Popup + Costos Fijos + Configuración Estática)
# =======================================================

from flask import Flask, render_template_string, request, redirect, url_for, session
from datetime import datetime, timedelta
import json
import os
import firebase_admin
from firebase_admin import credentials, firestore
from firebase_admin.exceptions import FirebaseError

app = Flask(__name__)
app.secret_key = os.urandom(24)
app.permanent_session_lifetime = timedelta(minutes=30)

# =======================================================
# Configuración Firebase
# =======================================================
try:
    if os.environ.get('FIREBASE_CREDENTIALS'):
        cred_json = json.loads(os.environ.get('FIREBASE_CREDENTIALS'))
        cred = credentials.Certificate(cred_json)
    else:
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
IGV_PORCENTAJE = 0.18
LOGIN_USER = "admin"
LOGIN_PASS = "123"

FAMILIAS_COLLECTION = "familias"
CONSUMOS_COLLECTION = "consumos"
CONFIG_DOC = "config"
LOGIN_DOC = "login"

# =======================================================
# Lógica de Datos
# =======================================================
def cargar_datos_desde_firebase():
    if db is None: return {"familias": [], "consumos": [], "config": {}, "login": {}}
    try:
        config_ref = db.collection(CONFIG_DOC).document(LOGIN_DOC)
        config_data = config_ref.get().to_dict() or {}
        
        if not config_data:
            config_data = {"costo_kwh": COSTO_KWH_DEFECTO, "costo_m3": COSTO_M3_DEFECTO, "igv_porcentaje": IGV_PORCENTAJE, "usuario": LOGIN_USER, "contrasena": LOGIN_PASS}
            config_ref.set(config_data)

        familias = []
        familias_docs = list(db.collection(FAMILIAS_COLLECTION).order_by("id").stream())
        if not familias_docs:
            for i in range(1, NUM_FAMILIAS + 1):
                fid = f"familia_{i}"
                fdata = {"id": fid, "nombre": f"Familia {i}"}
                db.collection(FAMILIAS_COLLECTION).document(fid).set(fdata)
                familias.append(fdata)
        else:
            familias = [d.to_dict() for d in familias_docs]

        consumos = []
        for doc in db.collection(CONSUMOS_COLLECTION).stream():
            d = doc.to_dict()
            if 'servicio' in d:
                d['id'] = doc.id
                consumos.append(d)
        
        return {
            "familias": familias, 
            "consumos": consumos, 
            "config": config_data, 
            "login": config_data
        }
    except Exception:
        return {"familias": [], "consumos": [], "config": {}, "login": {}}

def calcular_lectura_anterior(familia_id, servicio, fecha_corte, excluir_id=None):
    lectura_anterior = 0
    if db is None: return 0
    try:
        consumos_ref = db.collection(CONSUMOS_COLLECTION).where("familia_id", "==", familia_id).where("servicio", "==", servicio)
        candidatos = []
        for doc in consumos_ref.stream():
            if excluir_id and doc.id == excluir_id: continue
            data = doc.to_dict()
            if data.get('fecha', '9999-99-99') < fecha_corte:
                candidatos.append(data)
        if candidatos:
            candidatos.sort(key=lambda x: x.get('fecha', '0'), reverse=True)
            lectura_anterior = candidatos[0].get('lectura', 0)
    except Exception: pass
    return lectura_anterior

# =======================================================
# Lógica de Costos Fijos y Porcentajes
# =======================================================
def calcular_extras_y_total(familia_id, servicio, subtotal_con_igv, form_data):
    """Calcula los montos adicionales según la familia y el servicio."""
    porcentaje = 0.0
    if familia_id == 'familia_1':
        porcentaje = 0.13 # 13%
    elif familia_id == 'familia_2' or familia_id == 'familia_3':
        porcentaje = 0.435 # 43.5%
    
    extras = {
        "luz_cargo_fijo": 0.0, "luz_mantenimiento": 0.0, "luz_alumbrado": 0.0, "luz_interes": 0.0,
        "agua_alcantarillado": 0.0, "agua_cargo_fijo": 0.0
    }
    
    if servicio == "Luz":
        raw_cargo = float(form_data.get('luz_cargo_fijo', 0) or 0)
        raw_mant = float(form_data.get('luz_mantenimiento', 0) or 0)
        raw_alum = float(form_data.get('luz_alumbrado', 0) or 0)
        raw_int = float(form_data.get('luz_interes', 0) or 0)

        extras['luz_cargo_fijo'] = raw_cargo * porcentaje
        extras['luz_mantenimiento'] = raw_mant * porcentaje
        extras['luz_alumbrado'] = raw_alum * porcentaje
        extras['luz_interes'] = raw_int * porcentaje

    elif servicio == "Agua":
        raw_alcan = float(form_data.get('agua_alcantarillado', 0) or 0)
        raw_cargo = float(form_data.get('agua_cargo_fijo', 0) or 0)

        extras['agua_alcantarillado'] = raw_alcan * porcentaje
        extras['agua_cargo_fijo'] = raw_cargo * porcentaje

    total_extras = sum(extras.values())
    costo_final = subtotal_con_igv + total_extras
    
    return extras, costo_final

# =======================================================
# Rutas
# =======================================================
@app.before_request
def verificar_login():
    if 'usuario' not in session and request.endpoint not in ['login', 'static']:
        return redirect(url_for('login'))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        datos = cargar_datos_desde_firebase()
        if request.form.get("usuario") == datos["login"]["usuario"] and request.form.get("contrasena") == datos["login"]["contrasena"]:
            session.permanent = True
            session['usuario'] = request.form.get("usuario")
            return redirect(url_for('index'))
        return render_template_string(LOGIN_HTML, error="Credenciales incorrectas")
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

            familia_nombre = [f['nombre'] for f in datos['familias'] if f['id'] == familia_id][0]
            lectura_anterior = calcular_lectura_anterior(familia_id, servicio, fecha)
            consumo = max(0, lectura_actual - lectura_anterior)
            
            if servicio == "Luz":
                costo_unidad = datos["config"]["costo_kwh"]
                unidad = "kWh"
            else:
                costo_unidad = datos["config"]["costo_m3"]
                unidad = "m³"

            subtotal = consumo * costo_unidad
            igv_monto = subtotal * datos["config"]["igv_porcentaje"]
            base_con_igv = subtotal + igv_monto

            extras_calculados, costo_total = calcular_extras_y_total(familia_id, servicio, base_con_igv, request.form)
            
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
                "costo_total": costo_total,
                "timestamp": firestore.SERVER_TIMESTAMP,
                **extras_calculados
            }
            
            if db: db.collection(CONSUMOS_COLLECTION).add(nuevo_consumo)
            mensaje = "Datos guardados correctamente."
        except Exception as e:
            mensaje = f"Error: {e}"
            print(e)
        
        return redirect(url_for('index', mensaje=mensaje))
    
    historial = sorted(datos["consumos"], key=lambda x: x.get("timestamp") or x.get("fecha", '0'), reverse=True)
    return render_template_string(INDEX_HTML, familias=datos["familias"], historial=historial, config=datos["config"], mensaje=request.args.get('mensaje', ''))

@app.route("/configuracion", methods=["GET", "POST"])
def configuracion():
    mensaje = ""
    if request.method == "POST" and db:
        try:
            datos = cargar_datos_desde_firebase()
            for fam in datos["familias"]:
                nuevo = request.form.get(f"familia_nombre_{fam['id']}")
                db.collection(FAMILIAS_COLLECTION).document(fam['id']).update({"nombre": nuevo})
            
            db.collection(CONFIG_DOC).document(LOGIN_DOC).update({
                "costo_kwh": float(request.form["costo_kwh"]),
                "costo_m3": float(request.form["costo_m3"]),
                "igv_porcentaje": float(request.form["igv_porcentaje"])
            })
            mensaje = "Configuración guardada."
        except Exception: mensaje = "Error al guardar."
    
    datos = cargar_datos_desde_firebase()
    return render_template_string(CONFIG_HTML, familias=datos["familias"], config=datos["config"], mensaje=mensaje)

@app.route("/eliminar/<string:cid>", methods=["POST"])
def eliminar_consumo(cid):
    if db: db.collection(CONSUMOS_COLLECTION).document(cid).delete()
    return redirect(url_for('index', mensaje="Eliminado."))

@app.route("/editar/<string:cid>", methods=["GET"])
def editar_consumo(cid):
    if not db: return redirect(url_for('index'))
    doc = db.collection(CONSUMOS_COLLECTION).document(cid).get()
    if not doc.exists: return redirect(url_for('index'))
    datos = cargar_datos_desde_firebase()
    consumo = doc.to_dict()
    consumo['id'] = cid
    return render_template_string(EDIT_HTML, consumo=consumo, familias=datos["familias"])

@app.route("/actualizar/<string:cid>", methods=["POST"])
def actualizar_consumo(cid):
    if not db: return redirect(url_for('index'))
    try:
        datos = cargar_datos_desde_firebase()
        familia_id = request.form["familia"]
        servicio = request.form["servicio"]
        fecha = request.form["fecha"]
        lectura_actual = float(request.form["lectura"])
        
        familia_nombre = [f['nombre'] for f in datos['familias'] if f['id'] == familia_id][0]
        lectura_anterior = calcular_lectura_anterior(familia_id, servicio, fecha, excluir_id=cid)
        consumo = max(0, lectura_actual - lectura_anterior)
        
        if servicio == "Luz":
            costo_unidad = datos["config"]["costo_kwh"]
            unidad = "kWh"
        else:
            costo_unidad = datos["config"]["costo_m3"]
            unidad = "m³"

        subtotal = consumo * costo_unidad
        igv_monto = subtotal * datos["config"]["igv_porcentaje"]
        base_con_igv = subtotal + igv_monto

        extras_calculados, costo_total = calcular_extras_y_total(familia_id, servicio, base_con_igv, request.form)

        nuevos_datos = {
            "fecha": fecha, "familia_id": familia_id, "familia_nombre": familia_nombre,
            "servicio": servicio, "lectura": lectura_actual, "lectura_anterior": lectura_anterior,
            "consumo": consumo, "unidad": unidad, "subtotal": subtotal, "igv_monto": igv_monto,
            "costo_total": costo_total, "timestamp": firestore.SERVER_TIMESTAMP,
            **extras_calculados
        }
        db.collection(CONSUMOS_COLLECTION).document(cid).update(nuevos_datos)
        mensaje = "Actualizado."
    except Exception: mensaje = "Error al actualizar."
    return redirect(url_for('index', mensaje=mensaje))

# =======================================================
# HTML Templates (Frontend)
# =======================================================

LOGIN_HTML = """
<!DOCTYPE html>
<html lang="es"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Login</title><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-gray-100 flex items-center justify-center h-screen"><div class="bg-white p-8 rounded-2xl shadow-xl w-full max-w-md"><h2 class="text-3xl font-bold text-center mb-6">Iniciar Sesión</h2>{% if error %}<p class="bg-red-100 text-red-700 p-3 mb-4 rounded">{{ error }}</p>{% endif %}<form method="POST"><div class="mb-4"><label class="block text-gray-700 text-sm font-bold mb-2">Usuario</label><input type="text" name="usuario" class="shadow appearance-none border rounded w-full py-2 px-3 text-gray-700 leading-tight focus:outline-none focus:shadow-outline" required></div><div class="mb-6"><label class="block text-gray-700 text-sm font-bold mb-2">Contraseña</label><input type="password" name="contrasena" class="shadow appearance-none border rounded w-full py-2 px-3 text-gray-700 mb-3 leading-tight focus:outline-none focus:shadow-outline" required></div><button type="submit" class="bg-blue-500 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded w-full">Entrar</button></form></div></body></html>
"""

INDEX_HTML = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Gestor de Consumos</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>.tooltip-container {position: relative;display: inline-block;}.tooltip {visibility: hidden;width: 140px;background-color: #333;color: #fff;text-align: center;border-radius: 6px;padding: 5px 0;position: absolute;z-index: 10;bottom: 125%;left: 50%;margin-left: -70px;opacity: 0;transition: opacity 0.3s;}.tooltip-container:hover .tooltip {visibility: visible;opacity: 1;}</style>
</head>
<body class="bg-gray-100 min-h-screen p-4 md:p-8">
    <div class="container mx-auto">
        <div class="bg-white rounded-2xl shadow-xl p-6 mb-8 flex flex-col md:flex-row items-center justify-between">
            <h1 class="text-3xl font-bold text-gray-800">Gestor de Consumos</h1>
            <nav class="flex gap-4"><a href="{{ url_for('index') }}" class="text-blue-600 font-bold">Inicio</a><a href="{{ url_for('configuracion') }}" class="text-gray-600 hover:text-blue-600">Configuración</a><a href="{{ url_for('logout') }}" class="text-red-600 hover:text-red-800">Salir</a></nav>
        </div>
        {% if mensaje %}<div class="bg-green-100 text-green-700 p-4 rounded-xl mb-6">{{ mensaje }}</div>{% endif %}

        <div class="bg-white rounded-2xl shadow-xl p-6 mb-8">
            <h2 class="text-2xl font-bold mb-4">Ingresar Lectura</h2>
            <form action="{{ url_for('index') }}" method="POST" class="space-y-4">
                <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div><label class="block text-sm font-medium mb-1">Familia</label><select name="familia" class="w-full border rounded-lg p-2" required><option value="" disabled selected>-- Selecciona --</option>{% for f in familias %}<option value="{{ f.id }}">{{ f.nombre }}</option>{% endfor %}</select></div>
                    <div><label class="block text-sm font-medium mb-1">Servicio</label><select id="selectServicio" name="servicio" class="w-full border rounded-lg p-2" onchange="toggleCampos()" required><option value="Luz">Luz</option><option value="Agua">Agua</option></select></div>
                    <div><label class="block text-sm font-medium mb-1">Fecha</label><input type="date" id="fecha" name="fecha" class="w-full border rounded-lg p-2" required></div>
                    <div><label class="block text-sm font-medium mb-1">Lectura</label><input type="number" step="0.01" id="lectura" name="lectura" placeholder="Inserte aquí la lectura" class="w-full border rounded-lg p-2" required></div>
                </div>
                
                <div id="camposLuz" class="bg-yellow-50 p-4 rounded-xl border border-yellow-200 grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div class="col-span-full font-bold text-yellow-800">Costos Fijos Luz (Ingresar Total del Recibo):</div>
                    <div><label class="text-xs">Cargo Fijo</label><input type="number" step="0.01" name="luz_cargo_fijo" class="w-full border rounded p-1"></div>
                    <div><label class="text-xs">Mant. y Reposición</label><input type="number" step="0.01" name="luz_mantenimiento" class="w-full border rounded p-1"></div>
                    <div><label class="text-xs">Alumbrado Público</label><input type="number" step="0.01" name="luz_alumbrado" class="w-full border rounded p-1"></div>
                    <div><label class="text-xs">Interés Compensatorio</label><input type="number" step="0.01" name="luz_interes" class="w-full border rounded p-1"></div>
                </div>

                <div id="camposAgua" class="hidden bg-blue-50 p-4 rounded-xl border border-blue-200 grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div class="col-span-full font-bold text-blue-800">Costos Fijos Agua (Ingresar Total del Recibo):</div>
                    <div><label class="text-xs">Servicio Alcantarillado</label><input type="number" step="0.01" name="agua_alcantarillado" class="w-full border rounded p-1"></div>
                    <div><label class="text-xs">Cargo Fijo</label><input type="number" step="0.01" name="agua_cargo_fijo" class="w-full border rounded p-1"></div>
                </div>

                <div class="flex justify-end"><button type="submit" class="bg-blue-600 text-white px-6 py-2 rounded-lg hover:bg-blue-700">Guardar</button></div>
            </form>
        </div>

        <div class="bg-white rounded-2xl shadow-xl p-6">
            <div class="flex justify-between items-center mb-4">
                <h2 class="text-xl font-bold">Historial</h2>
                <div class="flex gap-2">
                    <select id="filtroFamilia" onchange="aplicarFiltros()" class="border rounded p-1 text-sm"><option value="">Todas</option>{% for f in familias %}<option value="{{ f.nombre }}">{{ f.nombre }}</option>{% endfor %}</select>
                    <select id="filtroServicio" onchange="aplicarFiltros()" class="border rounded p-1 text-sm"><option value="">Todos</option><option value="Luz">Luz</option><option value="Agua">Agua</option></select>
                </div>
            </div>
            <div class="overflow-x-auto">
                <table class="min-w-full divide-y divide-gray-200">
                    <thead class="bg-gray-50"><tr><th class="px-4 py-2 text-left text-xs text-gray-500 uppercase">Fecha</th><th class="px-4 py-2 text-left text-xs text-gray-500 uppercase">Familia</th><th class="px-4 py-2 text-left text-xs text-gray-500 uppercase">Servicio</th><th class="px-4 py-2 text-left text-xs text-gray-500 uppercase">Lec. Ant</th><th class="px-4 py-2 text-left text-xs text-gray-500 uppercase">Lec. Act</th><th class="px-4 py-2 text-left text-xs text-gray-500 uppercase">Consumo</th><th class="px-4 py-2 text-left text-xs text-gray-500 uppercase">Total</th><th class="px-4 py-2"></th><th class="px-4 py-2"></th></tr></thead>
                    <tbody class="bg-white divide-y divide-gray-200">
                        {% for c in historial %}
                        <tr class="hover:bg-gray-100 cursor-pointer fila-dato" onclick="abrirModal(this)"
                            data-fecha="{{ c.fecha }}" data-familia="{{ c.familia_nombre }}" data-servicio="{{ c.servicio }}"
                            data-lectura-ant="{{ '%.2f'|format(c.lectura_anterior) }} {{ c.unidad }}"
                            data-lectura-act="{{ '%.2f'|format(c.lectura) }} {{ c.unidad }}"
                            data-consumo="{{ '%.2f'|format(c.consumo) }} {{ c.unidad }}"
                            data-subtotal="S/ {{ '%.2f'|format(c.subtotal) }}"
                            data-igv="S/ {{ '%.2f'|format(c.igv_monto) }}"
                            data-total="S/ {{ '%.2f'|format(c.costo_total) }}"
                            data-luz-cargo="S/ {{ '%.2f'|format(c.luz_cargo_fijo|default(0)) }}"
                            data-luz-mant="S/ {{ '%.2f'|format(c.luz_mantenimiento|default(0)) }}"
                            data-luz-alum="S/ {{ '%.2f'|format(c.luz_alumbrado|default(0)) }}"
                            data-luz-int="S/ {{ '%.2f'|format(c.luz_interes|default(0)) }}"
                            data-agua-alcan="S/ {{ '%.2f'|format(c.agua_alcantarillado|default(0)) }}"
                            data-agua-cargo="S/ {{ '%.2f'|format(c.agua_cargo_fijo|default(0)) }}"
                        >
                            <td class="px-4 py-2 text-sm">{{ c.fecha }}</td>
                            <td class="px-4 py-2 text-sm celda-familia">{{ c.familia_nombre }}</td>
                            <td class="px-4 py-2 text-sm celda-servicio">{{ c.servicio }}</td>
                            <td class="px-4 py-2 text-sm">{{ "%.2f"|format(c.lectura_anterior) }}</td>
                            <td class="px-4 py-2 text-sm">{{ "%.2f"|format(c.lectura) }}</td>
                            <td class="px-4 py-2 text-sm">{{ "%.2f"|format(c.consumo) }}</td>
                            <td class="px-4 py-2 text-sm font-bold text-green-600">S/ {{ "%.2f"|format(c.costo_total) }}</td>
                            <td class="px-4 py-2 text-right"><a href="{{ url_for('editar_consumo', cid=c.id) }}" class="text-blue-600 text-sm" onclick="event.stopPropagation()">Editar</a></td>
                            <td class="px-4 py-2 text-right"><form action="{{ url_for('eliminar_consumo', cid=c.id) }}" method="POST" onsubmit="return confirm('¿Borrar?');" onclick="event.stopPropagation()"><button class="text-red-600 text-sm">X</button></form></td>
                        </tr>
                        {% else %}<tr><td colspan="9" class="p-4 text-center text-gray-500">Sin datos</td></tr>{% endfor %}
                    </tbody>
                </table>
            </div>
        </div>
    </div>

    <div id="modalDetalle" class="hidden fixed inset-0 bg-gray-600 bg-opacity-50 z-50 flex items-center justify-center">
        <div class="bg-white p-6 rounded-2xl shadow-lg w-96 relative">
            <h3 class="text-xl font-bold mb-4 text-center">Detalle de Consumo</h3>
            <div class="space-y-2 text-sm">
                <div class="flex justify-between"><span class="text-gray-500">Familia:</span><span id="mFamilia" class="font-bold"></span></div>
                <div class="flex justify-between"><span class="text-gray-500">Servicio:</span><span id="mServicio"></span></div>
                <div class="flex justify-between"><span class="text-gray-500">Fecha:</span><span id="mFecha"></span></div>
                <hr>
                <div class="flex justify-between"><span>Lectura Ant:</span><span id="mLecturaAnt"></span></div>
                <div class="flex justify-between"><span>Lectura Act:</span><span id="mLecturaAct"></span></div>
                <div class="flex justify-between font-bold"><span>Consumo:</span><span id="mConsumo" class="text-blue-600"></span></div>
                <hr>
                <div class="flex justify-between"><span>Subtotal Energía/Agua:</span><span id="mSubtotal"></span></div>
                <div class="flex justify-between"><span>IGV:</span><span id="mIgv"></span></div>
                
                <div id="extrasLuz" class="hidden bg-yellow-50 p-2 rounded text-xs mt-2 space-y-1">
                    <div class="font-bold text-yellow-800">Cargos Fijos (Prorrateado):</div>
                    <div class="flex justify-between"><span>Cargo Fijo:</span><span id="mLuzCargo"></span></div>
                    <div class="flex justify-between"><span>Mantenimiento:</span><span id="mLuzMant"></span></div>
                    <div class="flex justify-between"><span>Alumbrado:</span><span id="mLuzAlum"></span></div>
                    <div class="flex justify-between"><span>Interés:</span><span id="mLuzInt"></span></div>
                </div>
                <div id="extrasAgua" class="hidden bg-blue-50 p-2 rounded text-xs mt-2 space-y-1">
                    <div class="font-bold text-blue-800">Cargos Fijos (Prorrateado):</div>
                    <div class="flex justify-between"><span>Alcantarillado:</span><span id="mAguaAlcan"></span></div>
                    <div class="flex justify-between"><span>Cargo Fijo:</span><span id="mAguaCargo"></span></div>
                </div>

                <div class="flex justify-between text-lg font-bold mt-4 pt-2 border-t"><span>Total a Pagar:</span><span id="mTotal" class="text-green-600"></span></div>
            </div>
            <button onclick="document.getElementById('modalDetalle').classList.add('hidden')" class="mt-6 w-full bg-blue-600 text-white py-2 rounded-xl">Cerrar</button>
        </div>
    </div>

    <script>
        window.addEventListener('DOMContentLoaded', () => {
            const dateInput = document.getElementById('fecha');
            if(dateInput) { 
                const d = new Date();
                dateInput.value = `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`; 
            }
            toggleCampos(); 
        });

        function toggleCampos() {
            const servicio = document.getElementById('selectServicio').value;
            const luzDiv = document.getElementById('camposLuz');
            const aguaDiv = document.getElementById('camposAgua');
            if (servicio === 'Luz') {
                luzDiv.classList.remove('hidden');
                aguaDiv.classList.add('hidden');
            } else {
                luzDiv.classList.add('hidden');
                aguaDiv.classList.remove('hidden');
            }
        }

        function aplicarFiltros() {
            const fFam = document.getElementById('filtroFamilia').value.toLowerCase();
            const fServ = document.getElementById('filtroServicio').value.toLowerCase();
            document.querySelectorAll('.fila-dato').forEach(row => {
                const txtFam = row.querySelector('.celda-familia').textContent.toLowerCase();
                const txtServ = row.querySelector('.celda-servicio').textContent.toLowerCase();
                row.style.display = (txtFam.includes(fFam) && txtServ.includes(fServ)) ? '' : 'none';
            });
        }

        function abrirModal(row) {
            const ds = row.dataset;
            document.getElementById('mFecha').textContent = ds.fecha;
            document.getElementById('mFamilia').textContent = ds.familia;
            document.getElementById('mServicio').textContent = ds.servicio;
            document.getElementById('mLecturaAnt').textContent = ds.lecturaAnt;
            document.getElementById('mLecturaAct').textContent = ds.lecturaAct;
            document.getElementById('mConsumo').textContent = ds.consumo;
            document.getElementById('mSubtotal').textContent = ds.subtotal;
            document.getElementById('mIgv').textContent = ds.igv;
            document.getElementById('mTotal').textContent = ds.total;

            const boxLuz = document.getElementById('extrasLuz');
            const boxAgua = document.getElementById('extrasAgua');

            if(ds.servicio === 'Luz') {
                boxLuz.classList.remove('hidden');
                boxAgua.classList.add('hidden');
                document.getElementById('mLuzCargo').textContent = ds.luzCargo;
                document.getElementById('mLuzMant').textContent = ds.luzMant;
                document.getElementById('mLuzAlum').textContent = ds.luzAlum;
                document.getElementById('mLuzInt').textContent = ds.luzInt;
            } else {
                boxLuz.classList.add('hidden');
                boxAgua.classList.remove('hidden');
                document.getElementById('mAguaAlcan').textContent = ds.aguaAlcan;
                document.getElementById('mAguaCargo').textContent = ds.aguaCargo;
            }

            document.getElementById('modalDetalle').classList.remove('hidden');
        }
    </script>
</body>
</html>
"""

CONFIG_HTML = """
<!DOCTYPE html><html lang="es"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Config</title><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-gray-100 min-h-screen p-4 md:p-8"><div class="container mx-auto"><div class="bg-white rounded-2xl shadow-xl p-6 mb-8 flex justify-between"><h1 class="text-3xl font-bold text-gray-800">Gestor</h1><nav class="flex gap-4"><a href="{{ url_for('index') }}" class="text-blue-600">Inicio</a></nav></div>{% if mensaje %}<div class="bg-green-100 p-4 rounded mb-6">{{ mensaje }}</div>{% endif %}<div class="bg-white rounded-2xl shadow-xl p-6"><form method="POST" class="space-y-4"><h3 class="font-bold">Familias</h3>{% for f in familias %}<div><label>Familia {{ loop.index }}:</label><input type="text" name="familia_nombre_{{ f.id }}" value="{{ f.nombre }}" class="border rounded p-2 w-full"></div>{% endfor %}<hr><h3 class="font-bold">Costos Base</h3><div><label>Costo kWh:</label><input type="number" step="0.0001" name="costo_kwh" value="{{ config.costo_kwh }}" class="border rounded p-2 w-full"></div><div><label>Costo m3:</label><input type="number" step="0.0001" name="costo_m3" value="{{ config.costo_m3 }}" class="border rounded p-2 w-full"></div><div><label>IGV (%):</label><input type="number" step="0.01" name="igv_porcentaje" value="{{ config.igv_porcentaje }}" class="border rounded p-2 w-full"></div><button class="bg-blue-600 text-white px-6 py-2 rounded">Guardar</button></form></div></div></body></html>
"""

EDIT_HTML = """
<!DOCTYPE html><html lang="es"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Editar</title><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-gray-100 p-8"><div class="max-w-md mx-auto bg-white rounded-xl shadow-md p-6"><h2 class="text-2xl font-bold mb-4">Editar</h2><form action="{{ url_for('actualizar_consumo', cid=consumo.id) }}" method="POST" class="space-y-4"><div><label>Familia</label><select name="familia" class="w-full border p-2">{% for f in familias %}<option value="{{ f.id }}" {% if consumo.familia_id == f.id %}selected{% endif %}>{{ f.nombre }}</option>{% endfor %}</select></div><div><label>Servicio</label><select name="servicio" class="w-full border p-2"><option value="Luz" {% if consumo.servicio == 'Luz' %}selected{% endif %}>Luz</option><option value="Agua" {% if consumo.servicio == 'Agua' %}selected{% endif %}>Agua</option></select></div><div><label>Fecha</label><input type="date" name="fecha" value="{{ consumo.fecha }}" class="w-full border p-2"></div><div><label>Lectura</label><input type="number" step="0.01" name="lectura" value="{{ consumo.lectura }}" class="w-full border p-2"></div><hr>
<div class="bg-yellow-50 p-2 rounded"><p class="font-bold text-xs">Extras Luz (Total Recibo):</p><input placeholder="Cargo Fijo" name="luz_cargo_fijo" type="number" step="0.01" class="border w-full text-xs mb-1"><input placeholder="Mantenimiento" name="luz_mantenimiento" type="number" step="0.01" class="border w-full text-xs mb-1"><input placeholder="Alumbrado" name="luz_alumbrado" type="number" step="0.01" class="border w-full text-xs mb-1"><input placeholder="Interés" name="luz_interes" type="number" step="0.01" class="border w-full text-xs"></div>
<div class="bg-blue-50 p-2 rounded"><p class="font-bold text-xs">Extras Agua (Total Recibo):</p><input placeholder="Alcantarillado" name="agua_alcantarillado" type="number" step="0.01" class="border w-full text-xs mb-1"><input placeholder="Cargo Fijo" name="agua_cargo_fijo" type="number" step="0.01" class="border w-full text-xs"></div>
<div class="flex justify-end gap-2"><a href="{{ url_for('index') }}" class="px-4 py-2 border rounded">Cancelar</a><button class="bg-blue-600 text-white px-4 py-2 rounded">Guardar</button></div></form></div></body></html>
"""

if __name__ == '__main__':
    print("DEBUG: Iniciando App...")
    app.run(debug=True)
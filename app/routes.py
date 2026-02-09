# =======================================================
# Archivo: app/routes.py
# =======================================================

from flask import Blueprint, render_template, request, redirect, url_for, session
from .services import (
    cargar_datos_desde_firebase, calcular_lectura_anterior, 
    guardar_consumo, actualizar_consumo_db, eliminar_consumo_db, 
    actualizar_configuracion_db, obtener_consumo_por_id
)
# Nota: Importamos la nueva función calcular_extras
from .utils import safe_float, calcular_extras

main_bp = Blueprint('main', __name__)

@main_bp.before_request
def verificar_login():
    if 'usuario' not in session and request.endpoint not in ['main.login', 'static']:
        return redirect(url_for('main.login'))

@main_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        datos = cargar_datos_desde_firebase()
        user_input = request.form.get("usuario")
        pass_input = request.form.get("contrasena")
        
        if user_input == datos["login"]["usuario"] and pass_input == datos["login"]["contrasena"]:
            session.permanent = True
            session['usuario'] = user_input
            return redirect(url_for('main.index'))
        return render_template('login.html', error="Credenciales incorrectas")
    return render_template('login.html')

@main_bp.route("/logout")
def logout():
    session.pop('usuario', None)
    return redirect(url_for('main.login'))

@main_bp.route("/", methods=["GET", "POST"])
def index():
    datos = cargar_datos_desde_firebase()
    mensaje = ""

    if request.method == "POST":
        try:
            familia_id = request.form["familia"]
            servicio = request.form["servicio"]
            fecha = request.form["fecha"]
            lectura_actual = safe_float(request.form["lectura"])

            familia_nombre = next((f['nombre'] for f in datos['familias'] if f['id'] == familia_id), 'Desconocida')
            
            lectura_anterior = calcular_lectura_anterior(familia_id, servicio, fecha)
            consumo = max(0, lectura_actual - lectura_anterior)
            
            # 1. Calcular Costo del Consumo (Energía/Agua pura)
            if servicio == "Luz":
                costo_unidad = datos["config"]["costo_kwh"]
                unidad = "kWh"
            else:
                costo_unidad = datos["config"]["costo_m3"]
                unidad = "m³"

            costo_consumo = consumo * costo_unidad

            # 2. Calcular Extras Prorrateados
            extras_data = calcular_extras(familia_id, servicio, request.form)
            total_extras = sum(extras_data.values())

            # 3. NUEVA LÓGICA DE IMPUESTOS
            # Base Imponible = Consumo + Extras
            base_imponible = costo_consumo + total_extras
            
            # IGV sobre la suma total
            igv_monto = base_imponible * datos["config"]["igv_porcentaje"]
            
            # Total Final
            costo_total = base_imponible + igv_monto
            
            nuevo_consumo = {
                "fecha": fecha, "familia_id": familia_id, "familia_nombre": familia_nombre,
                "servicio": servicio, "lectura": lectura_actual, "lectura_anterior": lectura_anterior,
                "consumo": consumo, "unidad": unidad, 
                "subtotal": costo_consumo, # Guardamos el costo de consumo puro como subtotal para referencia
                "igv_monto": igv_monto,
                "costo_total": costo_total,
                **extras_data 
            }
            
            guardar_consumo(nuevo_consumo)
            mensaje = "Datos guardados correctamente."
        except Exception as e:
            mensaje = f"Error: {e}"
        
        return redirect(url_for('main.index', mensaje=mensaje))
    
    historial = sorted(
        datos["consumos"], 
        key=lambda x: str(x.get("timestamp")) if x.get("timestamp") else x.get("fecha", '0'), 
        reverse=True
    )
    return render_template('index.html', familias=datos["familias"], historial=historial, config=datos["config"], mensaje=request.args.get('mensaje', ''))

@main_bp.route("/configuracion", methods=["GET", "POST"])
def configuracion():
    mensaje = ""
    if request.method == "POST":
        try:
            datos = cargar_datos_desde_firebase()
            familias_updates = {}
            for fam in datos["familias"]:
                nuevo_nombre = request.form.get(f"familia_nombre_{fam['id']}")
                if nuevo_nombre:
                    familias_updates[fam['id']] = nuevo_nombre
            
            config_updates = {
                "costo_kwh": safe_float(request.form["costo_kwh"]),
                "costo_m3": safe_float(request.form["costo_m3"]),
                "igv_porcentaje": safe_float(request.form["igv_porcentaje"])
            }
            
            actualizar_configuracion_db(familias_updates, config_updates)
            mensaje = "Configuración guardada."
        except Exception: mensaje = "Error al guardar."
    
    datos = cargar_datos_desde_firebase()
    return render_template('config.html', familias=datos["familias"], config=datos["config"], mensaje=mensaje)

@main_bp.route("/eliminar/<string:cid>", methods=["POST"])
def eliminar_consumo(cid):
    eliminar_consumo_db(cid)
    return redirect(url_for('main.index', mensaje="Eliminado."))

@main_bp.route("/editar/<string:cid>", methods=["GET"])
def editar_consumo(cid):
    consumo = obtener_consumo_por_id(cid)
    if not consumo: return redirect(url_for('main.index'))
    
    datos = cargar_datos_desde_firebase()
    
    campos_numericos = ['luz_cargo_fijo', 'luz_mantenimiento', 'luz_alumbrado', 'luz_interes', 'agua_alcantarillado', 'agua_cargo_fijo']
    for campo in campos_numericos:
        if campo not in consumo: consumo[campo] = 0.0

    return render_template('edit.html', consumo=consumo, familias=datos["familias"])

@main_bp.route("/actualizar/<string:cid>", methods=["POST"])
def actualizar_consumo(cid):
    try:
        datos = cargar_datos_desde_firebase()
        familia_id = request.form["familia"]
        servicio = request.form["servicio"]
        fecha = request.form["fecha"]
        lectura_actual = safe_float(request.form["lectura"])
        
        familia_nombre = next((f['nombre'] for f in datos['familias'] if f['id'] == familia_id), 'Desconocida')
        
        lectura_anterior = calcular_lectura_anterior(familia_id, servicio, fecha, excluir_id=cid)
        consumo = max(0, lectura_actual - lectura_anterior)
        
        if servicio == "Luz":
            costo_unidad = datos["config"]["costo_kwh"]
            unidad = "kWh"
        else:
            costo_unidad = datos["config"]["costo_m3"]
            unidad = "m³"

        # 1. Costo Consumo
        costo_consumo = consumo * costo_unidad

        # 2. Extras
        extras_data = calcular_extras(familia_id, servicio, request.form)
        total_extras = sum(extras_data.values())

        # 3. Nueva Lógica IGV
        base_imponible = costo_consumo + total_extras
        igv_monto = base_imponible * datos["config"]["igv_porcentaje"]
        costo_total = base_imponible + igv_monto

        nuevos_datos = {
            "fecha": fecha, "familia_id": familia_id, "familia_nombre": familia_nombre,
            "servicio": servicio, "lectura": lectura_actual, "lectura_anterior": lectura_anterior,
            "consumo": consumo, "unidad": unidad, 
            "subtotal": costo_consumo, 
            "igv_monto": igv_monto,
            "costo_total": costo_total,
            **extras_data
        }
        actualizar_consumo_db(cid, nuevos_datos)
        mensaje = "Actualizado."
    except Exception: mensaje = "Error al actualizar."
    return redirect(url_for('main.index', mensaje=mensaje))
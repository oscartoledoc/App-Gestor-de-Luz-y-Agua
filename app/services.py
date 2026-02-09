from firebase_admin import firestore
from . import db
from .config import Config

def cargar_datos_desde_firebase():
    if db is None: 
        return {"familias": [], "consumos": [], "config": {}, "login": {}}
    
    try:
        config_ref = db.collection(Config.CONFIG_DOC).document(Config.LOGIN_DOC)
        config_data = config_ref.get().to_dict() or {}
        
        defaults = {
            "costo_kwh": Config.COSTO_KWH_DEFECTO, "costo_m3": Config.COSTO_M3_DEFECTO, 
            "igv_porcentaje": Config.IGV_PORCENTAJE, "usuario": Config.LOGIN_USER, "contrasena": Config.LOGIN_PASS
        }
        for k, v in defaults.items():
            if k not in config_data: config_data[k] = v
            
        if not config_ref.get().exists: config_ref.set(config_data)

        familias = []
        familias_docs = list(db.collection(Config.FAMILIAS_COLLECTION).order_by("id").stream())
        if not familias_docs:
            for i in range(1, Config.NUM_FAMILIAS + 1):
                fid = f"familia_{i}"
                fdata = {"id": fid, "nombre": f"Familia {i}"}
                db.collection(Config.FAMILIAS_COLLECTION).document(fid).set(fdata)
                familias.append(fdata)
        else:
            familias = [d.to_dict() for d in familias_docs]

        consumos = []
        for doc in db.collection(Config.CONSUMOS_COLLECTION).stream():
            d = doc.to_dict()
            if 'servicio' in d:
                d['id'] = doc.id
                
                campos_extra = ['luz_cargo_fijo', 'luz_mantenimiento', 'luz_alumbrado', 'luz_interes', 'agua_alcantarillado', 'agua_cargo_fijo']
                for campo in campos_extra:
                    if campo not in d: d[campo] = 0.0
                
                d.setdefault('lectura_anterior', 0.0)
                d.setdefault('lectura', 0.0)
                d.setdefault('consumo', 0.0)
                d.setdefault('subtotal', 0.0)
                d.setdefault('igv_monto', 0.0)
                d.setdefault('costo_total', 0.0)
                d.setdefault('familia_nombre', '---')
                d.setdefault('unidad', '')
                d.setdefault('fecha', '')
                
                consumos.append(d)
        
        return {"familias": familias, "consumos": consumos, "config": config_data, "login": config_data}
    except Exception as e:
        print(f"Error cargando datos: {e}")
        return {"familias": [], "consumos": [], "config": {}, "login": {}}

def calcular_lectura_anterior(familia_id, servicio, fecha_corte, excluir_id=None):
    lectura_anterior = 0
    if db is None: return 0
    try:
        consumos_ref = db.collection(Config.CONSUMOS_COLLECTION)\
            .where("familia_id", "==", familia_id)\
            .where("servicio", "==", servicio)
        
        candidatos = []
        for doc in consumos_ref.stream():
            if excluir_id and doc.id == excluir_id: continue
            data = doc.to_dict()
            fecha_doc = data.get('fecha', '9999-99-99')
            if fecha_doc and fecha_doc < fecha_corte:
                candidatos.append(data)
                
        if candidatos:
            candidatos.sort(key=lambda x: x.get('fecha', '0'), reverse=True)
            lectura_anterior = candidatos[0].get('lectura', 0)
    except Exception: pass
    return lectura_anterior

def guardar_consumo(data):
    if db:
        data['timestamp'] = firestore.SERVER_TIMESTAMP
        db.collection(Config.CONSUMOS_COLLECTION).add(data)

def actualizar_consumo_db(cid, data):
    if db:
        data['timestamp'] = firestore.SERVER_TIMESTAMP
        db.collection(Config.CONSUMOS_COLLECTION).document(cid).update(data)

def eliminar_consumo_db(cid):
    if db:
        db.collection(Config.CONSUMOS_COLLECTION).document(cid).delete()

def actualizar_configuracion_db(familias_updates, config_updates):
    if db:
        for fid, nombre in familias_updates.items():
            db.collection(Config.FAMILIAS_COLLECTION).document(fid).update({"nombre": nombre})
        db.collection(Config.CONFIG_DOC).document(Config.LOGIN_DOC).update(config_updates)

def obtener_consumo_por_id(cid):
    if not db: return None
    doc = db.collection(Config.CONSUMOS_COLLECTION).document(cid).get()
    if doc.exists:
        data = doc.to_dict()
        data['id'] = cid
        return data
    return None
def safe_float(val):
    try:
        if not val: return 0.0
        return float(val)
    except (ValueError, TypeError):
        return 0.0

def calcular_extras_y_total(familia_id, servicio, subtotal_con_igv, form_data):
    porcentaje = 0.0
    if familia_id == 'familia_1':
        porcentaje = 0.13
    elif familia_id in ['familia_2', 'familia_3']:
        porcentaje = 0.435
    
    extras = {
        "luz_cargo_fijo": 0.0, "luz_mantenimiento": 0.0, "luz_alumbrado": 0.0, "luz_interes": 0.0,
        "agua_alcantarillado": 0.0, "agua_cargo_fijo": 0.0
    }

    if servicio == "Luz":
        extras['luz_cargo_fijo'] = safe_float(form_data.get('luz_cargo_fijo')) * porcentaje
        extras['luz_mantenimiento'] = safe_float(form_data.get('luz_mantenimiento')) * porcentaje
        extras['luz_alumbrado'] = safe_float(form_data.get('luz_alumbrado')) * porcentaje
        extras['luz_interes'] = safe_float(form_data.get('luz_interes')) * porcentaje
    elif servicio == "Agua":
        extras['agua_alcantarillado'] = safe_float(form_data.get('agua_alcantarillado')) * porcentaje
        extras['agua_cargo_fijo'] = safe_float(form_data.get('agua_cargo_fijo')) * porcentaje

    total_extras = sum(extras.values())
    costo_final = subtotal_con_igv + total_extras
    
    return extras, costo_final
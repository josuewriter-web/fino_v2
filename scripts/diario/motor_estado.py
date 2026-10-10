import json
from datetime import datetime

# ==========================================================
# FUNCIONES AUXILIARES
# ==========================================================
def mapear_kpis_estrategicos(kpis_brutos: dict) -> dict:
    """
    Traduce las llaves crudas de los diccionarios a las 10 llaves limpias 
    utilizadas en los objetivos estratégicos y en los criterios de las fases.
    """
    return {
        "ventas_diarias": kpis_brutos.get("venta_total_usd", 0),
        "ganancia_diaria": kpis_brutos.get("ganancia_real_usd", 0),
        "ticket_promedio": kpis_brutos.get("ticket_promedio_usd", 0),
        "clientes_dia": kpis_brutos.get("total_clientes", 0),
        "articulos_por_factura": kpis_brutos.get("articulos_por_factura", 0),
        "facturas_diarias": kpis_brutos.get("total_facturas", 0),
        "salud_inventario": kpis_brutos.get("salud_del_inventario", 0),
        "productos_en_riesgo": kpis_brutos.get("cantidad_skus_en_riesgo", 0),
        "productos_vencidos": kpis_brutos.get("cantidad_skus_vencidos", 0),
        "margen_bruto": kpis_brutos.get("ganancia_real_porcentaje", 0)
    }

# ==========================================================
# FUNCIONES DEL MOTOR
# ==========================================================
def actualizar_objetivos_estrategicos(estado: dict, kpis_mapeados: dict, fecha_hoy: str):
    objetivos = estado["perfil_negocio"]["objetivos_estrategicos"]

    suma_avances = 0
    total_metricas = 0

    kpis_decrecientes = ["productos_en_riesgo", "productos_vencidos"]

    for clave, valor_actual in kpis_mapeados.items():
        if clave in objetivos:
            objetivos[clave]["actual"] = valor_actual

            inicial = objetivos[clave].get("inicial", 0)
            objetivo_meta = objetivos[clave].get("objetivo", 0)

            avance = 0
            if clave in kpis_decrecientes:
                if valor_actual <= objetivo_meta:
                    avance = 100.0
                else:
                    avance = 0.0 
            else:
                if objetivo_meta > inicial:
                    avance = ((valor_actual - inicial) / (objetivo_meta - inicial)) * 100
                    avance = min(max(avance, 0), 100)
                else:
                    avance = 100 if valor_actual >= objetivo_meta else 0

            suma_avances += avance
            total_metricas += 1

    if total_metricas > 0:
        objetivos["avance_global"] = round(suma_avances / total_metricas, 2)

    objetivos["ultima_actualizacion"] = fecha_hoy


def procesar_observacion(estado: dict, fecha_hoy: str) -> bool:
    """
    Maneja la Fase 0 (Fase de Observación de 7 días).
    Retorna True si la Observación está activa hoy.
    Retorna False si la Observación terminó o no aplica.
    """
    perfil = estado["perfil_negocio"]
    obs = perfil.get("observacion", perfil.get("diagnostico", {}))
    estado_act = perfil["estado_actual"]

    # Si no está en observación y la fase no es 0, continuamos con el flujo normal
    if not obs.get("activo", False) and estado_act.get("fase") != 0:
        return False

    if not obs.get("fecha_inicio"):
        obs["fecha_inicio"] = fecha_hoy

    dia_actual = obs.get("dia_actual", 1)
    duracion = obs.get("duracion_dias", 7)

    # Cuando termina el periodo de observación (Día 8 en adelante)
    if dia_actual > duracion or obs.get("completado", False):
        obs["activo"] = False
        obs["completado"] = True

        # Transición oficial a Fase 1
        fase_1 = perfil["roadmap"]["fase_1"]
        estado_act["fase"] = 1
        estado_act["etapa"] = "Roadmap Oficial"
        estado_act["nombre_fase"] = fase_1["nombre"]
        estado_act["fecha_inicio"] = fecha_hoy
        estado_act["fecha_inicio_roadmap"] = fecha_hoy
        estado_act["dias_en_fase"] = 0  # Se incrementa a 1 en el flujo principal
        estado_act["progreso"] = 0
        estado_act["dias_estabilidad"] = 0
        estado_act["estado"] = "En progreso"

        # Registrar Fase 0 en el historial
        perfil["historial_fases"].append({
            "fase": 0,
            "nombre": "Fase de Observación",
            "fecha_inicio": obs["fecha_inicio"],
            "fecha_fin": fecha_hoy,
            "duracion_dias": duracion,
            "porcentaje_final": 100.0
        })
        return False  # Pasa a la evaluación regular de la Fase 1

    # Mientras se mantenga en los 7 días de observación
    progreso_calculado = round((dia_actual / duracion) * 100, 2)

    estado_act["fase"] = 0
    estado_act["etapa"] = "Fase de Observación"
    estado_act["nombre_fase"] = "Fase de Observación"
    estado_act["estado"] = "En progreso"
    estado_act["progreso"] = progreso_calculado
    estado_act["dias_en_fase"] = dia_actual

    # Preparar el día siguiente
    obs["dia_actual"] += 1
    if obs["dia_actual"] > duracion:
        obs["completado"] = True

    return True


def evaluar_fase_actual(estado: dict, kpis_mapeados: dict):
    estado_actual = estado["perfil_negocio"]["estado_actual"]
    fase_num = estado_actual["fase"]
    fase_key = f"fase_{fase_num}"
    roadmap = estado["perfil_negocio"]["roadmap"]

    if fase_key not in roadmap:
        return [], []

    criterios = roadmap[fase_key].get("criterios", {})
    cumplidos = []
    pendientes = []
    progreso = 0

    for crit_key, crit_val in criterios.items():
        kpi_name = crit_val["kpi"]
        objetivo = crit_val["objetivo"]
        peso = crit_val["peso"]
        comparacion = crit_val["comparacion"]

        actual = kpis_mapeados.get(kpi_name, 0)
        logrado = False
        avance_kpi = 0.0

        if comparacion == "mayor_igual" and actual >= objetivo:
            logrado = True
        elif comparacion == "menor_igual" and actual <= objetivo:
            logrado = True
        elif comparacion == "igual" and actual == objetivo:
            logrado = True

        if comparacion == "mayor_igual":
            if objetivo > 0:
                avance_kpi = min(actual / objetivo, 1.0)
            else:
                avance_kpi = 1.0 if actual >= 0 else 0.0
                
        elif comparacion == "menor_igual":
            if actual <= objetivo:
                avance_kpi = 1.0
            else:
                avance_kpi = (objetivo / actual) if actual > 0 else 0.0
                
        elif comparacion == "igual":
            avance_kpi = 1.0 if logrado else 0.0

        aporte = avance_kpi * peso
        progreso += aporte

        if logrado:
            cumplidos.append(crit_key)
        else:
            pendientes.append(crit_key)

    estado_actual["progreso"] = round(progreso, 2)
    return cumplidos, pendientes


def controlar_estabilidad(estado: dict, cumplidos: list, pendientes: list, fase_key: str):
    estado_actual = estado["perfil_negocio"]["estado_actual"]
    roadmap = estado["perfil_negocio"]["roadmap"]

    if fase_key not in roadmap:
        return False

    dias_requeridos = roadmap[fase_key].get("dias_estabilidad_requeridos", 14)

    if len(pendientes) == 0 and len(cumplidos) > 0:
        estado_actual["dias_estabilidad"] += 1

    return estado_actual["dias_estabilidad"] >= dias_requeridos


def avanzar_fase(estado: dict, fase_key: str, fecha_hoy: str):
    estado_actual = estado["perfil_negocio"]["estado_actual"]
    roadmap = estado["perfil_negocio"]["roadmap"]
    historial = estado["perfil_negocio"]["historial_fases"]

    fase_num = estado_actual["fase"]
    fecha_inicio = estado_actual.get("fecha_inicio", fecha_hoy)

    try:
        d1 = datetime.strptime(fecha_inicio, "%Y-%m-%d")
        d2 = datetime.strptime(fecha_hoy, "%Y-%m-%d")
        duracion = (d2 - d1).days
    except Exception:
        duracion = 0

    historial.append({
        "fase": fase_num,
        "nombre": roadmap[fase_key]["nombre"],
        "fecha_inicio": fecha_inicio,
        "fecha_fin": fecha_hoy,
        "duracion_dias": duracion,
        "porcentaje_final": estado_actual["progreso"]
    })

    siguiente_fase_num = fase_num + 1
    siguiente_fase_key = f"fase_{siguiente_fase_num}"

    if siguiente_fase_key in roadmap:
        estado_actual["fase"] = siguiente_fase_num
        estado_actual["nombre_fase"] = roadmap[siguiente_fase_key]["nombre"]
        estado_actual["fecha_inicio"] = fecha_hoy
        estado_actual["dias_en_fase"] = 0
        estado_actual["progreso"] = 0
        estado_actual["dias_estabilidad"] = 0
        estado_actual["estado"] = "En progreso"
    else:
        estado_actual["estado"] = "Roadmap Completado"


# ==========================================================
# FUNCIÓN PRINCIPAL DE EJECUCIÓN (ENTRY POINT)
# ==========================================================
def ejecutar_motor_estado(
    estado: dict, 
    kpis_financieros: dict, 
    kpis_inventario: dict, 
    fecha: str = None
) -> dict:

    fecha_hoy = fecha if fecha else datetime.today().strftime("%Y-%m-%d")

    # Extraer KPIs financieros anidados
    kpis_fin = kpis_financieros.get("kpis_financieros", kpis_financieros)
    kpis_totales_brutos = {**kpis_fin, **kpis_inventario}
    kpis_mapeados = mapear_kpis_estrategicos(kpis_totales_brutos)

    # 1. Actualizar objetivos estratégicos
    actualizar_objetivos_estrategicos(estado, kpis_mapeados, fecha_hoy)

    # 2. Controlar Fase de Observación (Fase 0)
    en_observacion = procesar_observacion(estado, fecha_hoy)

    if en_observacion:
        dia_actual = estado["perfil_negocio"]["estado_actual"]["dias_en_fase"]
        estado["perfil_negocio"]["ultima_evaluacion"] = {
            "fecha": fecha_hoy,
            "resultado": f"Observación en progreso (Día {dia_actual}/7)",
            "criterios_cumplidos": [],
            "criterios_pendientes": []
        }
        return estado

    # 3. Flujo para Fases del Roadmap (1 a 4)
    estado_actual = estado["perfil_negocio"]["estado_actual"]
    if not estado_actual.get("fecha_inicio"):
        estado_actual["fecha_inicio"] = fecha_hoy

    estado_actual["dias_en_fase"] += 1

    fase_num = estado_actual["fase"]
    fase_key = f"fase_{fase_num}"
    cumplidos, pendientes = evaluar_fase_actual(estado, kpis_mapeados)

    listo_para_avanzar = controlar_estabilidad(estado, cumplidos, pendientes, fase_key)

    config = estado["perfil_negocio"].get("configuracion", {})
    resultado_evaluacion = "En progreso"

    if listo_para_avanzar and config.get("avance_automatico", True):
        avanzar_fase(estado, fase_key, fecha_hoy)
        resultado_evaluacion = "Fase superada y avanzada"

    estado["perfil_negocio"]["ultima_evaluacion"] = {
        "fecha": fecha_hoy,
        "resultado": resultado_evaluacion,
        "criterios_cumplidos": cumplidos,
        "criterios_pendientes": pendientes
    }

    return estado

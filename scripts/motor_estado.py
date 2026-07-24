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
            # 1. Actualizar el valor actual
            objetivos[clave]["actual"] = valor_actual

            # 2. Extraer datos para calcular progreso
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

    # Extraer KPIs financieros en caso de que vengan anidados
    kpis_fin = kpis_financieros.get("kpis_financieros", kpis_financieros)
    kpis_totales_brutos = {**kpis_fin, **kpis_inventario}
    kpis_mapeados = mapear_kpis_estrategicos(kpis_totales_brutos)

    estado_actual = estado["perfil_negocio"]["estado_actual"]
    if not estado_actual.get("fecha_inicio"):
        estado_actual["fecha_inicio"] = fecha_hoy
    estado_actual["dias_en_fase"] += 1

    actualizar_objetivos_estrategicos(estado, kpis_mapeados, fecha_hoy)

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

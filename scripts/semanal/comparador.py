import json
import os
import sys
from datetime import datetime
from fastapi import FastAPI, HTTPException

app = FastAPI()


def parsear_fecha(fecha_str):
    if not fecha_str:
        return datetime.min
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(fecha_str, fmt)
        except ValueError:
            pass
    return datetime.min


def extraer_kpis(semana_dict: dict) -> dict:
    """Extrae el bloque kpis_semana si viene anidado en la raíz, o lo retorna directo."""
    if not isinstance(semana_dict, dict):
        return {}
    return semana_dict.get("kpis_semana", semana_dict)


def obtener_semana_id(act_kpis, semana_actual_raw):
    """Calcula automáticamente semana_id si no viene en el JSON."""
    semana_id = act_kpis.get("semana_id") or semana_actual_raw.get("semana_id")
    periodo = act_kpis.get("periodo", {})
    f_ini = periodo.get("fecha_inicio")

    if not semana_id and f_ini:
        dt = parsear_fecha(f_ini)
        if dt != datetime.min:
            iso_year, iso_week, _ = dt.isocalendar()
            semana_id = f"{iso_year}-W{iso_week:02d}"
        else:
            semana_id = "Semana-Desconocida"

    return semana_id


def normalizar_periodo(periodo_dict):
    """Asegura que el periodo tenga el campo cobertura_completa."""
    if not isinstance(periodo_dict, dict):
        return {}
    p = dict(periodo_dict)
    if "cobertura_completa" not in p:
        p["cobertura_completa"] = True
    return p


def calc_variacion(actual, anterior):
    """Calcula el cambio absoluto y la variación porcentual."""
    if actual is None and anterior is None:
        return None, None
    if actual is None or anterior is None:
        return None, None

    diff = actual - anterior
    pct = None if anterior == 0 else round((diff / abs(anterior)) * 100, 2)

    diff_val = (
        int(diff)
        if isinstance(actual, int) and isinstance(anterior, int)
        else round(diff, 4)
    )
    return diff_val, pct


def comparar_bloque_kpis(dict_actual, dict_anterior, orden_llaves=None):
    dict_actual = dict_actual or {}
    dict_anterior = dict_anterior or {}

    todas_las_llaves = set(dict_actual.keys()).union(set(dict_anterior.keys()))
    todas_las_llaves.discard("concentracion_top5_porcentaje")

    if orden_llaves:
        llaves_ordenadas = [k for k in orden_llaves if k in todas_las_llaves] + [k for k in sorted(todas_las_llaves) if k not in orden_llaves]
    else:
        llaves_ordenadas = sorted(todas_las_llaves)

    resultado = {}
    for key in llaves_ordenadas:
        val_act = dict_actual.get(key)
        val_ant = dict_anterior.get(key)

        if isinstance(val_act, dict) or isinstance(val_ant, dict):
            sub_orden = None
            if key == "desglose_origen":
                sub_orden = ["reventa", "elaborado"]
            elif key in ("reventa", "elaborado"):
                sub_orden = ["ventas_usd", "costo_usd", "ganancia_usd", "margen_porcentaje", "unidades"]

            resultado[key] = comparar_bloque_kpis(val_act, val_ant, orden_llaves=sub_orden)
        elif isinstance(val_act, (int, float)) or isinstance(val_ant, (int, float)):
            abs_change, pct_change = calc_variacion(val_act, val_ant)
            resultado[key] = {
                "anterior": val_ant,
                "actual": val_act,
                "cambio_absoluto": abs_change,
                "variacion_porcentual": pct_change,
            }
        else:
            resultado[key] = {"anterior": val_ant, "actual": val_act}
    return resultado


def comparar_categorias(cats_actual, cats_anterior):
    cats_act_map = {
        c["categoria"]: c
        for c in (cats_actual or [])
        if isinstance(c, dict) and "categoria" in c
    }
    cats_ant_map = {
        c["categoria"]: c
        for c in (cats_anterior or [])
        if isinstance(c, dict) and "categoria" in c
    }
    todas = set(cats_act_map.keys()).union(set(cats_ant_map.keys()))

    lista_comparacion = []
    campos_num = [
        "ventas_usd",
        "costo_usd",
        "ganancia_usd",
        "unidades",
        "dias_presente",
        "margen_porcentaje",
    ]

    for cat in todas:
        act = cats_act_map.get(cat)
        ant = cats_ant_map.get(cat)

        res_cat = {}

        for campo in campos_num:
            v_act = act.get(campo) if act else None
            v_ant = ant.get(campo) if ant else None
            abs_c, pct_c = calc_variacion(v_act, v_ant)
            res_cat[campo] = {
                "anterior": v_ant,
                "actual": v_act,
                "cambio_absoluto": abs_c,
                "variacion_porcentual": pct_c,
            }

        p_act = act.get("participacion_porcentaje") if act else None
        p_ant = ant.get("participacion_porcentaje") if act else None
        p_abs, p_pct = calc_variacion(p_act, p_ant)
        res_cat["participacion_porcentaje"] = {
            "anterior": p_ant,
            "actual": p_act,
            "cambio_puntos_porcentuales": p_abs,
            "variacion_porcentual": p_pct,
        }

        ventas_orden = act.get("ventas_usd", 0) if act else 0
        lista_comparacion.append((ventas_orden, cat, res_cat))

    lista_comparacion.sort(key=lambda x: x[0], reverse=True)

    resultado = {}
    for _, cat_nombre, item in lista_comparacion:
        resultado[cat_nombre] = item

    return resultado


def comparar_comportamiento_temporal(temp_act, temp_ant):
    temp_act = temp_act or {}
    temp_ant = temp_ant or {}
    bloques = set(temp_act.keys()).union(set(temp_ant.keys()))

    resultado = {}
    for b in bloques:
        act = temp_act.get(b, {})
        ant = temp_ant.get(b, {})

        metricas = {}
        for m in ["ventas", "facturas", "ticket_promedio"]:
            v_act = act.get(m)
            v_ant = ant.get(m)
            abs_c, pct_c = calc_variacion(v_act, v_ant)
            metricas[m] = {
                "anterior": v_ant,
                "actual": v_act,
                "cambio_absoluto": abs_c,
                "variacion_porcentual": pct_c,
            }

        resultado[b] = metricas
    return resultado


def extraer_top_productos_temporales(temp_act):
    """Extrae únicamente las listas de top productos vendidos por cada bloque horario."""
    temp_act = temp_act or {}
    resultado = {}
    for turno, datos in temp_act.items():
        if isinstance(datos, dict):
            resultado[turno] = datos.get("top_productos", [])
    return resultado


def comparar_semanas(semana_actual, semana_pasada):
    act_kpis = extraer_kpis(semana_actual)
    pas_kpis = extraer_kpis(semana_pasada)

    semana_id = obtener_semana_id(act_kpis, semana_actual)
    comparacion_disponible = bool(
        pas_kpis and isinstance(pas_kpis, dict) and pas_kpis.get("periodo")
    )

    top_prods_temporal = extraer_top_productos_temporales(
        act_kpis.get("comportamiento_temporal", {})
    )

    periodo_actual = normalizar_periodo(act_kpis.get("periodo", {}))
    periodo_anterior = normalizar_periodo(pas_kpis.get("periodo", {})) if comparacion_disponible else None

    datos_absolutos = {
        "semana_id": semana_id,
        "periodo": periodo_actual,
        "hitos_semanales": act_kpis.get("hitos_semanales", {}),
        "evolucion_diaria": act_kpis.get("evolucion_diaria", []),
        "tops": {
            "top_vendidos": act_kpis.get("top_vendidos", []),
            "top_rentables": act_kpis.get("top_rentables", []),
            "top_skus_sin_venta": act_kpis.get("top_skus_sin_venta", []),
        },
        "comportamiento_temporal_productos": top_prods_temporal,
        "afinidad_productos": act_kpis.get("afinidad_productos"),
    }

    if not comparacion_disponible:
        datos_absolutos["mensaje"] = "No se proporcionó información válida de la semana pasada."
        return {
            "datos_absolutos": datos_absolutos,
            "variaciones_semanales": {
                "comparacion_disponible": False,
                "semana_id": semana_id,
                "periodo_actual": periodo_actual,
                "periodo_anterior": None,
                "datos_semana_actual": act_kpis,
            },
        }

    orden_kpis_semanales = [
        "venta_total_usd",
        "costo_total_usd",
        "ganancia_total_usd",
        "margen_semanal_porcentaje",
        "unidades_totales_vendidas",
        "total_facturas",
        "total_clientes",
        "ticket_promedio_usd",
        "articulos_por_factura",
        "desglose_origen"
    ]

    orden_inventario = [
        "unidades_inicio_semana",
        "unidades_fin_semana",
        "skus_activos_fin_semana",
        "salud_inventario_porcentaje",
        "costo_inventario_usd",
        "venta_potencial_usd",
        "ganancia_proyectada_usd",
        "mermas_totales_unidades",
        "mermas_totales_usd",
        "valor_en_riesgo_usd",
        "valor_vencido_usd",
        "capital_estancado_total_costo_usd",
        "capital_estancado_total_venta_usd"
    ]

    return {
        "datos_absolutos": datos_absolutos,
        "variaciones_semanales": {
            "comparacion_disponible": True,
            "semana_id": semana_id,
            "periodo_actual": periodo_actual,
            "periodo_anterior": periodo_anterior,
            "kpis_semanales": comparar_bloque_kpis(
                act_kpis.get("kpis_semanales"), 
                pas_kpis.get("kpis_semanales"),
                orden_llaves=orden_kpis_semanales
            ),
            "inventario": comparar_bloque_kpis(
                act_kpis.get("inventario"), 
                pas_kpis.get("inventario"),
                orden_llaves=orden_inventario
            ),
            "categorias": comparar_categorias(
                act_kpis.get("categorias"), 
                pas_kpis.get("categorias")
            ),
            "comportamiento_temporal": comparar_comportamiento_temporal(
                act_kpis.get("comportamiento_temporal"),
                pas_kpis.get("comportamiento_temporal"),
            ),
        },
    }


@app.post("/")
async def endpoint_comparador_semanal(payload: dict):
    """
    Endpoint FastAPI para recibir las solicitudes HTTP desde Make.com.
    Espera un JSON con estructura: {"semana_actual": {...}, "semana_pasada": {...}}
    """
    try:
        semana_actual = payload.get("semana_actual")
        semana_pasada = payload.get("semana_pasada")

        if not semana_actual:
            raise HTTPException(
                status_code=400, 
                detail="El campo 'semana_actual' es obligatorio en el cuerpo de la solicitud."
            )

        resultado = comparar_semanas(semana_actual, semana_pasada)
        return resultado

    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

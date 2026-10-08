from datetime import datetime
from typing import Any, Dict, Optional
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI(title="Comparador Semanal API")


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


def obtener_identificadores(act_kpis, semana_actual_raw):
    """Calcula automáticamente semana_id y fechas_rango si no vienen en el JSON."""
    semana_id = act_kpis.get("semana_id") or semana_actual_raw.get("semana_id")
    fechas_rango = act_kpis.get("fechas_rango") or semana_actual_raw.get("fechas_rango")

    periodo = act_kpis.get("periodo", {})
    f_ini = periodo.get("fecha_inicio")
    f_fin = periodo.get("fecha_fin")

    if not fechas_rango and f_ini and f_fin:
        fechas_rango = f"{f_ini} al {f_fin}" if f_ini != f_fin else f_ini

    if not semana_id and f_ini:
        dt = parsear_fecha(f_ini)
        if dt != datetime.min:
            iso_year, iso_week, _ = dt.isocalendar()
            semana_id = f"{iso_year}-W{iso_week:02d}"
        else:
            semana_id = "Semana-Desconocida"

    return semana_id, fechas_rango


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


def comparar_bloque_kpis(dict_actual, dict_anterior):
    dict_actual = dict_actual or {}
    dict_anterior = dict_anterior or {}

    todas_las_llaves = set(dict_actual.keys()).union(set(dict_anterior.keys()))
    todas_las_llaves.discard("concentracion_top5_porcentaje")

    resultado = {}

    for key in todas_las_llaves:
        val_act = dict_actual.get(key)
        val_ant = dict_anterior.get(key)

        if isinstance(val_act, dict) or isinstance(val_ant, dict):
            resultado[key] = comparar_bloque_kpis(val_act, val_ant)
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

    resultado = {}
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

        res_cat = {
            "estado": "mantiene" if act and ant else ("nuevo" if act else "salio")
        }

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
        p_ant = ant.get("participacion_porcentaje") if ant else None
        p_abs, p_pct = calc_variacion(p_act, p_ant)
        res_cat["participacion_porcentaje"] = {
            "anterior": p_ant,
            "actual": p_act,
            "cambio_puntos_porcentuales": p_abs,
            "variacion_porcentual": p_pct,
        }

        resultado[cat] = res_cat
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

    semana_id, fechas_rango = obtener_identificadores(act_kpis, semana_actual)
    comparacion_disponible = bool(
        pas_kpis and isinstance(pas_kpis, dict) and pas_kpis.get("periodo")
    )

    top_prods_temporal = extraer_top_productos_temporales(
        act_kpis.get("comportamiento_temporal", {})
    )

    # Sección datos_semana (SOLO DATOS CRUDOS DE LA SEMANA ACTUAL)
    datos_semana = {
        "comparacion_disponible": comparacion_disponible,
        "semana_id": semana_id,
        "fechas_rango": fechas_rango,
        "periodo": act_kpis.get("periodo", {}),
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
        datos_semana["mensaje"] = "No se proporcionó información válida de la semana pasada."
        return {
            "datos_semana": datos_semana,
            "metricas_comparadas": {
                "datos_semana_actual": act_kpis
            },
        }

    return {
        "datos_semana": datos_semana,
        "metricas_comparadas": {
            "kpis_semanales": comparar_bloque_kpis(
                act_kpis.get("kpis_semanales"), pas_kpis.get("kpis_semanales")
            ),
            "inventario": comparar_bloque_kpis(
                act_kpis.get("inventario"), pas_kpis.get("inventario")
            ),
            "categorias": comparar_categorias(
                act_kpis.get("categorias"), pas_kpis.get("categorias")
            ),
            "comportamiento_temporal": comparar_comportamiento_temporal(
                act_kpis.get("comportamiento_temporal"),
                pas_kpis.get("comportamiento_temporal"),
            ),
        },
    }


# --- RUTAS DE LA API ---

@app.get("/")
def home():
    return {"status": "ok", "message": "API Comparador activa"}


@app.post("/comparar")
async def api_comparar(request: Request):
    data = await request.json()
    semana_actual = data.get("semana_actual", data)
    semana_pasada = data.get("semana_pasada")

    resultado = comparar_semanas(semana_actual, semana_pasada)
    return JSONResponse(content=resultado)

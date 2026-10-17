from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, Optional
from datetime import datetime

app = FastAPI(title="FINO - Comparador Mensual API")

class ComparacionMensualRequest(BaseModel):
    mes_actual: Dict[str, Any]
    mes_pasado: Optional[Dict[str, Any]] = None


def parsear_fecha(fecha_str):
    if not fecha_str:
        return datetime.min
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(fecha_str, fmt)
        except ValueError:
            pass
    return datetime.min


def extraer_kpis(mes_dict: dict) -> dict:
    if not isinstance(mes_dict, dict):
        return {}
    return mes_dict.get("kpis_mes", mes_dict)


def obtener_identificador_mes(act_kpis, mes_actual_raw):
    mes_id = act_kpis.get("mes_id") or mes_actual_raw.get("mes_id")
    periodo = act_kpis.get("periodo", {})
    f_ini = periodo.get("fecha_inicio")

    if not mes_id and f_ini:
        dt = parsear_fecha(f_ini)
        if dt != datetime.min:
            mes_id = f"{dt.year}-{dt.month:02d}"
        else:
            mes_id = "Mes-Desconocido"
    return mes_id


def calc_variacion(actual, anterior):
    if actual is None or anterior is None:
        return None, None
    diff = actual - anterior
    pct = None if anterior == 0 else round((diff / abs(anterior)) * 100, 2)
    diff_val = int(diff) if isinstance(actual, int) and isinstance(anterior, int) else round(diff, 4)
    return diff_val, pct


def comparar_bloque_kpis(dict_actual, dict_anterior, orden_llaves=None):
    dict_actual = dict_actual or {}
    dict_anterior = dict_anterior or {}
    todas_las_llaves = set(dict_actual.keys()).union(set(dict_anterior.keys()))

    if orden_llaves:
        llaves_ordenadas = [k for k in orden_llaves if k in todas_las_llaves] + [k for k in sorted(todas_las_llaves) if k not in orden_llaves]
    else:
        llaves_ordenadas = sorted(todas_las_llaves)

    resultado = {}
    for key in llaves_ordenadas:
        val_act = dict_actual.get(key)
        val_ant = dict_anterior.get(key)
        if isinstance(val_act, dict) or isinstance(val_ant, dict):
            sub_orden = ["reventa", "elaborado"] if key == "desglose_origen" else (["ventas_usd", "costo_usd", "ganancia_usd", "margen_porcentaje", "unidades"] if key in ("reventa", "elaborado") else None)
            resultado[key] = comparar_bloque_kpis(val_act, val_ant, orden_llaves=sub_orden)
        elif isinstance(val_act, (int, float)) or isinstance(val_ant, (int, float)):
            abs_change, pct_change = calc_variacion(val_act, val_ant)
            resultado[key] = {"anterior": val_ant, "actual": val_act, "cambio_absoluto": abs_change, "variacion_porcentual": pct_change}
        else:
            resultado[key] = {"anterior": val_ant, "actual": val_act}
    return resultado


def comparar_categorias(cats_actual, cats_anterior):
    cats_act_map = {c["categoria"]: c for c in (cats_actual or []) if isinstance(c, dict) and "categoria" in c}
    cats_ant_map = {c["categoria"]: c for c in (cats_anterior or []) if isinstance(c, dict) and "categoria" in c}
    todas = set(cats_act_map.keys()).union(set(cats_ant_map.keys()))
    lista_comparacion = []
    campos_num = ["ventas_usd", "costo_usd", "ganancia_usd", "unidades_vendidas", "dias_presente", "margen_porcentaje"]

    for cat in todas:
        act = cats_act_map.get(cat)
        ant = cats_ant_map.get(cat)
        res_cat = {}
        for campo in campos_num:
            v_act = act.get(campo) if act else None
            v_ant = ant.get(campo) if ant else None
            abs_c, pct_c = calc_variacion(v_act, v_ant)
            res_cat[campo] = {"anterior": v_ant, "actual": v_act, "cambio_absoluto": abs_c, "variacion_porcentual": pct_c}
        p_act = act.get("participacion_porcentaje") if act else None
        p_ant = ant.get("participacion_porcentaje") if act else None
        p_abs, p_pct = calc_variacion(p_act, p_ant)
        res_cat["participacion_porcentaje"] = {"anterior": p_ant, "actual": p_act, "cambio_puntos_porcentuales": p_abs, "variacion_porcentual": p_pct}
        ventas_orden = act.get("ventas_usd", 0) if act else 0
        lista_comparacion.append((ventas_orden, cat, res_cat))

    lista_comparacion.sort(key=lambda x: x[0], reverse=True)
    return {cat_nombre: item for _, cat_nombre, item in lista_comparacion}


@app.post("/comparar-mes")
def endpoint_comparar_mes(payload: ComparacionMensualRequest):
    try:
        act_kpis = extraer_kpis(payload.mes_actual)
        pas_kpis = extraer_kpis(payload.mes_pasado) if payload.mes_pasado else {}

        mes_id = obtener_identificador_mes(act_kpis, payload.mes_actual)
        comparacion_disponible = bool(pas_kpis and isinstance(pas_kpis, dict) and pas_kpis.get("kpis_financieros"))

        periodo_actual = act_kpis.get("periodo", {})
        periodo_anterior = pas_kpis.get("periodo", {}) if comparacion_disponible else None

        datos_absolutos = {
            "mes_id": mes_id,
            "periodo": periodo_actual,
            "rankings": act_kpis.get("rankings", {}),
            "serie_semanal": act_kpis.get("serie_semanal", []),
        }

        if not comparacion_disponible:
            datos_absolutos["mensaje"] = "No se proporcionó información válida del mes pasado."
            return {
                "datos_absolutos": datos_absolutos,
                "variaciones_mensuales": {
                    "comparacion_disponible": False,
                    "mes_id": mes_id,
                    "periodo_actual": periodo_actual,
                    "periodo_anterior": None,
                    "datos_mes_actual": act_kpis,
                },
            }

        orden_financieros = ["venta_total_usd", "costo_total_usd", "ganancia_total_usd", "margen_mensual_porcentaje", "unidades_totales_vendidas", "total_facturas", "total_clientes", "ticket_promedio_usd", "articulos_por_factura", "articulos_por_cliente", "desglose_origen"]
        orden_inventario_final = ["fecha", "total_skus", "total_unidades", "valor_costo_usd", "valor_potencial_usd", "ganancia_proyectada_usd", "salud_inventario_porcentaje", "valor_en_riesgo_usd", "valor_vencido_usd"]

        val_econ_act = act_kpis.get("valor_economico_inventario", {})
        val_econ_pas = pas_kpis.get("valor_economico_inventario", {})

        return {
            "datos_absolutos": datos_absolutos,
            "variaciones_mensuales": {
                "comparacion_disponible": True,
                "mes_id": mes_id,
                "periodo_actual": periodo_actual,
                "periodo_anterior": periodo_anterior,
                "kpis_financieros": comparar_bloque_kpis(act_kpis.get("kpis_financieros"), pas_kpis.get("kpis_financieros"), orden_llaves=orden_financieros),
                "kpis_inventario": comparar_bloque_kpis(act_kpis.get("kpis_inventario"), pas_kpis.get("kpis_inventario")),
                "inventario_final": comparar_bloque_kpis(val_econ_act.get("inventario_final", {}), val_econ_pas.get("inventario_final", {}), orden_llaves=orden_inventario_final),
                "categorias": comparar_categorias(act_kpis.get("categorias"), pas_kpis.get("categorias")),
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

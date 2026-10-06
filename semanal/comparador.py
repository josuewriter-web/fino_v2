from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI()

# Claves que se ignoran completamente
LLAVES_IGNORADAS = {"tabla_mix", "top_skus_rotacion"}


def calc_variacion(actual, anterior):
    if actual is None and anterior is None:
        return None, None
    if actual is None or anterior is None:
        return None, None

    diff = actual - anterior
    if anterior == 0:
        pct = None
    else:
        pct = round((diff / abs(anterior)) * 100, 2)

    diff_val = (
        int(diff)
        if isinstance(actual, int) and isinstance(anterior, int)
        else round(diff, 4)
    )
    return diff_val, pct


def comparar_bloque_kpis(dict_actual, dict_anterior):
    dict_actual = dict_actual or {}
    dict_anterior = dict_anterior or {}

    todas_las_llaves = (
        set(dict_actual.keys()).union(set(dict_anterior.keys()))
    ) - LLAVES_IGNORADAS
    resultado = {}

    for key in todas_las_llaves:
        val_act = dict_actual.get(key)
        val_ant = dict_anterior.get(key)

        if isinstance(val_act, dict) or isinstance(val_ant, dict):
            resultado[key] = comparar_bloque_kpis(val_act, val_ant)
        elif isinstance(val_act, (int, float)) or isinstance(
            val_ant, (int, float)
        ):
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


def comparar_evolucion_diaria(act_list, ant_list):
    act_list = act_list or []
    ant_list = ant_list or []
    max_dias = max(len(act_list), len(ant_list))

    resultado = []
    campos_num = ["ventas_usd", "facturas", "ticket_promedio"]

    for i in range(max_dias):
        act = act_list[i] if i < len(act_list) else {}
        ant = ant_list[i] if i < len(ant_list) else {}

        res_dia = {
            "dia_numero": i + 1,
            "fecha_actual": act.get("fecha"),
            "fecha_anterior": ant.get("fecha"),
        }

        for campo in campos_num:
            v_act = act.get(campo)
            v_ant = ant.get(campo)
            abs_c, pct_c = calc_variacion(v_act, v_ant)
            res_dia[campo] = {
                "anterior": v_ant,
                "actual": v_act,
                "cambio_absoluto": abs_c,
                "variacion_porcentual": pct_c,
            }
        resultado.append(res_dia)
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


def comparar_ranking(actual_list, anterior_list, campo_valor):
    actual_list = actual_list or []
    anterior_list = anterior_list or []

    get_id = lambda p: p.get("codigo") or p.get("codigo_articulo") or p.get("nombre")

    act_map = {
        get_id(p): (idx + 1, p)
        for idx, p in enumerate(actual_list)
        if get_id(p)
    }
    ant_map = {
        get_id(p): (idx + 1, p)
        for idx, p in enumerate(anterior_list)
        if get_id(p)
    }

    todos_ids = set(act_map.keys()).union(set(ant_map.keys()))
    items = []

    for identifier in todos_ids:
        act_info = act_map.get(identifier)
        ant_info = ant_map.get(identifier)

        if act_info and ant_info:
            pos_act, p_act = act_info
            pos_ant, p_ant = ant_info
            shift = pos_ant - pos_act
            estado = "subio" if shift > 0 else ("bajo" if shift < 0 else "mantiene")

            v_act = p_act.get(campo_valor)
            v_ant = p_ant.get(campo_valor)
            abs_c, pct_c = calc_variacion(v_act, v_ant)

            items.append(
                {
                    "codigo": p_act.get("codigo")
                    or p_act.get("codigo_articulo")
                    or p_ant.get("codigo")
                    or p_ant.get("codigo_articulo"),
                    "nombre": p_act.get("nombre", p_ant.get("nombre")),
                    "estado": estado,
                    "posicion_anterior": pos_ant,
                    "posicion_actual": pos_act,
                    "cambio_posicion": shift,
                    "valor_anterior": v_ant,
                    "valor_actual": v_act,
                    "cambio_absoluto": abs_c,
                    "variacion_porcentual": pct_c,
                }
            )
        elif act_info:
            pos_act, p_act = act_info
            items.append(
                {
                    "codigo": p_act.get("codigo") or p_act.get("codigo_articulo"),
                    "nombre": p_act.get("nombre"),
                    "estado": "nuevo",
                    "posicion_anterior": None,
                    "posicion_actual": pos_act,
                    "cambio_posicion": None,
                    "valor_anterior": None,
                    "valor_actual": p_act.get(campo_valor),
                    "cambio_absoluto": None,
                    "variacion_porcentual": None,
                }
            )
        else:
            pos_ant, p_ant = ant_info
            items.append(
                {
                    "codigo": p_ant.get("codigo") or p_ant.get("codigo_articulo"),
                    "nombre": p_ant.get("nombre"),
                    "estado": "salio",
                    "posicion_anterior": pos_ant,
                    "posicion_actual": None,
                    "cambio_posicion": None,
                    "valor_anterior": p_ant.get(campo_valor),
                    "valor_actual": None,
                    "cambio_absoluto": None,
                    "variacion_porcentual": None,
                }
            )

    return sorted(
        items, key=lambda x: (x["posicion_actual"] is None, x["posicion_actual"] or 999)
    )


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

        prods_act = act.get("top_productos", [])
        prods_ant = ant.get("top_productos", [])
        prods_comp = comparar_ranking(prods_act, prods_ant, "unidades")

        resultado[b] = {"metricas": metricas, "top_productos": prods_comp}
    return resultado


def comparar_semanas(semana_actual, semana_pasada):
    if (
        not semana_pasada
        or not isinstance(semana_pasada, dict)
        or not semana_pasada.get("periodo")
    ):
        semana_limpia = {
            k: v
            for k, v in (semana_actual or {}).items()
            if k not in LLAVES_IGNORADAS
        }
        return {
            "comparacion_disponible": False,
            "mensaje": "No se proporcionó información válida de la semana pasada.",
            "periodo_actual": semana_actual.get("periodo", {})
            if isinstance(semana_actual, dict)
            else {},
            "periodo_anterior": None,
            "datos_semana_actual": semana_limpia,
        }

    semana_actual = semana_actual or {}

    c_act = semana_actual.get("kpis_semanales", {}).get(
        "concentracion_top5_porcentaje"
    )
    c_ant = semana_pasada.get("kpis_semanales", {}).get(
        "concentracion_top5_porcentaje"
    )
    c_abs, c_pct = calc_variacion(c_act, c_ant)

    af_act = semana_actual.get("afinidad_productos")
    af_ant = semana_pasada.get("afinidad_productos")

    return {
        "comparacion_disponible": True,
        "periodo_actual": semana_actual.get("periodo", {}),
        "periodo_anterior": semana_pasada.get("periodo", {}),
        "kpis_semanales": comparar_bloque_kpis(
            semana_actual.get("kpis_semanales"), semana_pasada.get("kpis_semanales")
        ),
        "evolucion_diaria": {
            "registros_diarios_comparados": comparar_evolucion_diaria(
                semana_actual.get("evolucion_diaria", []),
                semana_pasada.get("evolucion_diaria", []),
            ),
            "hitos_semana_actual": semana_actual.get("hitos_semanales", {}),
            "hitos_semana_anterior": semana_pasada.get("hitos_semanales", {}),
        },
        "inventario": comparar_bloque_kpis(
            semana_actual.get("inventario"), semana_pasada.get("inventario")
        ),
        "categorias": comparar_categorias(
            semana_actual.get("categorias"), semana_pasada.get("categorias")
        ),
        "top_vendidos": comparar_ranking(
            semana_actual.get("top_vendidos"),
            semana_pasada.get("top_vendidos"),
            "unidades",
        ),
        "top_facturacion": comparar_ranking(
            semana_actual.get("top_facturacion"),
            semana_pasada.get("top_facturacion"),
            "ventas_usd",
        ),
        "top_rentables": comparar_ranking(
            semana_actual.get("top_rentables"),
            semana_pasada.get("top_rentables"),
            "ganancia_usd",
        ),
        "top_baja_rotacion": comparar_ranking(
            semana_actual.get("top_baja_rotacion"),
            semana_pasada.get("top_baja_rotacion"),
            "unidades",
        ),
        "top_skus_sin_venta": comparar_ranking(
            semana_actual.get("top_skus_sin_venta"),
            semana_pasada.get("top_skus_sin_venta"),
            "capital_estancado_costo_usd",
        ),
        "comportamiento_temporal": comparar_comportamiento_temporal(
            semana_actual.get("comportamiento_temporal"),
            semana_pasada.get("comportamiento_temporal"),
        ),
        "concentracion": {
            "anterior": c_ant,
            "actual": c_act,
            "cambio_puntos_porcentuales": c_abs,
            "variacion_porcentual": c_pct,
        },
        "afinidad_productos": {
            "anterior": af_ant,
            "actual": af_act,
            "diferencias_detectadas": af_act != af_ant,
        },
    }


# --- RUTA DE LA API PARA MAKE ---

@app.post("/comparar")
async def api_comparar(request: Request):
    data = await request.json()
    semana_actual = data.get("semana_actual", {})
    semana_pasada = data.get("semana_pasada", {})
    
    resultado = comparar_semanas(semana_actual, semana_pasada)
    return JSONResponse(content=resultado)


@app.get("/")
def home():
    return {"status": "ok", "message": "API Comparador activa"}

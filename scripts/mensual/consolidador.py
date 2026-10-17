import json
import os
from datetime import datetime
from collections import defaultdict
from fastapi import FastAPI, HTTPException

app = FastAPI()

DIAS_SEMANA = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]

def calcular_margen(ganancia, ventas):
    if ventas > 0:
        return round((ganancia / ventas) * 100, 2)
    return 0.0

def parsear_fecha(fecha_str):
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(fecha_str, fmt)
        except ValueError:
            pass
    return datetime.min

def obtener_nombre_dia(fecha_str):
    dt = parsear_fecha(fecha_str)
    if dt != datetime.min:
        return DIAS_SEMANA[dt.weekday()]
    return "desconocido"

def obtener_dict_inv(dia):
    inv = dia.get("kpis_inventario", {})
    if isinstance(inv, dict) and "generales" in inv and isinstance(inv["generales"], dict):
        res = inv["generales"].copy()
        for k, v in inv.items():
            if k != "generales" and k not in res:
                res[k] = v
        return res
    return inv if isinstance(inv, dict) else {}

def procesar_mes(dias_json, anio_mes_filtro=None):
    if isinstance(dias_json, dict):
        dias_json = [dias_json]

    if not dias_json or not isinstance(dias_json, list):
        return {"error": "Se esperaba una lista de reportes diarios"}

    dias_validos = []
    for d in dias_json:
        if not isinstance(d, dict) or "informacion_sistema" not in d:
            continue
        fecha_str = d["informacion_sistema"].get("fecha_reporte")
        dt = parsear_fecha(fecha_str)
        if dt != datetime.min:
            dias_validos.append((dt, d))

    if not dias_validos:
        return {"error": "No se encontraron datos diarios válidos con fecha de reporte"}

    dias_validos.sort(key=lambda x: x[0])
    
    if anio_mes_filtro:
        dias_filtrados = [d for dt, d in dias_validos if dt.strftime("%Y-%m") == anio_mes_filtro]
    else:
        primer_mes = dias_validos[0][0].strftime("%Y-%m")
        dias_filtrados = [d for dt, d in dias_validos if dt.strftime("%Y-%m") == primer_mes]

    if not dias_filtrados:
        return {"error": f"No hay registros para el período especificado"}

    dias_ordenados = dias_filtrados
    dias_disponibles = len(dias_ordenados)

    fecha_inicio = dias_ordenados[0]["informacion_sistema"]["fecha_reporte"]
    fecha_fin = dias_ordenados[-1]["informacion_sistema"]["fecha_reporte"]

    ventas_totales = 0.0
    costo_total = 0.0
    ganancia_total = 0.0
    clientes_totales = 0
    facturas_totales = 0
    unidades_totales = 0.0

    desglose_origen = {
        "elaborado": {"ventas_usd": 0.0, "costo_usd": 0.0, "ganancia_usd": 0.0, "unidades": 0.0},
        "reventa": {"ventas_usd": 0.0, "costo_usd": 0.0, "ganancia_usd": 0.0, "unidades": 0.0}
    }

    categorias_dict = {}
    productos_dict = {}
    semanas_dict = defaultdict(list)

    for dt, dia in sorted([(parsear_fecha(d["informacion_sistema"]["fecha_reporte"]), d) for d in dias_ordenados], key=lambda x: x[0]):
        anio_iso, num_semana, _ = dt.isocalendar()
        semanas_dict[(anio_iso, num_semana)].append((dt, dia))

        fin = dia.get("kpis_financieros", {})
        v_dia = fin.get("venta_total_usd") or 0.0
        c_dia = fin.get("costo_de_ventas_usd") or 0.0
        g_dia = fin.get("ganancia_real_usd") or 0.0
        cli_dia = fin.get("total_clientes") or 0
        fac_dia = fin.get("total_facturas") or 0
        u_dia = fin.get("unidades_vendidas") or fin.get("articulos_vendidos") or 0.0

        ventas_totales += v_dia
        costo_total += c_dia
        ganancia_total += g_dia
        clientes_totales += cli_dia
        facturas_totales += fac_dia
        unidades_totales += u_dia

        desglose_dia = fin.get("desglose_origen", {})
        for origen in ["elaborado", "reventa"]:
            if origen in desglose_dia:
                desglose_origen[origen]["ventas_usd"] += desglose_dia[origen].get("ventas_usd") or 0.0
                desglose_origen[origen]["costo_usd"] += desglose_dia[origen].get("costo_usd") or 0.0
                desglose_origen[origen]["ganancia_usd"] += desglose_dia[origen].get("ganancia_usd") or 0.0
                desglose_origen[origen]["unidades"] += (
                    desglose_dia[origen].get("unidades_vendidas")
                    or desglose_dia[origen].get("unidades")
                    or 0.0
                )

        for cat in dia.get("categorias", []):
            nombre = cat.get("categoria", "Sin categoría")
            if nombre not in categorias_dict:
                categorias_dict[nombre] = {
                    "categoria": nombre,
                    "ventas_usd": 0.0,
                    "costo_usd": 0.0,
                    "ganancia_usd": 0.0,
                    "unidades_vendidas": 0.0,
                    "dias_presente": 0
                }
            categorias_dict[nombre]["ventas_usd"] += cat.get("ventas_usd") or 0.0
            categorias_dict[nombre]["costo_usd"] += cat.get("costo_usd") or 0.0
            categorias_dict[nombre]["ganancia_usd"] += cat.get("ganancia_usd") or 0.0
            categorias_dict[nombre]["unidades_vendidas"] += cat.get("unidades_vendidas") or cat.get("cantidad_vendida") or 0.0
            categorias_dict[nombre]["dias_presente"] += 1

        for prod in dia.get("tabla_mix", []):
            codigo = str(prod.get("codigo_articulo", "")).strip()
            tipo_origen = prod.get("tipo_origen") or prod.get("origen") or "reventa"
            cant_vendida = prod.get("cantidad_vendida") or prod.get("unidades_vendidas") or 0.0
            
            if codigo not in productos_dict:
                productos_dict[codigo] = {
                    "codigo_articulo": codigo,
                    "nombre": prod.get("nombre", "Desconocido"),
                    "categoria": prod.get("categoria", "General"),
                    "tipo_origen": tipo_origen,
                    "ventas_usd": 0.0,
                    "costo_usd": 0.0,
                    "ganancia_usd": 0.0,
                    "unidades": 0.0,
                    "dias_vendido": 0
                }
            
            productos_dict[codigo]["ventas_usd"] += prod.get("ventas_usd") or 0.0
            productos_dict[codigo]["costo_usd"] += prod.get("costo_usd") or 0.0
            productos_dict[codigo]["ganancia_usd"] += prod.get("ganancia_usd") or 0.0
            productos_dict[codigo]["unidades"] += cant_vendida
            productos_dict[codigo]["dias_vendido"] += 1

    serie_semanal = []
    for clave_semana, dias_semana in sorted(semanas_dict.items()):
        dias_semana.sort(key=lambda x: x[0])
        f_inicio_sem = dias_semana[0][1]["informacion_sistema"]["fecha_reporte"]
        f_fin_sem = dias_semana[-1][1]["informacion_sistema"]["fecha_reporte"]
        
        v_sem = c_sem = g_sem = u_sem = 0.0
        fac_sem = cli_sem = 0
        desglose_diario = []
        
        for dt, dia in dias_semana:
            fecha = dia["informacion_sistema"]["fecha_reporte"]
            nombre_dia = obtener_nombre_dia(fecha)
            fin = dia.get("kpis_financieros", {})
            v_dia = fin.get("venta_total_usd") or 0.0
            c_dia = fin.get("costo_de_ventas_usd") or 0.0
            g_dia = fin.get("ganancia_real_usd") or 0.0
            cli_dia = fin.get("total_clientes") or 0
            fac_dia = fin.get("total_facturas") or 0
            u_dia = fin.get("unidades_vendidas") or fin.get("articulos_vendidos") or 0.0
            inv_dia = obtener_dict_inv(dia)
            
            v_sem += v_dia
            c_sem += c_dia
            g_sem += g_dia
            fac_sem += fac_dia
            cli_sem += cli_dia
            u_sem += u_dia
            
            desglose_diario.append({
                "fecha": fecha,
                "dia_semana": nombre_dia,
                "ventas_usd": round(v_dia, 2),
                "costo_usd": round(c_dia, 2),
                "ganancia_usd": round(g_dia, 2),
                "margen_porcentaje": fin.get("ganancia_real_porcentaje") or calcular_margen(g_dia, v_dia),
                "facturas": fac_dia,
                "clientes": cli_dia,
                "unidades_vendidas": round(u_dia, 2),
                "ticket_promedio_usd": fin.get("ticket_promedio_usd") or 0.0,
                "skus_activos_inventario": inv_dia.get("total_skus", 0)
            })
        
        margen_sem = calcular_margen(g_sem, v_sem)
        ticket_sem = round(v_sem / fac_sem, 2) if fac_sem > 0 else 0.0

        serie_semanal.append({
            "semana": f"Semana {clave_semana[1]} ({clave_semana[0]})",
            "fecha_inicio": f_inicio_sem,
            "fecha_fin": f_fin_sem,
            "kpis_semana": {
                "venta_total_usd": round(v_sem, 2),
                "costo_total_usd": round(c_sem, 2),
                "ganancia_total_usd": round(g_sem, 2),
                "margen_porcentaje": margen_sem,
                "total_facturas": fac_sem,
                "total_clientes": cli_sem,
                "unidades_vendidas": round(u_sem, 2),
                "ticket_promedio_usd": ticket_sem,
                "desglose_diario": desglose_diario
            }
        })

    margen_mensual = calcular_margen(ganancia_total, ventas_totales)
    ticket_promedio_mensual = round(ventas_totales / facturas_totales, 2) if facturas_totales > 0 else 0.0
    articulos_por_factura_mensual = round(unidades_totales / facturas_totales, 2) if facturas_totales > 0 else 0.0
    articulos_por_cliente_mensual = round(unidades_totales / clientes_totales, 2) if clientes_totales > 0 else 0.0

    for origen in desglose_origen:
        v_orig = desglose_origen[origen]["ventas_usd"]
        g_orig = desglose_origen[origen]["ganancia_usd"]
        desglose_origen[origen]["ventas_usd"] = round(v_orig, 2)
        desglose_origen[origen]["costo_usd"] = round(desglose_origen[origen]["costo_usd"], 2)
        desglose_origen[origen]["ganancia_usd"] = round(g_orig, 2)
        desglose_origen[origen]["unidades"] = round(desglose_origen[origen]["unidades"], 2)
        desglose_origen[origen]["margen_porcentaje"] = calcular_margen(g_orig, v_orig)

    lista_categorias = []
    for nombre, datos in categorias_dict.items():
        datos["margen_porcentaje"] = calcular_margen(datos["ganancia_usd"], datos["ventas_usd"])
        datos["participacion_porcentaje"] = round((datos["ventas_usd"] / ventas_totales) * 100, 2) if ventas_totales > 0 else 0.0
        datos["ventas_usd"] = round(datos["ventas_usd"], 2)
        datos["costo_usd"] = round(datos["costo_usd"], 2)
        datos["ganancia_usd"] = round(datos["ganancia_usd"], 2)
        datos["unidades_vendidas"] = round(datos["unidades_vendidas"], 2)
        lista_categorias.append(datos)
    
    lista_categorias.sort(key=lambda x: x["ventas_usd"], reverse=True)

    lista_productos = list(productos_dict.values())
    for p in lista_productos:
        p["margen_porcentaje"] = calcular_margen(p["ganancia_usd"], p["ventas_usd"])
        p["participacion_porcentaje"] = round((p["ventas_usd"] / ventas_totales) * 100, 2) if ventas_totales > 0 else 0.0
        p["promedio_diario_unidades"] = round(p["unidades"] / dias_disponibles, 2)
        p["ventas_usd"] = round(p["ventas_usd"], 2)
        p["costo_usd"] = round(p["costo_usd"], 2)
        p["ganancia_usd"] = round(p["ganancia_usd"], 2)
        p["unidades"] = round(p["unidades"], 2)

    top_vendidos = sorted(lista_productos, key=lambda x: x["unidades"], reverse=True)[:5]
    top_rentables = sorted(lista_productos, key=lambda x: x["ganancia_usd"], reverse=True)[:5]

    ultimo_dia_dict = dias_ordenados[-1]
    inv_final_det = obtener_dict_inv(ultimo_dia_dict)
    val_econ_final = ultimo_dia_dict.get("valor_economico_inventario", {})

    skus_vendidos_set = set(p["codigo_articulo"] for p in lista_productos)
    raw_skus_sin_venta = inv_final_det.get("skus_sin_venta", [])
    
    processed_sin_venta = []
    for sku in raw_skus_sin_venta:
        cod = str(sku.get("codigo_articulo", "")).strip()
        if cod not in skus_vendidos_set:
            nom = sku.get("nombre", "")
            stk = sku.get("stock") or 0.0
            c_un = sku.get("costo_unidad_usd") or 0.0
            p_un = sku.get("precio_venta_usd") or 0.0
            cap_costo = round(stk * c_un, 2)
            cap_venta = round(stk * p_un, 2)

            processed_sin_venta.append({
                "codigo_articulo": cod,
                "nombre": nom,
                "stock": stk,
                "costo_unidad_usd": c_un,
                "precio_venta_usd": p_un,
                "capital_estancado_costo_usd": cap_costo,
                "capital_estancado_venta_usd": cap_venta
            })

    top_sin_ventas = sorted(
        processed_sin_venta,
        key=lambda x: (x["capital_estancado_costo_usd"], x["stock"]),
        reverse=True
    )[:5]

    primer_dia_dict = dias_ordenados[0]
    inv_inicial_det = obtener_dict_inv(primer_dia_dict)
    val_econ_inicial = primer_dia_dict.get("valor_economico_inventario", {})

    inventario_consolidado = {
        "inventario_inicial": {
            "fecha": primer_dia_dict.get("informacion_sistema", {}).get("fecha_reporte") or fecha_inicio,
            "total_skus": inv_inicial_det.get("total_skus", 0),
            "total_unidades": inv_inicial_det.get("total_unidades", 0.0),
            "valor_costo_usd": val_econ_inicial.get("valor_costo_total_usd") or inv_inicial_det.get("valor_inventario_usd", 0.0),
            "valor_potencial_usd": val_econ_inicial.get("valor_potencial_total_usd", 0.0)
        },
        "inventario_final": {
            "fecha": fecha_fin,
            "total_skus": inv_final_det.get("total_skus", 0),
            "total_unidades": inv_final_det.get("total_unidades", 0.0),
            "valor_costo_usd": val_econ_final.get("valor_costo_total_usd") or inv_final_det.get("valor_inventario_usd", 0.0),
            "valor_potencial_usd": val_econ_final.get("valor_potencial_total_usd", 0.0),
            "ganancia_proyectada_usd": val_econ_final.get("ganancia_proyectada_usd", 0.0),
            "salud_inventario_porcentaje": inv_final_det.get("salud_del_inventario") or inv_final_det.get("salud_inventario") or 100.0,
            "valor_en_riesgo_usd": inv_final_det.get("valor_en_riesgo_usd") or inv_final_det.get("valor_en_riesgo") or 0.0,
            "valor_vencido_usd": inv_final_det.get("valor_vencido_usd") or inv_final_det.get("valor_vencido") or 0.0
        }
    }

    return {
        "kpis_mes": {
            "periodo": {
                "fecha_inicio": fecha_inicio,
                "fecha_fin": fecha_fin,
                "dias_disponibles": dias_disponibles,
                "cobertura_completa": dias_disponibles >= 28
            },
            "kpis_financieros": {
                "venta_total_usd": round(ventas_totales, 2),
                "costo_total_usd": round(costo_total, 2),
                "ganancia_total_usd": round(ganancia_total, 2),
                "margen_mensual_porcentaje": margen_mensual,
                "total_facturas": facturas_totales,
                "total_clientes": clientes_totales,
                "ticket_promedio_usd": ticket_promedio_mensual,
                "articulos_por_factura": articulos_por_factura_mensual,
                "articulos_por_cliente": articulos_por_cliente_mensual,
                "unidades_totales_vendidas": round(unidades_totales, 2),
                "desglose_origen": desglose_origen
            },
            "kpis_inventario": {
                "mermas_totales_unidades": round(sum([obtener_dict_inv(d).get("mermas_detectadas_unidades", 0.0) for d in dias_ordenados]), 2),
                "mermas_totales_usd": round(sum([obtener_dict_inv(d).get("mermas_detectadas_usd", 0.0) for d in dias_ordenados]), 2)
            },
            "valor_economico_inventario": inventario_consolidado,
            "categorias": lista_categorias,
            "rankings": {
                "productos_mas_vendidos": [{"codigo": p["codigo_articulo"], "nombre": p["nombre"], "unidades": p["unidades"]} for p in top_vendidos],
                "productos_mayor_ganancia": [{"codigo": p["codigo_articulo"], "nombre": p["nombre"], "ganancia_usd": p["ganancia_usd"]} for p in top_rentables],
                "productos_sin_ventas_capital_estancado": top_sin_ventas
            },
            "serie_semanal": serie_semanal
        }
    }


@app.post("/")
async def endpoint_consolidador(payload: dict):
    """
    Endpoint FastAPI que acepta directamente los datos de KPIs (lista o diccionario)
    enviados desde Make.com, idéntico al flujo local.
    """
    try:
        # Acepta directamente el payload si es la lista o busca la clave común de entrada
        datos_entrada = payload.get("dias_json", payload) if isinstance(payload, dict) else payload

        resultado = procesar_mes(datos_entrada)
        
        if isinstance(resultado, dict) and "error" in resultado:
            raise HTTPException(status_code=400, detail=resultado["error"])

        return resultado

    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

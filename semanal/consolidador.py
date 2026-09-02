import os
from datetime import datetime
from fastapi import FastAPI, HTTPException, Request
import uvicorn

app = FastAPI()

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

def procesar_semana(dias_json):
    if not dias_json or not isinstance(dias_json, list):
        return {"error": "Se esperaba una lista de reportes diarios"}

    dias_ordenados = sorted(
        [d for d in dias_json if "informacion_sistema" in d],
        key=lambda x: parsear_fecha(x["informacion_sistema"]["fecha_reporte"])
    )
    
    dias_disponibles = len(dias_ordenados)
    if dias_disponibles == 0:
        return {"error": "No se encontraron datos diarios válidos"}

    fecha_inicio = dias_ordenados[0]["informacion_sistema"]["fecha_reporte"]
    fecha_fin = dias_ordenados[-1]["informacion_sistema"]["fecha_reporte"]

    ventas_totales = 0.0
    costo_total = 0.0
    ganancia_total = 0.0
    clientes_totales = 0
    facturas_totales = 0
    unidades_totales = 0.0
    
    evolucion_diaria = []
    categorias_dict = {}
    productos_dict = {}
    
    bloques = {
        "mañana": {"ventas": 0.0, "facturas": 0, "productos": {}}, 
        "tarde": {"ventas": 0.0, "facturas": 0, "productos": {}}, 
        "noche": {"ventas": 0.0, "facturas": 0, "productos": {}}
    }

    for dia in dias_ordenados:
        fecha = dia["informacion_sistema"]["fecha_reporte"]
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
        
        evolucion_diaria.append({
            "fecha": fecha,
            "ventas_usd": round(v_dia, 2),
            "facturas": fac_dia,
            "ticket_promedio": fin.get("ticket_promedio_usd") or 0.0
        })

        for cat in dia.get("categorias", []):
            nombre = cat.get("categoria", "Sin categoría")
            if nombre not in categorias_dict:
                categorias_dict[nombre] = {
                    "ventas_usd": 0.0, 
                    "costo_usd": 0.0, 
                    "ganancia_usd": 0.0, 
                    "unidades": 0.0, 
                    "dias_presente": 0
                }
            
            categorias_dict[nombre]["ventas_usd"] += cat.get("ventas_usd") or 0.0
            categorias_dict[nombre]["costo_usd"] += cat.get("costo_usd") or 0.0
            categorias_dict[nombre]["ganancia_usd"] += cat.get("ganancia_usd") or 0.0
            categorias_dict[nombre]["unidades"] += cat.get("unidades_vendidas") or cat.get("cantidad_vendida") or 0.0
            categorias_dict[nombre]["dias_presente"] += 1

        for prod in dia.get("tabla_mix", []):
            codigo = str(prod.get("codigo_articulo", "")).strip()
            if codigo not in productos_dict:
                productos_dict[codigo] = {
                    "codigo_articulo": codigo,
                    "nombre": prod.get("nombre", "Desconocido"),
                    "categoria": prod.get("categoria", "General"),
                    "ventas_usd": 0.0, 
                    "costo_usd": 0.0, 
                    "ganancia_usd": 0.0, 
                    "unidades": 0.0, 
                    "dias_vendido": 0
                }
            
            productos_dict[codigo]["ventas_usd"] += prod.get("ventas_usd") or 0.0
            productos_dict[codigo]["costo_usd"] += prod.get("costo_usd") or 0.0
            productos_dict[codigo]["ganancia_usd"] += prod.get("ganancia_usd") or 0.0
            productos_dict[codigo]["unidades"] += prod.get("cantidad_vendida") or prod.get("unidades_vendidas") or 0.0
            productos_dict[codigo]["dias_vendido"] += 1

        temp = dia.get("comportamiento_temporal", {})
        for turno in ["mañana", "tarde", "noche"]:
            if turno in temp:
                bloques[turno]["ventas"] += temp[turno].get("ventas_usd") or 0.0
                bloques[turno]["facturas"] += temp[turno].get("cantidad_facturas") or 0
                
                prods_turno = temp[turno].get("articulos") or temp[turno].get("productos") or temp[turno].get("top_productos", [])
                for p in prods_turno:
                    cod = str(p.get("codigo_articulo") or p.get("codigo") or p.get("nombre", "")).strip()
                    nom = p.get("nombre", cod)
                    cant = p.get("unidades") or p.get("cantidad") or p.get("cantidad_vendida") or 0.0
                    if cod not in bloques[turno]["productos"]:
                        bloques[turno]["productos"][cod] = {"nombre": nom, "unidades": 0.0}
                    bloques[turno]["productos"][cod]["unidades"] += cant

    margen_semanal = calcular_margen(ganancia_total, ventas_totales)
    ticket_promedio_semanal = round(ventas_totales / facturas_totales, 2) if facturas_totales > 0 else 0.0
    articulos_por_factura_semanal = round(unidades_totales / facturas_totales, 2) if facturas_totales > 0 else 0.0
    
    dia_max = max(evolucion_diaria, key=lambda x: x["ventas_usd"])
    dia_min = min(evolucion_diaria, key=lambda x: x["ventas_usd"])
    hitos_semanales = {
        "mejor_dia": {"fecha": dia_max["fecha"], "ventas_usd": round(dia_max["ventas_usd"], 2)},
        "peor_dia": {"fecha": dia_min["fecha"], "ventas_usd": round(dia_min["ventas_usd"], 2)}
    }

    lista_categorias = []
    for nombre, datos in categorias_dict.items():
        datos["margen_porcentaje"] = calcular_margen(datos["ganancia_usd"], datos["ventas_usd"])
        datos["participacion_porcentaje"] = round((datos["ventas_usd"] / ventas_totales) * 100, 2) if ventas_totales > 0 else 0.0
        datos["categoria"] = nombre
        lista_categorias.append(datos)
    
    lista_categorias.sort(key=lambda x: x["ventas_usd"], reverse=True)

    lista_productos = list(productos_dict.values())
    for p in lista_productos:
        p["margen_porcentaje"] = calcular_margen(p["ganancia_usd"], p["ventas_usd"])
        p["participacion_porcentaje"] = round((p["ventas_usd"] / ventas_totales) * 100, 2) if ventas_totales > 0 else 0.0

    top_vendidos = sorted(lista_productos, key=lambda x: x["unidades"], reverse=True)[:5]
    top_facturacion = sorted(lista_productos, key=lambda x: x["ventas_usd"], reverse=True)[:5]
    top_rentables = sorted(lista_productos, key=lambda x: x["ganancia_usd"], reverse=True)[:5]
    top_baja_rotacion = sorted(lista_productos, key=lambda x: x["unidades"])[:5]

    ventas_top_5 = sum([p["ventas_usd"] for p in top_facturacion])
    concentracion_top_5 = round((ventas_top_5 / ventas_totales) * 100, 2) if ventas_totales > 0 else 0.0

    comportamiento_temporal_final = {}
    for turno in bloques:
        f_turno = bloques[turno]["facturas"]
        t_prom = round(bloques[turno]["ventas"] / f_turno, 2) if f_turno > 0 else 0.0
        
        prods_turno_list = list(bloques[turno]["productos"].values())
        top_5_turno = sorted(prods_turno_list, key=lambda x: x["unidades"], reverse=True)[:5]
        
        comportamiento_temporal_final[turno] = {
            "ventas": round(bloques[turno]["ventas"], 2),
            "facturas": f_turno,
            "ticket_promedio": t_prom,
            "top_productos": [{"nombre": p["nombre"], "unidades": round(p["unidades"], 2)} for p in top_5_turno]
        }

    inv_inicial = dias_ordenados[0].get("kpis_inventario", {})
    inv_final = dias_ordenados[-1].get("kpis_inventario", {})
    
    mermas_totales_unidades = sum([(d.get("kpis_inventario", {}).get("mermas_detectadas_unidades") or 0.0) for d in dias_ordenados])
    mermas_totales_usd = sum([(d.get("kpis_inventario", {}).get("mermas_detectadas_usd") or 0.0) for d in dias_ordenados])

    raw_skus_sin_venta = inv_final.get("skus_sin_venta", [])
    processed_sin_venta = []
    for sku in raw_skus_sin_venta:
        cod = str(sku.get("codigo_articulo", "")).strip()
        nom = sku.get("nombre", "")
        stk = sku.get("stock") or 0.0
        c_un = sku.get("costo_unidad_usd") or 0.0
        p_un = sku.get("precio_venta_usd") or 0.0

        cap_costo = round(stk * c_un, 2)
        cap_venta = round(stk * p_un, 2)

        processed_sin_venta.append({
            "codigo": cod,
            "nombre": nom,
            "stock": stk,
            "costo_unidad_usd": c_un,
            "precio_venta_usd": p_un,
            "capital_estancado_costo_usd": cap_costo,
            "capital_estancado_venta_usd": cap_venta
        })

    top_skus_sin_venta = sorted(
        processed_sin_venta,
        key=lambda x: (x["capital_estancado_costo_usd"], x["capital_estancado_venta_usd"], x["stock"]),
        reverse=True
    )[:5]

    total_cap_estancado_costo = round(sum(p["capital_estancado_costo_usd"] for p in processed_sin_venta), 2)
    total_cap_estancado_venta = round(sum(p["capital_estancado_venta_usd"] for p in processed_sin_venta), 2)

    afinidades = [d.get("afinidad_productos") for d in dias_ordenados if d.get("afinidad_productos") and d.get("afinidad_productos") != "No se detectaron patrones de frecuencia de compra"]
    resultado_afinidad = afinidades if afinidades else "No se detectaron patrones de frecuencia de compra"

    return {
        "periodo": {
            "fecha_inicio": fecha_inicio,
            "fecha_fin": fecha_fin,
            "dias_disponibles": dias_disponibles
        },
        "kpis_semanales": {
            "venta_total_usd": round(ventas_totales, 2),
            "costo_total_usd": round(costo_total, 2),
            "ganancia_total_usd": round(ganancia_total, 2),
            "margen_semanal_porcentaje": margen_semanal,
            "total_facturas": facturas_totales,
            "total_clientes": clientes_totales,
            "ticket_promedio_usd": ticket_promedio_semanal,
            "articulos_por_factura": articulos_por_factura_semanal,
            "unidades_totales_vendidas": round(unidades_totales, 2)
        },
        "hitos_semanales": hitos_semanales,
        "evolucion_diaria": evolucion_diaria,
        "inventario": {
            "unidades_inicio_semana": inv_inicial.get("total_unidades") or 0.0,
            "unidades_fin_semana": inv_final.get("total_unidades") or 0.0,
            "skus_activos_fin_semana": inv_final.get("total_skus") or 0,
            "salud_inventario_porcentaje": inv_final.get("salud_del_inventario") or inv_final.get("salud_inventario") or 100.0,
            "mermas_totales_unidades": round(mermas_totales_unidades, 2),
            "mermas_totales_usd": round(mermas_totales_usd, 2),
            "valor_en_riesgo_usd": inv_final.get("valor_en_riesgo") or 0.0,
            "valor_vencido_usd": inv_final.get("valor_vencido") or 0.0,
            "capital_estancado_total_costo_usd": total_cap_estancado_costo,
            "capital_estancado_total_venta_usd": total_cap_estancado_venta
        },
        "categorias": lista_categorias,
        "top_vendidos": [{"codigo": p["codigo_articulo"], "nombre": p["nombre"], "unidades": p["unidades"]} for p in top_vendidos],
        "top_facturacion": [{"codigo": p["codigo_articulo"], "nombre": p["nombre"], "ventas_usd": round(p["ventas_usd"], 2)} for p in top_facturacion],
        "top_rentables": [{"codigo": p["codigo_articulo"], "nombre": p["nombre"], "ganancia_usd": round(p["ganancia_usd"], 2)} for p in top_rentables],
        "top_baja_rotacion": [{"codigo": p["codigo_articulo"], "nombre": p["nombre"], "unidades": p["unidades"]} for p in top_baja_rotacion],
        "top_skus_sin_venta": top_skus_sin_venta,
        "consistencia_productos": [{"codigo": p["codigo_articulo"], "nombre": p["nombre"], "dias_vendido": p["dias_vendido"]} for p in lista_productos],
        "comportamiento_temporal": comportamiento_temporal_final,
        "concentracion": {
            "participacion_top5_porcentaje": concentracion_top_5
        },
        "afinidad_productos": resultado_afinidad
    }

@app.post("/procesar-semana")
async def webhook_procesar_semana(request: Request):
    try:
        payload = await request.json()
        if not payload:
            raise HTTPException(status_code=400, detail="Payload JSON no válido o vacío")

        if isinstance(payload, dict) and "dias" in payload:
            dias_json = payload["dias"]
        elif isinstance(payload, list):
            dias_json = payload
        else:
            raise HTTPException(status_code=400, detail="Formato inválido. Enviar lista o JSON con clave 'dias'")

        resultado = procesar_semana(dias_json)
        if "error" in resultado:
            raise HTTPException(status_code=400, detail=resultado["error"])

        return resultado

    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"Error procesando la solicitud: {str(e)}")

@app.get("/")
def health_check():
    return {"status": "ok", "mensaje": "Servidor activo"}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)

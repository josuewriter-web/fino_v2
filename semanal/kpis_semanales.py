import json
from datetime import datetime
from flask import Flask, request, jsonify

app = Flask(__name__)

def calcular_margen(ganancia, ventas):
    if ventas > 0:
        return round((ganancia / ventas) * 100, 2)
    return 0.0

def procesar_semana(dias_json):
    if not dias_json or not isinstance(dias_json, list):
        return {"error": "Se esperaba una lista de reportes diarios"}

    # 1. Ordenar por fecha
    dias_ordenados = sorted(
        [d for d in dias_json if "informacion_sistema" in d],
        key=lambda x: datetime.strptime(x["informacion_sistema"]["fecha_reporte"], "%d/%m/%Y")
    )
    
    dias_disponibles = len(dias_ordenados)
    if dias_disponibles == 0:
        return {"error": "No se encontraron datos diarios válidos"}

    fecha_inicio = dias_ordenados[0]["informacion_sistema"]["fecha_reporte"]
    fecha_fin = dias_ordenados[-1]["informacion_sistema"]["fecha_reporte"]

    # --- INICIALIZAR VARIABLES ---
    ventas_totales = 0.0
    costo_total = 0.0
    ganancia_total = 0.0
    clientes_totales = 0
    facturas_totales = 0
    unidades_totales = 0.0
    
    evolucion_diaria = []
    categorias_dict = {}
    productos_dict = {}
    skus_sin_venta_semanal_dict = {}
    
    bloques = {
        "mañana": {"ventas": 0.0, "facturas": 0, "productos": {}}, 
        "tarde": {"ventas": 0.0, "facturas": 0, "productos": {}}, 
        "noche": {"ventas": 0.0, "facturas": 0, "productos": {}}
    }

    # --- PROCESAMIENTO DIARIO ---
    for dia in dias_ordenados:
        fecha = dia["informacion_sistema"]["fecha_reporte"]
        fin = dia.get("kpis_financieros", {})
        
        # Sumar métricas acumulables
        ventas_totales += fin.get("venta_total_usd", 0)
        costo_total += fin.get("costo_de_ventas_usd", 0)
        ganancia_total += fin.get("ganancia_real_usd", 0)
        clientes_totales += fin.get("total_clientes", 0)
        facturas_totales += fin.get("total_facturas", 0)
        unidades_totales += fin.get("unidades_vendidas", 0)
        
        # Guardar evolución diaria
        evolucion_diaria.append({
            "fecha": fecha,
            "ventas_usd": fin.get("venta_total_usd", 0),
            "facturas": fin.get("total_facturas", 0),
            "ticket_promedio": fin.get("ticket_promedio_usd", 0)
        })

        # Procesar Categorías
        for cat in dia.get("categorias", []):
            nombre = cat["categoria"]
            if nombre not in categorias_dict:
                categorias_dict[nombre] = {
                    "ventas_usd": 0.0, 
                    "costo_usd": 0.0, 
                    "ganancia_usd": 0.0, 
                    "unidades": 0.0, 
                    "dias_presente": 0
                }
            
            categorias_dict[nombre]["ventas_usd"] += cat.get("ventas_usd", 0)
            categorias_dict[nombre]["costo_usd"] += cat.get("costo_usd", 0)
            categorias_dict[nombre]["ganancia_usd"] += cat.get("ganancia_usd", 0)
            categorias_dict[nombre]["unidades"] += cat.get("unidades_vendidas", 0)
            categorias_dict[nombre]["dias_presente"] += 1

        # Procesar Productos (tabla_mix)
        for prod in dia.get("tabla_mix", []):
            codigo = str(prod["codigo_articulo"]).strip()
            if codigo not in productos_dict:
                productos_dict[codigo] = {
                    "codigo_articulo": codigo,
                    "nombre": prod["nombre"],
                    "categoria": prod["categoria"],
                    "ventas_usd": 0.0, 
                    "costo_usd": 0.0, 
                    "ganancia_usd": 0.0, 
                    "unidades": 0.0, 
                    "dias_vendido": 0
                }
            
            productos_dict[codigo]["ventas_usd"] += prod.get("ventas_usd", 0)
            productos_dict[codigo]["costo_usd"] += prod.get("costo_usd", 0)
            productos_dict[codigo]["ganancia_usd"] += prod.get("ganancia_usd", 0)
            productos_dict[codigo]["unidades"] += prod.get("cantidad_vendida", 0)
            productos_dict[codigo]["dias_vendido"] += 1

        # Registrar SKUs que no vendieron en el día (desde kpis_inventario)
        inv_dia = dia.get("kpis_inventario", {})
        for sku in inv_dia.get("skus_sin_venta", []):
            cod = str(sku.get("codigo_articulo")).strip()
            nom = sku.get("nombre", "")
            if cod not in skus_sin_venta_semanal_dict:
                skus_sin_venta_semanal_dict[cod] = {"codigo": cod, "nombre": nom, "dias_sin_venta": 0}
            skus_sin_venta_semanal_dict[cod]["dias_sin_venta"] += 1

        # Procesar Bloques Temporales y Productos por Turno
        temp = dia.get("comportamiento_temporal", {})
        for turno in ["mañana", "tarde", "noche"]:
            if turno in temp:
                bloques[turno]["ventas"] += temp[turno].get("ventas_usd", 0)
                bloques[turno]["facturas"] += temp[turno].get("cantidad_facturas", 0)
                
                prods_turno = temp[turno].get("articulos") or temp[turno].get("productos") or temp[turno].get("top_productos", [])
                for p in prods_turno:
                    cod = str(p.get("codigo_articulo") or p.get("codigo") or p.get("nombre")).strip()
                    nom = p.get("nombre", cod)
                    cant = p.get("unidades") or p.get("cantidad") or p.get("cantidad_vendida", 0)
                    if cod not in bloques[turno]["productos"]:
                        bloques[turno]["productos"][cod] = {"nombre": nom, "unidades": 0}
                    bloques[turno]["productos"][cod]["unidades"] += cant

    # --- RECÁLCULOS SEMANALES ---
    margen_semanal = calcular_margen(ganancia_total, ventas_totales)
    ticket_promedio_semanal = round(ventas_totales / facturas_totales, 2) if facturas_totales > 0 else 0
    articulos_por_factura_semanal = round(unidades_totales / facturas_totales, 2) if facturas_totales > 0 else 0
    
    # Identificar Mejor y Peor Día (Hitos)
    dia_max = max(evolucion_diaria, key=lambda x: x["ventas_usd"])
    dia_min = min(evolucion_diaria, key=lambda x: x["ventas_usd"])
    hitos_semanales = {
        "mejor_dia": {"fecha": dia_max["fecha"], "ventas_usd": round(dia_max["ventas_usd"], 2)},
        "peor_dia": {"fecha": dia_min["fecha"], "ventas_usd": round(dia_min["ventas_usd"], 2)}
    }

    # Formatear Categorías
    lista_categorias = []
    for nombre, datos in categorias_dict.items():
        datos["margen_porcentaje"] = calcular_margen(datos["ganancia_usd"], datos["ventas_usd"])
        datos["participacion_porcentaje"] = round((datos["ventas_usd"] / ventas_totales) * 100, 2) if ventas_totales > 0 else 0
        datos["categoria"] = nombre
        lista_categorias.append(datos)
    
    lista_categorias.sort(key=lambda x: x["ventas_usd"], reverse=True)

    # Formatear Productos y Rankings
    lista_productos = list(productos_dict.values())
    for p in lista_productos:
        p["margen_porcentaje"] = calcular_margen(p["ganancia_usd"], p["ventas_usd"])
        p["participacion_porcentaje"] = round((p["ventas_usd"] / ventas_totales) * 100, 2) if ventas_totales > 0 else 0

    top_vendidos = sorted(lista_productos, key=lambda x: x["unidades"], reverse=True)[:10]
    top_facturacion = sorted(lista_productos, key=lambda x: x["ventas_usd"], reverse=True)[:10]
    top_rentables = sorted(lista_productos, key=lambda x: x["ganancia_usd"], reverse=True)[:10]
    
    # Ranking de Baja Rotación (Top 5 menos vendidos)
    top_baja_rotacion = sorted(lista_productos, key=lambda x: x["unidades"])[:5]

    # SKUs sin rotación (0 ventas durante TODOS los días procesados)
    skus_sin_rotacion = [
        {"codigo": item["codigo"], "nombre": item["nombre"]}
        for cod, item in skus_sin_venta_semanal_dict.items()
        if item["dias_sin_venta"] == dias_disponibles and productos_dict.get(cod, {}).get("unidades", 0) == 0
    ]

    ventas_top_10 = sum([p["ventas_usd"] for p in top_facturacion])
    concentracion_top_10 = round((ventas_top_10 / ventas_totales) * 100, 2) if ventas_totales > 0 else 0

    # Comportamiento Temporal Recalculado con Top 5 Productos por Turno
    comportamiento_temporal_final = {}
    for turno in bloques:
        f_turno = bloques[turno]["facturas"]
        t_prom = round(bloques[turno]["ventas"] / f_turno, 2) if f_turno > 0 else 0
        
        prods_turno_list = list(bloques[turno]["productos"].values())
        top_5_turno = sorted(prods_turno_list, key=lambda x: x["unidades"], reverse=True)[:5]
        
        comportamiento_temporal_final[turno] = {
            "ventas": round(bloques[turno]["ventas"], 2),
            "facturas": f_turno,
            "ticket_promedio": t_prom,
            "top_productos": [{"nombre": p["nombre"], "unidades": round(p["unidades"], 2)} for p in top_5_turno]
        }

    # Consolidación de Inventario y Mermas
    inv_inicial = dias_ordenados[0].get("kpis_inventario", {})
    inv_final = dias_ordenados[-1].get("kpis_inventario", {})
    mermas_totales = sum([d.get("kpis_inventario", {}).get("mermas_detectadas_unidades", 0) for d in dias_ordenados])

    # Afinidades
    afinidades = [d.get("afinidad_productos") for d in dias_ordenados if d.get("afinidad_productos") != "No se detectaron patrones de frecuencia de compra"]
    resultado_afinidad = afinidades if afinidades else "No se detectaron patrones de frecuencia de compra"

    # --- ESTRUCTURA DE SALIDA ---
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
            "ticket_promedio_usd": ticket_promedio_semanal,
            "articulos_por_factura": articulos_por_factura_semanal,
            "unidades_totales_vendidas": round(unidades_totales, 2)
        },
        "hitos_semanales": hitos_semanales,
        "evolucion_diaria": evolucion_diaria,
        "inventario": {
            "unidades_inicio_semana": inv_inicial.get("total_unidades", 0),
            "unidades_fin_semana": inv_final.get("total_unidades", 0),
            "skus_activos_fin_semana": inv_final.get("total_skus", 0),
            "salud_inventario_porcentaje": inv_final.get("salud_del_inventario", 100.0),
            "mermas_totales_unidades": round(mermas_totales, 2),
            "valor_en_riesgo_usd": inv_final.get("valor_en_riesgo", 0.0),
            "valor_vencido_usd": inv_final.get("valor_vencido", 0.0)
        },
        "categorias": lista_categorias,
        "top_vendidos": [{"codigo": p["codigo_articulo"], "nombre": p["nombre"], "unidades": p["unidades"]} for p in top_vendidos],
        "top_facturacion": [{"codigo": p["codigo_articulo"], "nombre": p["nombre"], "ventas_usd": round(p["ventas_usd"], 2)} for p in top_facturacion],
        "top_rentables": [{"codigo": p["codigo_articulo"], "nombre": p["nombre"], "ganancia_usd": round(p["ganancia_usd"], 2)} for p in top_rentables],
        "top_baja_rotacion": [{"codigo": p["codigo_articulo"], "nombre": p["nombre"], "unidades": p["unidades"]} for p in top_baja_rotacion],
        "skus_sin_rotacion": skus_sin_rotacion,
        "consistencia_productos": [{"codigo": p["codigo_articulo"], "nombre": p["nombre"], "dias_vendido": p["dias_vendido"]} for p in lista_productos],
        "comportamiento_temporal": comportamiento_temporal_final,
        "concentracion": {
            "participacion_top10_porcentaje": concentracion_top_10
        },
        "afinidad_productos": resultado_afinidad
    }

# Endpoint para Make
@app.route("/procesar-semana", methods=["POST"])
def endpoint_semanal():
    datos = request.get_json()
    if not datos:
        return jsonify({"error": "No se recibió cuerpo JSON"}), 400
    
    if isinstance(datos, dict) and "dias" in datos:
        lista_dias = datos["dias"]
    elif isinstance(datos, list):
        lista_dias = datos
    else:
        return jsonify({"error": "Formato de datos no compatible"}), 400

    resultado = procesar_semana(lista_dias)
    return jsonify(resultado), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

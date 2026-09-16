import json
from datetime import datetime

def normalizar_memoria(memoria):
    if not memoria:
        return {}

    while isinstance(memoria, str):
        memoria = memoria.strip()
        if not memoria:
            return {}
        try:
            memoria = json.loads(memoria)
        except Exception:
            return {}

    if not isinstance(memoria, (dict, list)):
        return {}

    if isinstance(memoria, dict):
        if "inventario_actualizado" in memoria and isinstance(memoria["inventario_actualizado"], (dict, list)):
            memoria = memoria["inventario_actualizado"]
        elif "memoria" in memoria and isinstance(memoria["memoria"], (dict, list)):
            memoria = memoria["memoria"]

    if isinstance(memoria, list):
        res = {}
        for item in memoria:
            if isinstance(item, dict):
                codigo = str(item.get("codigo_articulo", "")).strip()
                if codigo:
                    res[codigo] = item
        return res

    return memoria


def aplicar_fifo(lotes, cantidad_a_descontar):
    lotes.sort(key=lambda x: x.get("edad", 0), reverse=True)
    restante = cantidad_a_descontar
    
    for lote in lotes:
        if restante <= 0:
            break
        if lote["cantidad"] <= restante:
            restante = round(restante - lote["cantidad"], 2)
            lote["cantidad"] = 0
        else:
            lote["cantidad"] = round(lote["cantidad"] - restante, 2)
            restante = 0
            
    return [lote for lote in lotes if lote["cantidad"] > 0]


def ejecutar_control_inventario(inventario_hoy, ventas_hoy, memoria=None):
    FECHA_HOY = datetime.today().strftime("%Y-%m-%d")
    TIMESTAMP = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    memoria = normalizar_memoria(memoria)

    # 1. Calcular ventas de hoy
    ventas_consolidadas = {}
    for factura in ventas_hoy.get("facturas_agrupadas", []):
        for prod in factura.get("articulos", []):
            codigo = str(prod.get("codigo_articulo")).strip()
            ventas_consolidadas[codigo] = ventas_consolidadas.get(codigo, 0) + prod.get("cantidad", 0)

    inv_fisico = {str(p["codigo_articulo"]).strip(): p.get("existencia_actual", 0) for p in inventario_hoy.get("productos", [])}
    inv_costos = {str(p["codigo_articulo"]).strip(): p.get("costo_unidad_usd", 0.0) for p in inventario_hoy.get("productos", [])}

    # 2. Cargar productos a memoria preservando tipo_origen
    for prod in inventario_hoy.get("productos", []):
        codigo = str(prod.get("codigo_articulo")).strip()
        tipo_origen = prod.get("tipo_origen", "reventa")
        
        if codigo not in memoria:
            ventas_del_dia = ventas_consolidadas.get(codigo, 0)
            existencia_fisica = prod.get("existencia_actual", 0)
            
            memoria[codigo] = {
                "codigo_articulo": codigo,
                "nombre": prod.get("nombre", ""),
                "categoria": prod.get("categoria", "Sin clasificar"),
                "tipo_origen": tipo_origen,
                "dias_maximos": prod.get("dias_maximos", 180),
                "precio_unitario_usd": prod.get("precio_venta_usd", 0.0),
                "costo_unitario_usd": prod.get("costo_unidad_usd", 0.0),
                "fecha_ultima_venta": None,
                "lotes": [{
                    "fecha_ingreso": FECHA_HOY,
                    "edad": 0, 
                    "cantidad": round(existencia_fisica + ventas_del_dia, 2)
                }]
            }
        else:
            memoria[codigo]["precio_unitario_usd"] = prod.get("precio_venta_usd", 0.0)
            memoria[codigo]["costo_unitario_usd"] = prod.get("costo_unidad_usd", 0.0)
            memoria[codigo]["tipo_origen"] = tipo_origen

    # Contadores por categoría
    def crear_estructura_metricas():
        return {
            "total_skus": 0,
            "total_unidades": 0.0,
            "valor_inventario_usd": 0.0,
            "total_lotes": 0,
            "entradas_unidades": 0.0,
            "skus_con_entrada": 0,
            "mermas_unidades": 0.0,
            "mermas_usd": 0.0,
            "skus_con_merma": 0,
            "unidades_en_riesgo": 0.0,
            "valor_en_riesgo": 0.0,
            "skus_en_riesgo": 0,
            "unidades_vencidas": 0.0,
            "valor_vencido": 0.0,
            "skus_vencidos": 0,
            "skus_sin_venta": []
        }

    met_gen = crear_estructura_metricas()
    met_ela = crear_estructura_metricas()
    met_rev = crear_estructura_metricas()

    suma_edades_unidades = 0
    edad_maxima_global = 0
    sku_mas_antiguo = {"codigo_articulo": "", "nombre": "", "edad": 0}

    for codigo, datos_memoria in memoria.items():
        lotes = datos_memoria.get("lotes", [])
        dias_max = datos_memoria.get("dias_maximos", 180)
        nombre_sku = datos_memoria.get("nombre", "")
        tipo_origen = datos_memoria.get("tipo_origen", "reventa")
        
        costo_sku = inv_costos.get(codigo, datos_memoria.get("costo_unitario_usd", 0.0))
        precio_sku = datos_memoria.get("precio_unitario_usd", 0.0)
        
        # Selección de métrica específica según tipo
        met_especifica = met_ela if tipo_origen == "elaborado" else met_rev
        
        met_gen["total_skus"] += 1
        met_especifica["total_skus"] += 1

        # Ventas (FIFO)
        ventas_sku = ventas_consolidadas.get(codigo, 0)
        if ventas_sku > 0:
            datos_memoria["fecha_ultima_venta"] = FECHA_HOY
            lotes = aplicar_fifo(lotes, ventas_sku)
        
        # Entradas y Mermas
        esperado = round(sum(lote["cantidad"] for lote in lotes), 2)
        
        if codigo in inv_fisico:
            real = round(inv_fisico[codigo], 2)
            if real > esperado:
                diferencia = round(real - esperado, 2)
                lotes.append({"fecha_ingreso": FECHA_HOY, "edad": 0, "cantidad": diferencia})
                
                met_gen["entradas_unidades"] += diferencia
                met_gen["skus_con_entrada"] += 1
                met_especifica["entradas_unidades"] += diferencia
                met_especifica["skus_con_entrada"] += 1

            elif real < esperado:
                diferencia = round(esperado - real, 2)
                lotes = aplicar_fifo(lotes, diferencia)
                costo_merma = diferencia * costo_sku
                
                met_gen["mermas_unidades"] += diferencia
                met_gen["mermas_usd"] += costo_merma
                met_gen["skus_con_merma"] += 1
                
                met_especifica["mermas_unidades"] += diferencia
                met_especifica["mermas_usd"] += costo_merma
                met_especifica["skus_con_merma"] += 1

        for lote in lotes:
            lote["edad"] += 1
        
        total_sku_unidades = round(sum(l["cantidad"] for l in lotes), 2)
        valor_sku_total = round(total_sku_unidades * costo_sku, 2)

        met_gen["total_unidades"] += total_sku_unidades
        met_gen["valor_inventario_usd"] += valor_sku_total
        met_especifica["total_unidades"] += total_sku_unidades
        met_especifica["valor_inventario_usd"] += valor_sku_total

        if ventas_sku == 0 and total_sku_unidades > 0:
            item_sin_venta = {
                "codigo_articulo": codigo,
                "nombre": nombre_sku,
                "stock": total_sku_unidades,
                "costo_unidad_usd": costo_sku,
                "precio_venta_usd": precio_sku
            }
            met_gen["skus_sin_venta"].append(item_sin_venta)
            met_especifica["skus_sin_venta"].append(item_sin_venta)
        
        nombre = datos_memoria.get("nombre", "")
        categoria = datos_memoria.get("categoria", "Sin clasificar")
        fecha_venta = datos_memoria.get("fecha_ultima_venta")
        
        datos_memoria.clear()
        datos_memoria["codigo_articulo"] = codigo
        datos_memoria["nombre"] = nombre
        datos_memoria["categoria"] = categoria
        datos_memoria["tipo_origen"] = tipo_origen
        datos_memoria["existencia_total"] = total_sku_unidades
        datos_memoria["dias_maximos"] = dias_max
        datos_memoria["precio_unitario_usd"] = precio_sku
        datos_memoria["costo_unitario_usd"] = costo_sku
        datos_memoria["fecha_ultima_venta"] = fecha_venta
        datos_memoria["lotes"] = lotes
        
        met_gen["total_lotes"] += len(lotes)
        met_especifica["total_lotes"] += len(lotes)
        
        sku_tiene_riesgo = False
        sku_tiene_vencidos = False
        
        for lote in lotes:
            cant = lote["cantidad"]
            edad = lote["edad"]
            
            suma_edades_unidades += (edad * cant)
            
            if edad > edad_maxima_global:
                edad_maxima_global = edad
                sku_mas_antiguo = {
                    "codigo_articulo": codigo,
                    "nombre": nombre_sku,
                    "edad": edad
                }
                
            if edad > dias_max:
                val_venc = cant * costo_sku
                met_gen["unidades_vencidas"] += cant
                met_gen["valor_vencido"] += val_venc
                met_especifica["unidades_vencidas"] += cant
                met_especifica["valor_vencido"] += val_venc
                sku_tiene_vencidos = True

            elif edad >= (dias_max * 0.8):
                val_riesg = cant * costo_sku
                met_gen["unidades_en_riesgo"] += cant
                met_gen["valor_en_riesgo"] += val_riesg
                met_especifica["unidades_en_riesgo"] += cant
                met_especifica["valor_en_riesgo"] += val_riesg
                sku_tiene_riesgo = True
                
        if sku_tiene_riesgo:
            met_gen["skus_en_riesgo"] += 1
            met_especifica["skus_en_riesgo"] += 1
            
        if sku_tiene_vencidos:
            met_gen["skus_vencidos"] += 1
            met_especifica["skus_vencidos"] += 1

    # Cálculo de promedios globales
    tot_unid = met_gen["total_unidades"]
    edad_promedio = round(suma_edades_unidades / tot_unid, 2) if tot_unid > 0 else 0.0
    pct_riesgo = round((met_gen["unidades_en_riesgo"] / tot_unid) * 100, 2) if tot_unid > 0 else 0.0
    pct_vencidos = round((met_gen["unidades_vencidas"] / tot_unid) * 100, 2) if tot_unid > 0 else 0.0

    def formatear_bloque_kpi(m):
        return {
            "total_skus": m["total_skus"],
            "total_unidades": round(m["total_unidades"], 2),
            "valor_inventario_usd": round(m["valor_inventario_usd"], 2),
            "total_lotes": m["total_lotes"],
            "unidades_en_riesgo": round(m["unidades_en_riesgo"], 2),
            "valor_en_riesgo_usd": round(m["valor_en_riesgo"], 2),
            "cantidad_skus_en_riesgo": m["skus_en_riesgo"],
            "unidades_vencidas": round(m["unidades_vencidas"], 2),
            "valor_vencido_usd": round(m["valor_vencido"], 2),
            "cantidad_skus_vencidos": m["skus_vencidos"],
            "entradas_detectadas_unidades": round(m["entradas_unidades"], 2),
            "cantidad_skus_con_entrada": m["skus_con_entrada"],
            "mermas_detectadas_unidades": round(m["mermas_unidades"], 2),
            "mermas_detectadas_usd": round(m["mermas_usd"], 2),
            "cantidad_skus_con_merma": m["skus_con_merma"],
            "cantidad_skus_sin_venta": len(m["skus_sin_venta"]),
            "skus_sin_venta": m["skus_sin_venta"]
        }

    kpis_estructurados = {
        "fecha": FECHA_HOY,
        "timestamp": TIMESTAMP,
        "generales": {
            **formatear_bloque_kpi(met_gen),
            "edad_promedio": edad_promedio,
            "edad_maxima_inventario": edad_maxima_global,
            "porcentaje_en_riesgo": pct_riesgo,
            "porcentaje_vencidos": pct_vencidos,
            "salud_del_inventario": round(100 - pct_riesgo - pct_vencidos, 2),
            "sku_mas_antiguo": sku_mas_antiguo
        },
        "elaborado": formatear_bloque_kpi(met_ela),
        "reventa": formatear_bloque_kpi(met_rev)
    }

    return {
        "kpis": kpis_estructurados,
        "inventario_actualizado": memoria
    }

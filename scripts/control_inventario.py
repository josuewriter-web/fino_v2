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

    # 2. Cargar productos a memoria
    for prod in inventario_hoy.get("productos", []):
        codigo = str(prod.get("codigo_articulo")).strip()
        
        if codigo not in memoria:
            ventas_del_dia = ventas_consolidadas.get(codigo, 0)
            existencia_fisica = prod.get("existencia_actual", 0)
            
            memoria[codigo] = {
                "codigo_articulo": codigo,
                "nombre": prod.get("nombre", ""),
                "categoria": prod.get("categoria", "Sin clasificar"),
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

    total_unidades = 0
    total_lotes_global = 0
    total_entradas_dia = 0
    total_mermas_dia = 0
    total_mermas_usd_dia = 0.0
    suma_edades_unidades = 0
    edad_maxima_global = 0
    unidades_riesgo = 0
    unidades_vencidas = 0
    valor_en_riesgo = 0.0
    valor_vencido = 0.0
    sku_mas_antiguo = {"codigo_articulo": "", "nombre": "", "edad": 0}

    skus_en_riesgo_count = 0
    skus_vencidos_count = 0
    skus_con_entrada_count = 0
    skus_con_merma_count = 0
    skus_sin_venta_hoy = []

    for codigo, datos_memoria in memoria.items():
        lotes = datos_memoria.get("lotes", [])
        dias_max = datos_memoria.get("dias_maximos", 180)
        nombre_sku = datos_memoria.get("nombre", "")
        
        costo_sku = inv_costos.get(codigo, datos_memoria.get("costo_unitario_usd", 0.0))
        precio_sku = datos_memoria.get("precio_unitario_usd", 0.0)
        
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
                total_entradas_dia += diferencia
                skus_con_entrada_count += 1
            elif real < esperado:
                diferencia = round(esperado - real, 2)
                lotes = aplicar_fifo(lotes, diferencia)
                total_mermas_dia += diferencia
                total_mermas_usd_dia += (diferencia * costo_sku)
                skus_con_merma_count += 1

        for lote in lotes:
            lote["edad"] += 1
        
        total_sku_unidades = round(sum(l["cantidad"] for l in lotes), 2)
        total_unidades += total_sku_unidades

        if ventas_sku == 0 and total_sku_unidades > 0:
            skus_sin_venta_hoy.append({
                "codigo_articulo": codigo,
                "nombre": nombre_sku,
                "stock": total_sku_unidades,
                "costo_unidad_usd": costo_sku,
                "precio_venta_usd": precio_sku
            })
        
        nombre = datos_memoria.get("nombre", "")
        categoria = datos_memoria.get("categoria", "Sin clasificar")
        fecha_venta = datos_memoria.get("fecha_ultima_venta")
        
        datos_memoria.clear()
        datos_memoria["codigo_articulo"] = codigo
        datos_memoria["nombre"] = nombre
        datos_memoria["categoria"] = categoria
        datos_memoria["existencia_total"] = total_sku_unidades
        datos_memoria["dias_maximos"] = dias_max
        datos_memoria["precio_unitario_usd"] = precio_sku
        datos_memoria["costo_unitario_usd"] = costo_sku
        datos_memoria["fecha_ultima_venta"] = fecha_venta
        datos_memoria["lotes"] = lotes
        
        total_lotes_global += len(lotes)
        
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
                unidades_vencidas += cant
                valor_vencido += (cant * costo_sku)
                sku_tiene_vencidos = True
            elif edad >= (dias_max * 0.8):
                unidades_riesgo += cant
                valor_en_riesgo += (cant * costo_sku)
                sku_tiene_riesgo = True
                
        if sku_tiene_riesgo:
            skus_en_riesgo_count += 1
        if sku_tiene_vencidos:
            skus_vencidos_count += 1

    total_skus = len(memoria.keys())
    edad_promedio = round(suma_edades_unidades / total_unidades, 2) if total_unidades > 0 else 0.0
    porcentaje_riesgo = round((unidades_riesgo / total_unidades) * 100, 2) if total_unidades > 0 else 0.0
    porcentaje_vencidos = round((unidades_vencidas / total_unidades) * 100, 2) if total_unidades > 0 else 0.0
    porcentaje_salud = round(100 - porcentaje_riesgo - porcentaje_vencidos, 2)

    kpis = {
        "fecha": FECHA_HOY,
        "timestamp": TIMESTAMP,
        "total_skus": total_skus,
        "total_unidades": round(total_unidades, 2),
        "total_lotes": total_lotes_global,
        "edad_promedio": edad_promedio,
        "edad_maxima_inventario": edad_maxima_global,
        "unidades_en_riesgo": round(unidades_riesgo, 2),
        "porcentaje_en_riesgo": porcentaje_riesgo,
        "cantidad_skus_en_riesgo": skus_en_riesgo_count,
        "unidades_vencidas": round(unidades_vencidas, 2),
        "porcentaje_vencidos": porcentaje_vencidos,
        "cantidad_skus_vencidos": skus_vencidos_count,
        "salud_del_inventario": porcentaje_salud,
        "valor_en_riesgo": round(valor_en_riesgo, 2),
        "valor_vencido": round(valor_vencido, 2),
        "entradas_detectadas_unidades": round(total_entradas_dia, 2),
        "cantidad_skus_con_entrada": skus_con_entrada_count,
        "mermas_detectadas_unidades": round(total_mermas_dia, 2),
        "mermas_detectadas_usd": round(total_mermas_usd_dia, 2),
        "cantidad_skus_con_merma": skus_con_merma_count,
        "cantidad_skus_sin_venta": len(skus_sin_venta_hoy),
        "skus_sin_venta": skus_sin_venta_hoy,
        "sku_mas_antiguo": sku_mas_antiguo
    }

    return {
        "kpis": kpis,
        "inventario_actualizado": memoria
    }

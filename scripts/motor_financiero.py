def ejecutar_motor_financiero(inventario_actualizado: dict, kpis_inventario: dict, ventas_clasificado: dict) -> dict:
    ventas_data = ventas_clasificado
    inventario_data = inventario_actualizado
    kpis_inventario_data = kpis_inventario

    # 1. Información del sistema
    info_sistema_ventas = ventas_data.get("informacion_sistema", {})
    informacion_sistema = {
        "nombre_negocio": info_sistema_ventas.get("nombre_negocio", ""),
        "fecha_reporte": info_sistema_ventas.get("fecha_reporte", ""),
        "tasa_bcv_utilizada": info_sistema_ventas.get("tasa_bcv_utilizada", 0.0)
    }

    facturas = ventas_data.get("facturas_agrupadas", [])
    
    # Acumuladores globales
    venta_total_usd = 0.0
    costo_de_ventas_usd = 0.0
    unidades_vendidas = 0.0
    clientes_unicos = set()
    total_facturas = len(facturas)
    
    sku_ventas = {}
    
    # Estructura para bloques horarios
    bloques_horarios = {
        "mañana": {"ventas_usd": 0.0, "cantidad_facturas": 0, "unidades_vendidas": 0.0, "productos_dict": {}},
        "tarde": {"ventas_usd": 0.0, "cantidad_facturas": 0, "unidades_vendidas": 0.0, "productos_dict": {}},
        "noche": {"ventas_usd": 0.0, "cantidad_facturas": 0, "unidades_vendidas": 0.0, "productos_dict": {}}
    }
    
    combinaciones_count = {}

    # Procesar cada factura
    for factura in facturas:
        id_cliente = factura.get("id_cliente")
        if id_cliente:
            clientes_unicos.add(id_cliente)
            
        hora_str = factura.get("hora_venta", "")
        try:
            hora = int(hora_str.split(":")[0])
        except Exception:
            hora = 12
            
        if 6 <= hora < 12:
            bloque = "mañana"
        elif 12 <= hora < 18:
            bloque = "tarde"
        else:
            bloque = "noche"
            
        bloques_horarios[bloque]["cantidad_facturas"] += 1
            
        articulos_factura_nombres = []
        
        # Procesar artículos
        for art in factura.get("articulos", []):
            codigo = str(art.get("codigo_articulo", "")).strip()
            nombre = art.get("nombre", "").strip()
            cantidad = art.get("cantidad", 0.0)
            precio_un = art.get("precio_unitario_usd", art.get("precio_unidad_usd", 0.0))
            subtotal = art.get("subtotal_usd", cantidad * precio_un)
            
            prod_inv = inventario_data.get(codigo, {})
            costo_un = prod_inv.get("costo_unitario_usd", art.get("costo_unidad_usd", 0.0))
            categoria = prod_inv.get("categoria", art.get("categoria", "Sin clasificar"))
            
            if not nombre and prod_inv:
                nombre = prod_inv.get("nombre", "")

            if nombre:
                articulos_factura_nombres.append(nombre)
                if nombre not in bloques_horarios[bloque]["productos_dict"]:
                    bloques_horarios[bloque]["productos_dict"][nombre] = 0.0
                bloques_horarios[bloque]["productos_dict"][nombre] += cantidad

            venta_total_usd += subtotal
            costo_sku_total = cantidad * costo_un
            costo_de_ventas_usd += costo_sku_total
            unidades_vendidas += cantidad
            
            bloques_horarios[bloque]["ventas_usd"] += subtotal
            bloques_horarios[bloque]["unidades_vendidas"] += cantidad
            
            if codigo not in sku_ventas:
                sku_ventas[codigo] = {
                    "codigo_articulo": codigo,
                    "nombre": nombre,
                    "categoria": categoria,
                    "cantidad_vendida": 0.0,
                    "ventas_usd": 0.0,
                    "costo_usd": 0.0
                }
            
            sku_ventas[codigo]["cantidad_vendida"] += cantidad
            sku_ventas[codigo]["ventas_usd"] += subtotal
            sku_ventas[codigo]["costo_usd"] += costo_sku_total

        # Afinidad
        articulos_unicos_factura = sorted(list(set(articulos_factura_nombres)))
        if len(articulos_unicos_factura) >= 2:
            combo_tuple = tuple(articulos_unicos_factura)
            combinaciones_count[combo_tuple] = combinaciones_count.get(combo_tuple, 0) + 1

    # 2. KPIs globales financieros
    ganancia_real_usd = venta_total_usd - costo_de_ventas_usd
    ganancia_real_porcentaje = (ganancia_real_usd / venta_total_usd * 100) if venta_total_usd > 0 else 0.0
    ticket_promedio_usd = (venta_total_usd / total_facturas) if total_facturas > 0 else 0.0
    total_clientes = len(clientes_unicos)
    articulos_por_factura = (unidades_vendidas / total_facturas) if total_facturas > 0 else 0.0
    articulos_por_cliente = (unidades_vendidas / total_clientes) if total_clientes > 0 else 0.0
    skus_vendidos = len(sku_ventas)

    kpis_financieros = {
        "venta_total_usd": round(venta_total_usd, 2),
        "costo_de_ventas_usd": round(costo_de_ventas_usd, 2),
        "ganancia_real_usd": round(ganancia_real_usd, 2),
        "ganancia_real_porcentaje": round(ganancia_real_porcentaje, 2),
        "ticket_promedio_usd": round(ticket_promedio_usd, 2),
        "total_clientes": total_clientes,
        "total_facturas": total_facturas,
        "articulos_por_factura": round(articulos_por_factura, 2),
        "articulos_por_cliente": round(articulos_por_cliente, 2),
        "skus_vendidos": skus_vendidos,
        "unidades_vendidas": round(unidades_vendidas, 2)
    }

    # 3. Valor económico del inventario
    valor_costo_total_usd = 0.0
    valor_potencial_total_usd = 0.0

    for codigo, prod in inventario_data.items():
        costo_un = prod.get("costo_unitario_usd", 0.0)
        precio_un = prod.get("precio_unitario_usd", 0.0)
        lotes = prod.get("lotes", [])
        
        total_cant_inv = sum(l.get("cantidad", 0.0) for l in lotes)
        valor_costo_total_usd += (total_cant_inv * costo_un)
        valor_potencial_total_usd += (total_cant_inv * precio_un)

    ganancia_proyectada_usd = valor_potencial_total_usd - valor_costo_total_usd
    margen_proyectado_porcentaje = (ganancia_proyectada_usd / valor_potencial_total_usd * 100) if valor_potencial_total_usd > 0 else 0.0

    valor_economico_inventario = {
        "valor_costo_total_usd": round(valor_costo_total_usd, 2),
        "valor_potencial_total_usd": round(valor_potencial_total_usd, 2),
        "ganancia_proyectada_usd": round(ganancia_proyectada_usd, 2),
        "margen_proyectado_porcentaje": round(margen_proyectado_porcentaje, 2)
    }

    # 4 y 5. Categorías y Tabla Mix
    categorias_dict = {}
    for prod in inventario_data.values():
        cat_inv = prod.get("categoria", "Sin clasificar").strip()
        if cat_inv and cat_inv not in categorias_dict:
            categorias_dict[cat_inv] = {
                "categoria": cat_inv,
                "ventas_usd": 0.0,
                "costo_usd": 0.0,
                "unidades_vendidas": 0.0
            }

    tabla_mix_lista = []
    for codigo, datos in sku_ventas.items():
        cat = datos["categoria"]
        v_usd = datos["ventas_usd"]
        c_usd = datos["costo_usd"]
        g_usd = v_usd - c_usd
        cant_v = datos["cantidad_vendida"]
        
        margen_p = (g_usd / v_usd * 100) if v_usd > 0 else 0.0
        participacion_p = (v_usd / venta_total_usd * 100) if venta_total_usd > 0 else 0.0
        
        tabla_mix_lista.append({
            "codigo_articulo": codigo,
            "nombre": datos["nombre"],
            "categoria": cat,
            "cantidad_vendida": round(cant_v, 2),
            "ventas_usd": round(v_usd, 2),
            "costo_usd": round(c_usd, 2),
            "ganancia_usd": round(g_usd, 2),
            "margen_porcentaje": round(margen_p, 2),
            "participacion_porcentaje": round(participacion_p, 2)
        })
        
        if cat not in categorias_dict:
            categorias_dict[cat] = {
                "categoria": cat,
                "ventas_usd": 0.0,
                "costo_usd": 0.0,
                "unidades_vendidas": 0.0
            }
        categorias_dict[cat]["ventas_usd"] += v_usd
        categorias_dict[cat]["costo_usd"] += c_usd
        categorias_dict[cat]["unidades_vendidas"] += cant_v

    tabla_mix_lista = sorted(tabla_mix_lista, key=lambda x: x["ventas_usd"], reverse=True)

    categorias_lista = []
    for cat, datos in categorias_dict.items():
        g_usd = datos["ventas_usd"] - datos["costo_usd"]
        margen_p = (g_usd / datos["ventas_usd"] * 100) if datos["ventas_usd"] > 0 else 0.0
        participacion_p = (datos["ventas_usd"] / venta_total_usd * 100) if venta_total_usd > 0 else 0.0
        
        categorias_lista.append({
            "categoria": cat,
            "ventas_usd": round(datos["ventas_usd"], 2),
            "costo_usd": round(datos["costo_usd"], 2),
            "ganancia_usd": round(g_usd, 2),
            "margen_porcentaje": round(margen_p, 2),
            "unidades_vendidas": round(datos["unidades_vendidas"], 2),
            "participacion_porcentaje": round(participacion_p, 2)
        })

    categorias_lista = sorted(categorias_lista, key=lambda x: x["ventas_usd"], reverse=True)

    # Rankings
    top_vendidos = sorted(tabla_mix_lista, key=lambda x: x["cantidad_vendida"], reverse=True)[:20]
    top_vendidos_formateado = [
        {
            "codigo_articulo": x["codigo_articulo"], 
            "nombre": x["nombre"], 
            "categoria": x["categoria"],
            "cantidad_vendida": x["cantidad_vendida"]
        }
        for x in top_vendidos
    ]
    
    top_rentables = sorted(tabla_mix_lista, key=lambda x: x["ganancia_usd"], reverse=True)[:20]
    top_rentables_formateado = []
    for x in top_rentables:
        g_por_unidad = (x["ganancia_usd"] / x["cantidad_vendida"]) if x["cantidad_vendida"] > 0 else 0.0
        top_rentables_formateado.append({
            "codigo_articulo": x["codigo_articulo"], 
            "nombre": x["nombre"], 
            "categoria": x["categoria"],
            "ventas_usd": x["ventas_usd"],
            "ganancia_usd": x["ganancia_usd"],
            "ganancia_por_unidad_usd": round(g_por_unidad, 2),
            "margen_porcentaje": x["margen_porcentaje"]
        })
    
    top_facturacion = sorted(tabla_mix_lista, key=lambda x: x["ventas_usd"], reverse=True)[:20]
    top_facturacion_formateado = [
        {
            "codigo_articulo": x["codigo_articulo"], 
            "nombre": x["nombre"], 
            "categoria": x["categoria"],
            "ventas_usd": x["ventas_usd"]
        }
        for x in top_facturacion
    ]

    # Comportamiento temporal
    comportamiento_temporal = {}
    for bloque_nombre, bloque_datos in bloques_horarios.items():
        v_usd = bloque_datos["ventas_usd"]
        c_facturas = bloque_datos["cantidad_facturas"]
        u_vendidas = bloque_datos["unidades_vendidas"]
        
        t_promedio = (v_usd / c_facturas) if c_facturas > 0 else 0.0
        art_por_factura = (u_vendidas / c_facturas) if c_facturas > 0 else 0.0
        
        productos_bloque = [
            {"nombre": n, "cantidad": round(c, 2)} 
            for n, c in bloque_datos["productos_dict"].items()
        ]
        productos_bloque = sorted(productos_bloque, key=lambda x: x["cantidad"], reverse=True)
        
        comportamiento_temporal[bloque_nombre] = {
            "ventas_usd": round(v_usd, 2),
            "cantidad_facturas": c_facturas,
            "ticket_promedio": round(t_promedio, 2),
            "articulos_por_factura": round(art_por_factura, 2),
            "productos": productos_bloque
        }

    # Afinidad
    afinidad_productos = []
    sorted_combos = sorted(combinaciones_count.items(), key=lambda x: x[1], reverse=True)[:10]
    for combo, veces in sorted_combos:
        if veces >= 2:
            afinidad_productos.append({
                "productos": list(combo),
                "veces": veces
            })

    if not afinidad_productos:
        afinidad_productos = "No se detectaron patrones de frecuencia de compra"

    # Concentración
    top_10_productos_facturacion = sorted(tabla_mix_lista, key=lambda x: x["ventas_usd"], reverse=True)[:10]
    ventas_top10 = sum(x["ventas_usd"] for x in top_10_productos_facturacion)
    participacion_top10 = (ventas_top10 / venta_total_usd * 100) if venta_total_usd > 0 else 0.0
    concentracion = {
        "participacion_top10_porcentaje": round(participacion_top10, 2)
    }

    # Retorno final
    return {
        "informacion_sistema": informacion_sistema,
        "kpis_inventario": kpis_inventario_data,
        "kpis_financieros": kpis_financieros,
        "valor_economico_inventario": valor_economico_inventario,
        "categorias": categorias_lista,
        "tabla_mix": tabla_mix_lista,
        "top_vendidos": top_vendidos_formateado,
        "top_rentables": top_rentables_formateado,
        "top_facturacion": top_facturacion_formateado,
        "comportamiento_temporal": comportamiento_temporal,
        "afinidad_productos": afinidad_productos,
        "concentracion": concentracion
    }

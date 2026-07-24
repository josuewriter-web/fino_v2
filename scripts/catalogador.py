# ==========================================
# FUNCIONES AUXILIARES
# ==========================================

def extraer_skus_ventas(ventas):
    resultado = {}
    tabla = ventas.get("tabla_mix_productos", [])

    for producto in tabla:
        codigo = str(producto.get("codigo_articulo", "")).strip()
        if not codigo:
            continue

        resultado[codigo] = {
            "codigo_articulo": codigo,
            "nombre": str(producto.get("nombre", "")).strip()
        }

    return resultado


def extraer_skus_inventario(inventario):
    resultado = {}
    productos = inventario.get("productos", [])

    for producto in productos:
        codigo = str(producto.get("codigo_articulo", "")).strip()
        if not codigo:
            continue

        resultado[codigo] = {
            "codigo_articulo": codigo,
            "nombre": str(producto.get("nombre", "")).strip()
        }

    return resultado


def unir_skus(*listas):
    resultado = {}
    for lista in listas:
        resultado.update(lista)
    return resultado


# ==========================================
# FUNCIÓN PRINCIPAL
# ==========================================

def ejecutar_catalogador(ventas, inventario):
    ventas_skus = extraer_skus_ventas(ventas)
    inventario_skus = extraer_skus_inventario(inventario)

    todos_los_skus = unir_skus(ventas_skus, inventario_skus)

    return {
        "total_skus_detectados": len(todos_los_skus),
        "skus_detectados": list(todos_los_skus.values())
    }

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


def detectar_nuevos(skus_detectados, catalogo):
    nuevos = []
    
    # Si el catálogo viene como lista desde Make/DB, lo normalizamos a dict
    if isinstance(catalogo, list):
        catalogo_dict = {str(item.get("codigo_articulo", "")).strip(): item for item in catalogo}
    elif isinstance(catalogo, dict):
        catalogo_dict = catalogo
    else:
        catalogo_dict = {}

    for codigo, datos in skus_detectados.items():
        if codigo not in catalogo_dict:
            nuevos.append(datos)

    return nuevos


# ==========================================
# FUNCIÓN PRINCIPAL
# ==========================================

def ejecutar_catalogador(ventas, inventario, catalogo_maestro=None):
    if catalogo_maestro is None:
        catalogo_maestro = {}

    ventas_skus = extraer_skus_ventas(ventas)
    inventario_skus = extraer_skus_inventario(inventario)

    todos_los_skus = unir_skus(ventas_skus, inventario_skus)
    nuevos = detectar_nuevos(todos_los_skus, catalogo_maestro)

    return {
        "hay_skus_nuevos": len(nuevos) > 0,
        "total_skus_detectados": len(todos_los_skus),
        "total_skus_nuevos": len(nuevos),
        "skus_detectados": list(todos_los_skus.values()),
        "nuevos_skus": nuevos
    }

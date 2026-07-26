import json

# ==========================================
# FUNCIONES AUXILIARES
# ==========================================

def normalizar_catalogo(catalogo):
    """
    Convierte el catálogo a diccionario indexado por codigo_articulo.
    Maneja textos dobles de Make, listas y diccionarios anidados.
    """
    if not catalogo:
        return {}

    # 1. Si Make envía un JSON envuelto en comillas múltiples, lo desempaqueta del todo
    while isinstance(catalogo, str):
        catalogo = catalogo.strip()
        if not catalogo:
            return {}
        try:
            catalogo = json.loads(catalogo)
        except Exception:
            return {}

    if not isinstance(catalogo, (dict, list)):
        return {}

    # 2. Si viene dentro de una clave contenedora
    if isinstance(catalogo, dict):
        if "catalogo_actualizado" in catalogo and isinstance(catalogo["catalogo_actualizado"], (dict, list)):
            catalogo = catalogo["catalogo_actualizado"]
        elif "catalogo_maestro" in catalogo and isinstance(catalogo["catalogo_maestro"], (dict, list)):
            catalogo = catalogo["catalogo_maestro"]

    res = {}

    # 3. Si es una lista
    if isinstance(catalogo, list):
        for item in catalogo:
            if isinstance(item, dict):
                codigo = str(item.get("codigo_articulo", "")).strip()
                if codigo:
                    res[codigo] = item

    # 4. Si es un diccionario
    elif isinstance(catalogo, dict):
        for k, v in catalogo.items():
            if isinstance(v, dict):
                # Extrae el código interno o usa la clave ('MAS-001')
                codigo_interno = str(v.get("codigo_articulo", "")).strip()
                if codigo_interno:
                    res[codigo_interno] = v
                else:
                    res[str(k).strip()] = v
            else:
                res[str(k).strip()] = v

    return res


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
    
    catalogo_dict = normalizar_catalogo(catalogo)

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

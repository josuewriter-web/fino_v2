import json
import ast

# ==========================================
# FUNCIONES AUXILIARES
# ==========================================

def normalizar_catalogo(catalogo):
    """
    Convierte el catálogo a diccionario.
    Prueba varias formas de lectura para que el texto de Make no rompa el código.
    """
    if not catalogo:
        return {}

    data = None

    # Si ya es un diccionario o lista
    if isinstance(catalogo, (dict, list)):
        data = catalogo

    # Si viene como texto plano desde Make
    elif isinstance(catalogo, str):
        catalogo = catalogo.strip()
        if not catalogo:
            return {}

        # Intento 1: JSON normal ignorando saltos de línea
        try:
            data = json.loads(catalogo, strict=False)
        except Exception:
            # Intento 2: Formato de comillas simples de Python
            try:
                data = ast.literal_eval(catalogo)
            except Exception:
                # Intento 3: Limpiar comillas dañadas
                try:
                    limpio = catalogo.replace('\\"', '"').replace("'", '"')
                    data = json.loads(limpio, strict=False)
                except Exception as err:
                    print(f"Error leyendo el catálogo: {err}")
                    return {}
    else:
        return {}

    # Si viene dentro de una clave contenedora
    if isinstance(data, dict):
        if "catalogo_actualizado" in data and isinstance(data["catalogo_actualizado"], (dict, list)):
            data = data["catalogo_actualizado"]
        elif "catalogo_maestro" in data and isinstance(data["catalogo_maestro"], (dict, list)):
            data = data["catalogo_maestro"]

    res = {}

    # Si es una lista
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                codigo = str(item.get("codigo_articulo", "")).strip()
                if codigo:
                    res[codigo] = item

    # Si es un diccionario
    elif isinstance(data, dict):
        for k, v in data.items():
            if isinstance(v, dict):
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

import json

# ==========================================
# FUNCIONES AUXILIARES
# ==========================================

def normalizar_catalogo(catalogo):
    """
    Convierte el catálogo a diccionario indexado por codigo_articulo.
    Soporta dict, list, str (texto plano de JSON) o None/vacío.
    """
    if not catalogo:
        return {}

    # Si llega como texto plano desde Make, lo convierte a JSON
    if isinstance(catalogo, str):
        try:
            catalogo = json.loads(catalogo)
        except Exception:
            return {}

    if isinstance(catalogo, list):
        return {str(item.get("codigo_articulo", "")).strip(): item for item in catalogo if isinstance(item, dict)}
    elif isinstance(catalogo, dict):
        return {str(k).strip(): v for k, v in catalogo.items()}
    return {}


def extraer_skus_ventas(ventas):
    """Extrae los SKUs presentes en la tabla mix del reporte de ventas."""
    resultado = {}
    ventas_dict = ventas if isinstance(ventas, dict) else {}
    tabla = ventas_dict.get("tabla_mix_productos", [])

    if isinstance(tabla, list):
        for producto in tabla:
            if isinstance(producto, dict):
                codigo = str(producto.get("codigo_articulo", "")).strip()
                if not codigo:
                    continue

                resultado[codigo] = {
                    "codigo_articulo": codigo,
                    "nombre": str(producto.get("nombre", "")).strip()
                }

    return resultado


def extraer_skus_inventario(inventario):
    """Extrae los SKUs presentes en el reporte de inventario."""
    resultado = {}
    inventario_dict = inventario if isinstance(inventario, dict) else {}
    productos = inventario_dict.get("productos", [])

    if isinstance(productos, list):
        for producto in productos:
            if isinstance(producto, dict):
                codigo = str(producto.get("codigo_articulo", "")).strip()
                if not codigo:
                    continue

                resultado[codigo] = {
                    "codigo_articulo": codigo,
                    "nombre": str(producto.get("nombre", "")).strip()
                }

    return resultado


def unir_skus(*listas):
    """Unifica múltiples diccionarios de SKUs evitando duplicados."""
    resultado = {}
    for lista in listas:
        if isinstance(lista, dict):
            resultado.update(lista)
    return resultado


def detectar_nuevos(skus_detectados, catalogo):
    """Compara los SKUs detectados hoy contra el catálogo maestro guardado."""
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
    """
    Función principal que procesa las ventas e inventario del día,
    detecta si hay SKUs nuevos respecto al catálogo en memoria y 
    retorna el resumen listo para el siguiente paso del flujo.
    """
    # Garantiza que las entradas sean diccionarios/objetos válidos
    ventas = ventas or {}
    inventario = inventario or {}
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

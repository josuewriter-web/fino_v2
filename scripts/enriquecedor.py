CAMPO_CATEGORIA = "categoria"
CAMPO_DIAS = "dias_maximos"


def registrar_error(lista_errores, codigo, nombre, motivo):
    """
    Registra un error evitando duplicados por SKU.
    """
    if not any(e["codigo_articulo"] == codigo for e in lista_errores):
        lista_errores.append({
            "codigo_articulo": codigo,
            "nombre": nombre,
            "motivo": motivo
        })


def normalizar_catalogo(catalogo):
    """
    Convierte el catálogo a diccionario indexado por codigo_articulo
    soporta tanto formatos dict como list.
    """
    if isinstance(catalogo, list):
        return {str(item.get("codigo_articulo", "")).strip(): item for item in catalogo}
    elif isinstance(catalogo, dict):
        return {str(k).strip(): v for k, v in catalogo.items()}
    return {}


def obtener_info_catalogo(codigo, nombre, catalogo_dict, errores):
    if codigo not in catalogo_dict:
        registrar_error(
            errores,
            codigo,
            nombre,
            "SKU no encontrado en el catálogo maestro."
        )
        return None

    info = catalogo_dict[codigo]

    if CAMPO_CATEGORIA not in info:
        registrar_error(
            errores,
            codigo,
            nombre,
            "El SKU existe pero no tiene categoría."
        )
        return None

    if CAMPO_DIAS not in info:
        registrar_error(
            errores,
            codigo,
            nombre,
            "El SKU existe pero no tiene días máximos."
        )
        return None

    return info


# ==========================================
# FUNCIÓN PRINCIPAL
# ==========================================

def ejecutar_enriquecedor(ventas, inventario, catalogo_maestro):
    catalogo_dict = normalizar_catalogo(catalogo_maestro)
    errores = []

    if not catalogo_dict:
        raise ValueError("El catálogo maestro está vacío o no es válido.")

    # 1. ENRIQUECER TABLA MIX
    for producto in ventas.get("tabla_mix_productos", []):
        codigo = str(producto.get("codigo_articulo", "")).strip()
        nombre = str(producto.get("nombre", "")).strip()

        info = obtener_info_catalogo(codigo, nombre, catalogo_dict, errores)
        if info:
            producto[CAMPO_CATEGORIA] = info[CAMPO_CATEGORIA]

    # 2. ENRIQUECER FACTURAS
    # Soporta tanto 'facturas_agrupadas' (del Ingestor) como 'facturas'
    key_facturas = "facturas_agrupadas" if "facturas_agrupadas" in ventas else "facturas"

    for factura in ventas.get(key_facturas, []):
        # Soporta tanto 'articulos' (del Ingestor) como 'productos'
        key_articulos = "articulos" if "articulos" in factura else "productos"

        for producto in factura.get(key_articulos, []):
            codigo = str(producto.get("codigo_articulo", "")).strip()
            nombre = str(producto.get("nombre", "")).strip()

            info = obtener_info_catalogo(codigo, nombre, catalogo_dict, errores)
            if info:
                producto[CAMPO_CATEGORIA] = info[CAMPO_CATEGORIA]

    # 3. ENRIQUECER INVENTARIO
    for producto in inventario.get("productos", []):
        codigo = str(producto.get("codigo_articulo", "")).strip()
        nombre = str(producto.get("nombre", "")).strip()

        info = obtener_info_catalogo(codigo, nombre, catalogo_dict, errores)
        if info:
            producto[CAMPO_CATEGORIA] = info[CAMPO_CATEGORIA]
            producto[CAMPO_DIAS] = info[CAMPO_DIAS]

    return {
        "ventas": ventas,
        "inventario": inventario,
        "total_errores": len(errores),
        "errores": errores
    }

import pandas as pd
import json
import io
from datetime import datetime

CONFIG = {
    "columnas_inventario": {
        "codigo_articulo": "Código Saint",
        "nombre": "Descripción del Artículo",
        "existencia_actual": "Existencia",
        "precio_venta_usd": "Precio Venta (Bs.)",
        "costo_unidad_usd": "Costo Unitario (Bs.)"
    },
    "columnas_ventas": {
        "numero_factura": "Nro. Factura",
        "hora_venta": "Hora",
        "id_cliente": "Cédula Cliente",
        "codigo_articulo": "Código Saint",
        "nombre": "Descripción del Artículo",
        "cantidad": "Cant. Vendida",
        "precio_unidad_usd": "Precio Venta (Bs.)",
    }
}

def obtener_dia_semana(fecha_str):
    dias = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
    fecha_obj = datetime.strptime(fecha_str, "%d/%m/%Y")
    return dias[fecha_obj.weekday()]

def convertir_numero(valor):
    if pd.isna(valor):
        return 0.0
    texto = str(valor).strip()
    if not texto:
        return 0.0
    if ',' in texto:
        texto = texto.replace('.', '').replace(',', '.')
    try:
        return float(texto)
    except ValueError:
        return 0.0

# Lee el archivo desde la memoria RAM (bytes)
def leer_contenido(contenido_bytes, mapa_columnas):
    texto = contenido_bytes.decode('utf-8', errors='ignore')
    lineas = texto.splitlines()
    columnas_pos = list(mapa_columnas.values())
    
    fila_inicio = 0
    encontrado = False

    for i, linea in enumerate(lineas):
        if all(col in linea for col in columnas_pos):
            fila_inicio = i
            encontrado = True
            break
                
    if not encontrado:
        raise ValueError(f"No se encontró el encabezado. Buscaba: {columnas_pos}")

    buffer = io.StringIO(texto)
    df = pd.read_csv(buffer, skiprows=fila_inicio, sep=None, engine='python')

    faltan = [col for col in columnas_pos if col not in df.columns]
    if faltan:
        raise ValueError(f"Faltan columnas: {faltan}")

    mapa_inverso = {v: k for k, v in mapa_columnas.items()}
    return df.rename(columns=mapa_inverso)

def procesar_inventario(contenido_bytes, tasa_bcv):
    df = leer_contenido(contenido_bytes, CONFIG["columnas_inventario"])
    df = df[df["codigo_articulo"].notna() & (df["codigo_articulo"].astype(str).str.strip() != "TOTAL GENERAL")]

    for campo in ["existencia_actual", "precio_venta_usd", "costo_unidad_usd"]:
        df[campo] = df[campo].apply(convertir_numero)
        
    df["precio_venta_usd"] = round(df["precio_venta_usd"] / tasa_bcv, 2)
    df["costo_unidad_usd"] = round(df["costo_unidad_usd"] / tasa_bcv, 2)
    
    df_agrupado = df.groupby("codigo_articulo", as_index=False).agg({
        "nombre": "first",
        "existencia_actual": "sum",
        "precio_venta_usd": "first",
        "costo_unidad_usd": "first"
    })
    df_agrupado["stock_minimo"] = 0.0

    return df_agrupado.to_dict("records")

def procesar_ventas(contenido_bytes, tasa_bcv, mapa_costos):
    df = leer_contenido(contenido_bytes, CONFIG["columnas_ventas"])
    df = df[df["numero_factura"].notna() & (df["numero_factura"].astype(str).str.strip() != "TOTAL DIARIO")]
    
    tiene_costo_pos = "costo_unidad_usd" in CONFIG["columnas_ventas"]
    campos_numeros = ["cantidad", "precio_unidad_usd"]
    if tiene_costo_pos:
        campos_numeros.append("costo_unidad_usd")
        
    for campo in campos_numeros:
        df[campo] = df[campo].apply(convertir_numero)
        
    df["precio_unidad_usd"] = round(df["precio_unidad_usd"] / tasa_bcv, 2)
    
    if tiene_costo_pos:
        df["costo_unidad_usd"] = round(df["costo_unidad_usd"] / tasa_bcv, 2)
        def aplicar_fallback(row):
            costo_actual = row["costo_unidad_usd"]
            if costo_actual == 0.0 or pd.isna(costo_actual):
                return mapa_costos.get(row["codigo_articulo"], 0.0)
            return costo_actual
        df["costo_unidad_usd"] = df.apply(aplicar_fallback, axis=1)
    else:
        df["costo_unidad_usd"] = df["codigo_articulo"].map(mapa_costos).fillna(0.0)
    
    df["subtotal_usd"] = round(df["cantidad"] * df["precio_unidad_usd"], 2)
    
    facturas = []
    for num, grupo in df.groupby("numero_factura"):
        total_factura = round(grupo["subtotal_usd"].sum(), 2)
        factura = {
            "numero_factura": str(num),
            "hora_venta": str(grupo["hora_venta"].iloc[0]),
            "id_cliente": str(grupo["id_cliente"].iloc[0]),
            "total_factura_usd": total_factura,
            "articulos": grupo[[
                "codigo_articulo", "nombre", "cantidad", 
                "precio_unidad_usd", "costo_unidad_usd", "subtotal_usd"
            ]].to_dict("records")
        }
        facturas.append(factura)
        
    return facturas, df

def generar_tabla_mix(df_ventas):
    mix = df_ventas.groupby(["codigo_articulo", "nombre"], as_index=False).agg({
        "cantidad": "sum",
        "subtotal_usd": "sum"
    })
    mix = mix.rename(columns={"cantidad": "cantidad_vendida", "subtotal_usd": "ingresos_usd"})
    mix["cantidad_vendida"] = round(mix["cantidad_vendida"], 2)
    mix["ingresos_usd"] = round(mix["ingresos_usd"], 2)
    mix = mix.sort_values(by="ingresos_usd", ascending=False)
    return mix.to_dict("records")

# Función principal que llama FastAPI
def ejecutar_ingestor(bytes_inv, bytes_ventas, nombre_negocio, fecha, tasa_bcv):
    info_sistema = {
        "nombre_negocio": nombre_negocio,
        "fecha_reporte": fecha,
        "dia_semana": obtener_dia_semana(fecha),
        "tasa_bcv_utilizada": float(tasa_bcv)
    }

    productos = procesar_inventario(bytes_inv, tasa_bcv)
    mapa_costos = {p["codigo_articulo"]: p["costo_unidad_usd"] for p in productos}

    facturas, df_ventas = procesar_ventas(bytes_ventas, tasa_bcv, mapa_costos)
    tabla_mix = generar_tabla_mix(df_ventas)

    # Retorna el resultado como diccionario (FastAPI lo convierte a JSON)
    return {
        "inventario": {
            "informacion_sistema": info_sistema,
            "productos": productos
        },
        "ventas": {
            "informacion_sistema": info_sistema,
            "facturas_agrupadas": facturas,
            "tabla_mix_productos": tabla_mix
        }
    }

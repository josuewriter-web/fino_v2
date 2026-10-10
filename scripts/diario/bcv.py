import requests
from datetime import datetime, timezone, timedelta

def obtener_tasa_y_fecha():
    tasa_hoy = "0.00"
    
    try:
        url = "https://ve.dolarapi.com/v1/dolares/oficial"
        respuesta = requests.get(url, timeout=10).json()
        # Convierte a número y lo deja con solo 2 decimales
        valor = float(respuesta["promedio"])
        tasa_hoy = f"{valor:.2f}"
    except Exception:
        tasa_hoy = "0.00"

    # Fecha en formato numérico compatible (ej: 24/07/2026)
    zona_bcv = timezone(timedelta(hours=-4))
    hoy = datetime.now(zona_bcv)
    fecha_limpia = hoy.strftime("%d/%m/%Y")
    
    return {"tasa": tasa_hoy, "fecha": fecha_limpia}

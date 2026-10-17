import requests
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException

def obtener_tasa_y_fecha():
    url = "https://ve.dolarapi.com/v1/dolares/oficial"
    
    try:
        # Petición a DolarAPI con timeout de 10 segundos
        respuesta = requests.get(url, timeout=10)
        respuesta.raise_for_status()  # Lanza un error si la respuesta es HTTP 4xx o 5xx
        
        datos = respuesta.json()
        valor_promedio = float(datos["promedio"])
        
        # Validar que la tasa recibida sea razonable (no cero ni negativa)
        if valor_promedio <= 0:
            raise ValueError("La tasa BCV recibida no es válida (es menor o igual a 0).")
            
        tasa_hoy = round(valor_promedio, 2)
        
    except Exception as e:
        # En lugar de silenciar el error devolviendo "0.00", notificamos
        # de forma explícita para que Render/Make detengan el flujo.
        raise HTTPException(
            status_code=502, 
            detail=f"Error al obtener la tasa oficial del BCV desde DolarAPI: {str(e)}"
        )

    # Fecha en zona horaria de Venezuela (UTC-4)
    zona_bcv = timezone(timedelta(hours=-4))
    hoy = datetime.now(zona_bcv)
    fecha_limpia = hoy.strftime("%d/%m/%Y")
    
    return {
        "tasa": tasa_hoy,
        "fecha": fecha_limpia
    }

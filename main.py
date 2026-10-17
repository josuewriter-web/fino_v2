import re
from fastapi import FastAPI, UploadFile, File, Form, Response, Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Dict, Any, Optional, Union, List
from weasyprint import HTML

# Flujo Diario
from scripts.diario.bcv import obtener_tasa_y_fecha
from scripts.diario.ingestor import ejecutar_ingestor
from scripts.diario.catalogador import ejecutar_catalogador
from scripts.diario.enriquecedor import ejecutar_enriquecedor
from scripts.diario.control_inventario import ejecutar_control_inventario
from scripts.diario.motor_financiero import ejecutar_motor_financiero
from scripts.diario.motor_estado import ejecutar_motor_estado

# Flujo Semanal
from scripts.semanal.consolidador import procesar_semana
from scripts.semanal.comparador import comparar_semanas

# Flujo Mensual
from scripts.mensual.consolidador_mensual import procesar_mes
from scripts.mensual.comparador_mensual import comparar_meses

app = FastAPI()

# Función auxiliar para emojis en PDF
def cambiar_emojis_por_fotos(texto_html: str) -> str:
    patron = re.compile(r'[\U0001f000-\U0001ffff]')
    def reemplazar(match):
        codigo_hex = f"{ord(match.group(0)):x}"
        url_foto = f"https://cdnjs.cloudflare.com/ajax/libs/twemoji/14.0.2/72x72/{codigo_hex}.png"
        return f'<img src="{url_foto}" style="width: 1.1em; height: 1.1em; vertical-align: middle; margin-right: 3px;" />'
    return patron.sub(reemplazar, texto_html)

# Modelos para endpoints diarios
class PayloadCatalogador(BaseModel):
    ventas: Dict[str, Any]
    inventario: Dict[str, Any]
    catalogo_maestro: Optional[Union[Dict[str, Any], List[Any], str]] = {}

class PayloadEnriquecedor(BaseModel):
    ventas: Dict[str, Any]
    inventario: Dict[str, Any]
    catalogo_memoria: Optional[Union[Dict[str, Any], List[Any], str]] = None
    catalogo_nuevos: Optional[Union[Dict[str, Any], List[Any], str]] = None

class PayloadControlInventario(BaseModel):
    inventario: Dict[str, Any]
    ventas: Dict[str, Any]
    memoria: Optional[Union[Dict[str, Any], str]] = {}

class PayloadMotorFinanciero(BaseModel):
    inventario_actualizado: Dict[str, Any]
    kpis_inventario: Dict[str, Any]
    ventas_clasificado: Dict[str, Any]

class PayloadMotorEstado(BaseModel):
    estado: Dict[str, Any]
    kpis_financieros: Dict[str, Any]
    kpis_inventario: Dict[str, Any]
    fecha: Optional[str] = None


# --- ENDPOINTS FLUJO DIARIO ---

@app.get("/bcv")
def api_bcv():
    return obtener_tasa_y_fecha()

@app.post("/ingestor")
async def endpoint_ingestor(
    file_inventario: UploadFile = File(...),
    file_ventas: UploadFile = File(...),
    nombre_negocio: str = Form(...),
    fecha: str = Form(...),
    tasa_bcv: float = Form(...)
):
    bytes_inv = await file_inventario.read()
    bytes_ventas = await file_ventas.read()
    return ejecutar_ingestor(bytes_inv, bytes_ventas, nombre_negocio, fecha, tasa_bcv)

@app.post("/catalogador")
async def endpoint_catalogador(payload: PayloadCatalogador):
    return ejecutar_catalogador(payload.ventas, payload.inventario, payload.catalogo_maestro)

@app.post("/enriquecedor")
async def endpoint_enriquecedor(payload: PayloadEnriquecedor):
    return ejecutar_enriquecedor(
        ventas=payload.ventas,
        inventario=payload.inventario,
        catalogo_memoria=payload.catalogo_memoria,
        catalogo_nuevos=payload.catalogo_nuevos
    )

@app.post("/control-inventario")
async def endpoint_control_inventario(payload: PayloadControlInventario):
    return ejecutar_control_inventario(payload.inventario, payload.ventas, payload.memoria)

@app.post("/motor-financiero")
async def endpoint_motor_financiero(payload: PayloadMotorFinanciero):
    return ejecutar_motor_financiero(payload.inventario_actualizado, payload.kpis_inventario, payload.ventas_clasificado)

@app.post("/motor-estado")
async def endpoint_motor_estado(payload: PayloadMotorEstado):
    return ejecutar_motor_estado(payload.estado, payload.kpis_financieros, payload.kpis_inventario, payload.fecha)


# --- ENDPOINTS FLUJO SEMANAL ---

@app.post("/procesar-semana")
def api_procesar_semana(payload: Union[List[Dict[str, Any]], Dict[str, Any]], key: Optional[str] = None):
    resultado = procesar_semana(payload)
    if isinstance(resultado, dict) and "error" in resultado:
        raise HTTPException(status_code=400, detail=resultado["error"])
    return resultado

@app.post("/comparar")
async def api_comparar(request: Request):
    data = await request.json()
    semana_actual = data.get("semana_actual", data)
    semana_pasada = data.get("semana_pasada")
    resultado = comparar_semanas(semana_actual, semana_pasada)
    return JSONResponse(content=resultado)


# --- ENDPOINTS FLUJO MENSUAL ---

@app.post("/procesar-mes")
def api_procesar_mes(payload: Union[List[Dict[str, Any]], Dict[str, Any]]):
    """Consolida los reportes diarios para generar los KPIs del mes."""
    datos_entrada = payload.get("dias_json", payload) if isinstance(payload, dict) else payload
    if not datos_entrada:
        raise HTTPException(status_code=400, detail="El cuerpo de la solicitud no contiene datos válidos.")
    
    resultado = procesar_mes(datos_entrada)
    if isinstance(resultado, dict) and "error" in resultado:
        raise HTTPException(status_code=400, detail=resultado["error"])
    return resultado

@app.post("/comparar-meses")
async def api_comparar_meses(request: Request):
    """Compara el mes actual con el mes pasado y calcula variaciones."""
    data = await request.json()
    mes_actual = data.get("mes_actual")
    mes_pasado = data.get("mes_pasado")

    if not mes_actual:
        raise HTTPException(status_code=400, detail="El campo 'mes_actual' es obligatorio en el cuerpo de la solicitud.")

    resultado = comparar_meses(mes_actual, mes_pasado)
    return JSONResponse(content=resultado)


# --- ENDPOINT COMPARTIDO / UTILIDAD ---

@app.post("/convertir")
async def convertir_pdf(request: Request):
    body = await request.body()
    html_text = body.decode("utf-8")
    html_final = cambiar_emojis_por_fotos(html_text)
    pdf_bytes = HTML(string=html_final).write_pdf()
    return Response(content=pdf_bytes, media_type="application/pdf")

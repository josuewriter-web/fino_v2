import re
from fastapi import FastAPI, UploadFile, File, Form, Response, Request
from pydantic import BaseModel
from typing import Dict, Any, Optional, Union, List
from weasyprint import HTML

from scripts.bcv import obtener_tasa_y_fecha
from scripts.ingestor import ejecutar_ingestor
from scripts.catalogador import ejecutar_catalogador
from scripts.enriquecedor import ejecutar_enriquecedor
from scripts.control_inventario import ejecutar_control_inventario
from scripts.motor_financiero import ejecutar_motor_financiero
from scripts.motor_estado import ejecutar_motor_estado

app = FastAPI()

# Función auxiliar para emojis en PDF
def cambiar_emojis_por_fotos(texto_html: str) -> str:
    patron = re.compile(r'[\U0001f000-\U0001ffff]')
    def reemplazar(match):
        codigo_hex = f"{ord(match.group(0)):x}"
        url_foto = f"https://cdnjs.cloudflare.com/ajax/libs/twemoji/14.0.2/72x72/{codigo_hex}.png"
        return f'<img src="{url_foto}" style="width: 1.1em; height: 1.1em; vertical-align: middle; margin-right: 3px;" />'
    return patron.sub(reemplazar, texto_html)

# Modelos para endpoints
class PayloadCatalogador(BaseModel):
    ventas: Dict[str, Any]
    inventario: Dict[str, Any]
    catalogo_maestro: Optional[Union[Dict[str, Any], List[Any]]] = {}

class PayloadEnriquecedor(BaseModel):
    ventas: Dict[str, Any]
    inventario: Dict[str, Any]
    catalogo_maestro: Union[Dict[str, Any], List[Any]]

class PayloadControlInventario(BaseModel):
    inventario: Dict[str, Any]
    ventas: Dict[str, Any]
    memoria: Optional[Dict[str, Any]] = {}

class PayloadMotorFinanciero(BaseModel):
    inventario_actualizado: Dict[str, Any]
    kpis_inventario: Dict[str, Any]
    ventas_clasificado: Dict[str, Any]

class PayloadMotorEstado(BaseModel):
    estado: Dict[str, Any]
    kpis_financieros: Dict[str, Any]
    kpis_inventario: Dict[str, Any]
    fecha: Optional[str] = None


# Endpoint 1: Buscar Tasa BCV
@app.get("/bcv")
def api_bcv():
    return obtener_tasa_y_fecha()

# Endpoint 2: Ingestor
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

    return ejecutar_ingestor(
        bytes_inv, 
        bytes_ventas, 
        nombre_negocio, 
        fecha, 
        tasa_bcv
    )

# Endpoint 3: Catalogador
@app.post("/catalogador")
async def endpoint_catalogador(payload: PayloadCatalogador):
    return ejecutar_catalogador(
        payload.ventas,
        payload.inventario,
        payload.catalogo_maestro
    )

# Endpoint 4: Enriquecedor
@app.post("/enriquecedor")
async def endpoint_enriquecedor(payload: PayloadEnriquecedor):
    return ejecutar_enriquecedor(
        payload.ventas,
        payload.inventario,
        payload.catalogo_maestro
    )

# Endpoint 5: Control de Inventario
@app.post("/control-inventario")
async def endpoint_control_inventario(payload: PayloadControlInventario):
    return ejecutar_control_inventario(
        payload.inventario,
        payload.ventas,
        payload.memoria
    )

# Endpoint 6: Motor Financiero
@app.post("/motor-financiero")
async def endpoint_motor_financiero(payload: PayloadMotorFinanciero):
    return ejecutar_motor_financiero(
        payload.inventario_actualizado,
        payload.kpis_inventario,
        payload.ventas_clasificado
    )

# Endpoint 7: Motor de Estado
@app.post("/motor-estado")
async def endpoint_motor_estado(payload: PayloadMotorEstado):
    return ejecutar_motor_estado(
        payload.estado,
        payload.kpis_financieros,
        payload.kpis_inventario,
        payload.fecha
    )

# Endpoint 8: Convertir PDF (WeasyPrint)
@app.post("/convertir")
async def convertir_pdf(request: Request):
    body = await request.body()
    html_text = body.decode("utf-8")
    html_final = cambiar_emojis_por_fotos(html_text)
    pdf_bytes = HTML(string=html_final).write_pdf()
    return Response(content=pdf_bytes, media_type="application/pdf")

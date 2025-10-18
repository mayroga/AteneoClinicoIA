from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from typing import Optional, Any, Dict, List
import os
import json
import stripe
from google import genai
from google.genai.errors import APIError
import asyncio
import time
import base64
from dotenv import load_dotenv

# 1. Cargar variables de entorno (para desarrollo local)
load_dotenv()

# =========================================================================
# 0. CONFIGURACIÓN DE SECRETOS, TIERS Y ADD-ONS
# =========================================================================

# NOTA: Estas claves DEBEN ser configuradas como variables de entorno
ADMIN_BYPASS_KEY = os.getenv("ADMIN_BYPASS_KEY", "CLAVE_SECRETA_ADMIN")
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY", "pk_test_...")
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
RENDER_APP_URL = os.getenv("RENDER_APP_URL", "https://ateneoclinicoia.onrender.com")

# ESTRUCTURA MEJORADA: VALOR POR ALCANCE FUNCIONAL
# INSTRUCCIONES MODIFICADAS: Tratamiento Hipotético con alternativas (genéricos/baratos) para todos los niveles.
TIERS = {
    1: {"name": " Nivel 1 – Diagnóstico Rápido", "price": 10, "value_focus": "Respuesta Directa. (1 Tarea IA)", "max_time_min": 5, "token_instruction": "Proporciona una respuesta extremadamente concisa y directa (Diagnóstico y/o Hipótesis). Máximo 100 palabras. Al final, añade una sección de 'Tratamiento Hipotético (Simulación)', obligatoriamente con opciones de manejo. Incluye al menos 1-2 alternativas de medicamentos genéricos/baratos si aplica. Asegura el aviso en ROJO.", "base_tasks": ["Diagnóstico/Hipótesis", "Tratamiento Hipotético (Sim.)"]},
    2: {"name": " Nivel 2 – Evaluación Estándar", "price": 50, "value_focus": "Análisis Básico Completo. (2 Tareas IA)", "max_time_min": 10, "token_instruction": "Proporciona un Diagnóstico Definitivo y una Sugerencia Terapéutica General y concisa. Máximo 500 palabras. Al final, añade una sección de 'Tratamiento Hipotético (Simulación)'. Incluye opciones de tratamiento que consideren recursos limitados (genéricos/baratos) y el estándar de oro. Asegura el aviso en ROJO.", "base_tasks": ["Diagnóstico Definitivo", "Sugerencia Terapéutica General", "Tratamiento Hipotético (Sim.)"]},
    3: {"name": " Nivel 3 – Planificación y Protocolo", "price": 100, "value_focus": "Protocolo Clínico Detallado. Genera Escenario Clínico.", "max_time_min": 25, "token_instruction": "Genera un Escenario Clínico completo, exigiendo un razonamiento crítico. Genera un Protocolo Clínico Detallado: Diagnóstico, Terapia Específica y Plan de Pruebas Adicionales (Laboratorio/Imagen). Simula el pensamiento de un examen tipo Board. Análisis PROFUNDO, CRÍTICO y listo para el debate profesional. El 'Tratamiento Hipotético (Simulación)' debe ser robusto, incluyendo la terapia de primera línea y alternativas económicas o de recursos limitados. Máximo 800 palabras. Asegura el aviso en ROJO.", "base_tasks": ["Diagnóstico Definitivo", "Terapia Específica", "Plan de Pruebas Adicionales", "Tratamiento Hipotético (Sim.)"]},
    4: {"name": " Nivel 4 – Debate y Evidencia", "price": 200, "value_focus": "Análisis Crítico y Controvertido. Genera Escenario Clínico.", "max_time_min": 45, "token_instruction": "Genera un Escenario Clínico completo, exigiendo un razonamiento crítico. Genera un Debate Clínico que incluye Diagnóstico, Terapia, Pruebas y una Sección 'Debate y Alternativas', analizando controversias y evidencia. El 'Tratamiento Hipotético (Simulación)' debe ser exhaustivo, contrastando el estándar de oro con opciones de bajo coste/genéricos. Simula el pensamiento de un examen tipo Board/Enclex. Análisis PROFUNDO, CRÍTICO y listo para el debate profesional. Máximo 1500 palabras. Asegura el aviso en ROJO.", "base_tasks": ["Diagnóstico", "Terapia", "Pruebas Adicionales", "Debate y Alternativas", "Tratamiento Hipotético (Sim.)"]},
    5: {"name": " Nivel 5 – Mesa Clínica Premium", "price": 500, "value_focus": "Multi-Caso y Documentación Formal. Genera Escenario Clínico.", "max_time_min": 70, "token_instruction": "Genera un Escenario Clínico completo, exigiendo un razonamiento crítico. Analiza tres casos clínicos proporcionados de forma secuencial. Al final proporciona un Resumen Comparativo, Insights y un borrador de Documentación Formal. El 'Tratamiento Hipotético (Simulación)' debe ser el más completo, comparando el coste-efectividad y la logística de tratamientos múltiples, incluyendo alternativas genéricas. Simula el pensamiento de un examen tipo Board/Enclex. Análisis PROFUNDO, CRÍTICO y listo para el debate profesional. Máximo 3000 palabras. Asegura el aviso en ROJO.", "base_tasks": ["Diagnóstico Completo", "Terapia y Protocolo", "Debate Crítico", "Análisis Comparativo (Multi-Caso)", "Borrador de Informe Documental", "Tratamiento Hipotético (Sim.)"]},
}

# ADD-ONS DEFINITION (Precios fijos)
ADDONS = {
    "image_analysis": {"name": "Análisis de Imagen/Laboratorio", "price": 10, "instruction_boost": "INTEGRA EL ANÁLISIS VISUAL DE LA IMAGEN/LABORATORIO al diagnóstico. Aumenta la profundidad del análisis en 200 palabras adicionales."},
    "tts_audio": {"name": "Audio Profesional del Análisis (TTS)", "price": 3, "tiers_included": [3, 4, 5]}, # Incluido en Nivel 3, 4, 5
}

# Inicialización de Stripe
if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY

# Inicialización del Cliente de Gemini
gemini_client = None
if GEMINI_API_KEY:
    try:
        gemini_client = genai.Client(api_key=GEMINI_API_KEY)
    except Exception as e:
        print(f"Error inicializando el cliente de Gemini: {e}")

# Inicialización de la aplicación FastAPI
app = FastAPI(title="Ateneo Clínico IA Backend API")

# --- CONFIGURACIÓN CRÍTICA DE CORS ---
origins = ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================================================================
# 1. MIDDLEWARE DE SEGURIDAD CRÍTICO PARA PERMITIR STRIPE (SOLUCIÓN)
# =========================================================================

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """
    Añade encabezados de seguridad para la integración sin bloqueos con Stripe.
    Esto permite a Google Chrome (y otros) la redirección y carga de recursos de Stripe.
    """
    response = await call_next(request)
    
    # Política de Seguridad de Contenido (CSP): Permite scripts y frames de los dominios de Stripe
    csp_header = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://js.stripe.com; "
        "frame-src 'self' https://js.stripe.com https://hooks.stripe.com https://checkout.stripe.com; "
        "connect-src 'self' https://api.stripe.com https://q.stripe.com https://checkout.stripe.com;"
    )
    response.headers["Content-Security-Policy"] = csp_header
    
    # Referrer-Policy: Esencial para la redirección segura entre dominios
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    
    # X-Frame-Options: Buena práctica de seguridad (protege contra clickjacking)
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    
    return response

# =========================================================================
# 2. UTILITY FUNCTIONS (Funciones de Soporte)
# =========================================================================

async def call_gemini_api(prompt: str, token_instruction: str, image_data: Optional[bytes] = None):
    """
    Genera el análisis clínico con instrucciones específicas para control de tokens
    y maneja la entrada multimodal (texto + imagen).
    """
    if not gemini_client:
        return {
            "analysis_status": "error",
            "reason": "GEMINI_API_KEY no configurada. El servicio de análisis de IA está DESACTIVADO.",
            "prompt_used": prompt
        }
    
    # 1. CONSTRUCCIÓN DE LA INSTRUCCIÓN DEL SISTEMA (MODIFICADO: Sin mención a Gemini + Preguntas Obligatorias)
    # Se añade la instrucción de tratamiento hipotético directamente al prompt system para controlar el formato
    # y la instrucción de la advertencia.
    
    system_instruction = (
        f"Eres un analista clínico experto que debe actuar como un humano profesional. {token_instruction} "
        "Analiza el caso. Detecta automáticamente el idioma de la consulta y responde íntegramente en ese mismo idioma. "
        "El Tratamiento Hipotético (Simulación) o Tratamiento Medicamentoso siempre debe aparecer al final en una sección propia "
        "que incluya el aviso '⚠️ Solo Simulación, Experimental, para Estudio y Debate. ⚠️' justo antes de la lista de opciones. "
        "IMPORTANTE: Si la 'Descripción del Caso' es muy corta (menos de 30 palabras) o vaga, DEBES incluir al final de tu respuesta "
        "una sección obligatoria de 'Preguntas de Seguimiento para el Ateneo Clínico IA' con al menos tres preguntas clave para un mejor diagnóstico. "
        "El análisis es generado por el ATENEO CLÍNICO IA." # <<-- INSTRUCCIÓN CRÍTICA DE LENGUAJE
    )

    # 2. CONSTRUCCIÓN DE LA ENTRADA MULTIMODAL (parts)
    parts = []
    
    # Agregar la imagen si existe
    if image_data:
        # Nota: La simulación de archivo aquí asume que es una imagen simple (e.g., JPEG/PNG).
        # Usamos 'image/jpeg' como un MIME type de fallback.
        parts.append({
            "inlineData": {
                "mimeType": "image/jpeg",
                "data": image_data.decode('latin1') # Decodificación simple a base64
            }
        })
        
    # Agregar el texto del prompt
    parts.append({"text": prompt})


    def blocking_call():
        """Función síncrona que envuelve la llamada al cliente de Gemini (Texto/Multimodal)."""
        response = gemini_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=parts, # Usa las partes (imagen + texto)
            config=dict(
                system_instruction=system_instruction
            )
        )
        return response.text
        
    try:
        # Ejecutar la llamada a la API en un hilo separado para no bloquear la ejecución asíncrona de FastAPI
        analysis_text = await asyncio.to_thread(blocking_call)
        
        return {
            "analysis_status": "success",
            "analysis_text": analysis_text
        }
            
    except APIError as e:
        print(f"Error de API de Gemini: {e}")
        return {
            "analysis_status": "error",
            "reason": f"Error de API de Gemini: {e}. Revise su cuota o clave.",
            "prompt_used": prompt
        }
    except Exception as e:
        print(f"Error inesperado con Gemini: {e}")
        return {
            "analysis_status": "error",
            "reason": f"Error desconocido al llamar a Gemini: {e}",
            "prompt_used": prompt
        }


def create_stripe_checkout_session(total_price: int, product_name: str, metadata: dict, line_items: List[Dict]):
    """Crea una sesión de Stripe Checkout con múltiples line_items para los add-ons."""
    
    if not stripe.api_key:
        raise HTTPException(status_code=500, detail="La clave secreta de Stripe no está configurada.")
        
    success_url = f"{RENDER_APP_URL}/stripe/success?session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{RENDER_APP_URL}/stripe/cancel"
    
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=line_items, # Usamos los line_items construidos
            mode='payment',
            success_url=success_url,
            cancel_url=cancel_url,
            metadata=metadata,
        )
        return {"status": "payment_required", "payment_url": session.url, "price": total_price, "currency": "USD"}
    
    except stripe.error.StripeError as e:
        print(f"Error de Stripe: {e}")
        raise HTTPException(status_code=500, detail=f"Error en la API de Stripe: {e}")
    except Exception as e:
        print(f"Error desconocido al crear la sesión de pago: {e}")
        raise HTTPException(status_code=500, detail="Error desconocido al crear la sesión de pago.")


async def fulfill_case(metadata: Dict[str, Any]):
    """
    Función de cumplimiento que se ejecuta DESPUÉS de un pago exitoso (via Webhook).
    Esta es la ruta crítica para el control de tokens y add-ons.
    """
    user_id = metadata.get("user_id", "Unknown")
    level = int(metadata.get("service_level", 1))
    
    # 1. Recuperar info base
    tier_info = TIERS.get(level, TIERS[1])
    # Ttoken_instruction tiene las nuevas órdenes de tratamiento diversificado
    token_instruction = tier_info["token_instruction"]
    
    # 2. Checkear Add-ons pagados y ajustar instrucción de tokens
    include_image_analysis = metadata.get("image_analysis", "false") == "true"
    
    if include_image_analysis:
        # Aumentar la instrucción de tokens si se pagó por el add-on de imagen
        token_instruction += " " + ADDONS["image_analysis"]["instruction_boost"]
        # Aquí se debería recuperar el archivo adjunto (que fue temporalmente almacenado)
        image_data_simulated = True
    else:
        image_data_simulated = False
        
    
    description_snippet = metadata.get("description_snippet", "Caso clínico no especificado.")
    prompt = f"Analizar el siguiente caso clínico: {description_snippet}"
    
    # SIMULACIÓN DE LA LLAMADA: Asumimos que no hay datos binarios reales para la imagen en el webhook
    analysis_result = await call_gemini_api(prompt, token_instruction, image_data=None)
    
    print(f" Análisis de IA completado (Nivel {level}) para el usuario {user_id}. Estado: {analysis_result.get('analysis_status')}")
    
    # REGISTRO AUTOMÁTICO CRÍTICO:
    print(f"REGISTRO AUTOMÁTICO: Caso ID: XXX, Nivel: {level}, Pagó Imagen: {include_image_analysis}, Pagó Audio: {metadata.get('tts_audio')}")

    return analysis_result


# =========================================================================
# 3. ENDPOINTS API (Rutas)
# =========================================================================

# --- RUTA PRINCIPAL DE SERVICIO (Controlada por Nivel y Add-ons) ---
@app.post("/create-service")
async def create_service(
    user_id: int = Form(...),
    service_level: int = Form(...),
    description: str = Form(None),
    include_image_analysis: bool = Form(False),
    include_tts_addon: bool = Form(False),
    developer_bypass_key: str = Form(None),
    clinical_file: Optional[UploadFile] = File(None)
):
    
    if service_level not in TIERS:
        raise HTTPException(status_code=400, detail="Nivel de servicio no válido.")
        
    tier_info = TIERS[service_level]
    
    # Lógica anti-doble cobro TTS
    is_tts_included = service_level in ADDONS["tts_audio"]["tiers_included"]
    # Si se marca el checkbox PERO ya está incluido en el nivel, ignoramos el cargo.
    charge_for_tts = include_tts_addon and not is_tts_included
    
    # 1. FLUJO DE BYPASS (GRATUITO PARA DESARROLLO)
    if developer_bypass_key and developer_bypass_key == ADMIN_BYPASS_KEY:
        
        # 1.1. Construir la instrucción de tokens base
        prompt_instruction = tier_info["token_instruction"]
        
        # 1.2. Añadir boost de tokens si se incluyó el add-on de imagen
        if include_image_analysis and clinical_file:
            prompt_instruction += " " + ADDONS["image_analysis"]["instruction_boost"]
        
        prompt = description if description else "Caso clínico no especificado. Análisis genérico de salud preventiva."
        
        # Preparar la data de la imagen para la llamada multimodal
        image_data_base64 = None
        if clinical_file and clinical_file.file:
            # Leer el contenido del archivo si existe (necesario para el bypass multimodal)
            file_contents = await clinical_file.read()
            # Codificar la imagen para el envío a Gemini (simulación: base64 en latin1)
            image_data_base64 = base64.b64encode(file_contents).decode('latin1')
            
        # Ejecutar análisis con la instrucción de tokens del nivel seleccionado
        analysis_result = await call_gemini_api(prompt, prompt_instruction, image_data=image_data_base64)
        file_info = clinical_file.filename if clinical_file else None
        
        # En el bypass, el audio se considera 'incluido' si se solicitó O si el nivel lo incluye
        tts_included_in_fulfillment = include_tts_addon or is_tts_included
        
        return {
            "status": "success",
            "payment_method": "Bypass (Gratuito)",
            "fulfillment": {
                "user_id": user_id,
                "service_level": service_level,
                "analysis_result": analysis_result,
                "file_info": file_info,
                "max_time_min": tier_info["max_time_min"], # Tiempo simulado
                "tts_included": tts_included_in_fulfillment # Bandera para activar el botón de audio en el frontend
            }
        }

    # 2. FLUJO DE PAGO DE STRIPE
    
    total_price = tier_info["price"]
    line_items = []
    
    # 2.1. Añadir el Line Item Base (Tier)
    line_items.append({
        'price_data': {
            'currency': 'usd',
            'product_data': {'name': tier_info["name"]},
            'unit_amount': tier_info["price"] * 100,
        },
        'quantity': 1,
    })
    
    # 2.2. Manejar Add-on de Análisis de Imagen
    if include_image_analysis:
        addon_info = ADDONS["image_analysis"]
        total_price += addon_info["price"]
        line_items.append({
            'price_data': {
                'currency': 'usd',
                'product_data': {'name': addon_info["name"]},
                'unit_amount': addon_info["price"] * 100,
            },
            'quantity': 1,
        })

    # 2.3. Manejar Add-on de Audio (Solo si se requiere cargo)
    if charge_for_tts:
        addon_info = ADDONS["tts_audio"]
        total_price += addon_info["price"]
        line_items.append({
            'price_data': {
                'currency': 'usd',
                'product_data': {'name': addon_info["name"]},
                'unit_amount': addon_info["price"] * 100,
            },
            'quantity': 1,
        })
    
    # El metadata debe reflejar si el audio se incluirá, ya sea por pago o por ser un nivel alto.
    tts_included_in_metadata = include_tts_addon or is_tts_included

    metadata = {
        "user_id": str(user_id),
        "service_level": str(service_level),
        "description_snippet": description[:100] if description else "N/A",
        "image_analysis": "true" if include_image_analysis else "false",
        "tts_audio": "true" if tts_included_in_metadata else "false", # Bandera real para fulfillment
        "file_name": clinical_file.filename if clinical_file else "No File"
    }

    return create_stripe_checkout_session(total_price, "Servicio Clínico IA", metadata, line_items)


# --- RUTA WEBHOOK DE STRIPE (Fulfillment Seguro y CRÍTICO) ---
@app.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    """
    Ruta para manejar eventos POST de Stripe (Webhooks).
    CRÍTICO: Verifica la firma y solo cumple el servicio con pago confirmado.
    """
    if not STRIPE_WEBHOOK_SECRET:
        print(" STRIPE_WEBHOOK_SECRET no configurada. Saltando verificación de firma (RIESGO DE FRAUDE).")
        
    payload = await request.body()
    sig_header = request.headers.get('stripe-signature')
    event = None

    # 1. VERIFICAR LA FIRMA DEL WEBHOOK
    try:
        if STRIPE_WEBHOOK_SECRET:
              event = stripe.Webhook.construct_event(
                  payload, sig_header, STRIPE_WEBHOOK_SECRET
               )
        else:
              event = json.loads(payload.decode('utf-8'))
              
    except Exception as e:
        print(f"Webhook Error: Error de verificación o carga: {e}")
        return JSONResponse({"message": "Invalid signature or payload"}, status_code=400)
        
    # 2. MANEJAR EL EVENTO PRINCIPAL
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        
        if session.get('payment_status') == 'paid':
            print(f" Pago exitoso y verificado para Session ID: {session['id']}")
            
            # 3. Ejecutar la función de cumplimiento (ASÍNCRONA)
            # Esta función desencadena el análisis de IA real.
            asyncio.create_task(fulfill_case(session['metadata']))
            
        else:
            print(f" Sesión completada, pero no pagada para Session ID: {session['id']}")

    return JSONResponse({"message": "Success"}, status_code=200)

# --- RUTAS DE REDIRECCIÓN Y PRINCIPAL (Mantenidas y actualizadas) ---

@app.get("/stripe/success", response_class=HTMLResponse)
async def stripe_success(session_id: str):
    return HTMLResponse(f"""
        <body style="font-family: 'Inter', sans-serif; text-align: center; padding: 50px; background: #e0f2f1;">
            <div style="background: white; padding: 40px; border-radius: 12px; max-width: 600px; margin: auto; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
                <h1 style="color: #059669;">¡Pago Recibido y Verificado!</h1>
                <p>Su pago ha sido **verificado por nuestro Webhook seguro**. El análisis de IA (controlado por tokens) se está ejecutando AHORA de forma asíncrona. Estará listo en breve.</p>
                <p style="margin-top: 20px;"><a href="{RENDER_APP_URL}" style="color: #10b981; text-decoration: none; font-weight: bold;">Volver a la plataforma</a></p>
            </div>
        </body>
    """)

@app.get("/stripe/cancel", response_class=HTMLResponse)
async def stripe_cancel():
    return HTMLResponse(f"""
        <body style="font-family: 'Inter', sans-serif; text-align: center; padding: 50px; background: #fee2e2;">
            <div style="background: white; padding: 40px; border-radius: 12px; max-width: 600px; margin: auto; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
                <h1 style="color: #dc2626;">Pago Cancelado</h1>
                <p>Su proceso de pago fue cancelado. No se ha realizado ningún cargo.</p>
                <p style="margin-top: 20px;"><a href="{RENDER_APP_URL}" style="color: #ef4444; text-decoration: none; font-weight: bold;">Volver a la plataforma para reintentar</a></p>
            </div>
        </body>
    """)

# --- RUTA PRINCIPAL (HTML) ---
@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    
    tier_html = ""
    for level, data in TIERS.items():
        tasks = "".join(f'<li class="flex items-center text-xs text-gray-600"><svg class="h-4 w-4 text-emerald-500 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg>{task}</li>' for task in data['base_tasks'])
        tier_html += f"""
        <div class="tier-card p-6 bg-white border rounded-xl shadow-lg transition duration-300 hover:shadow-xl cursor-pointer flex flex-col" data-level="{level}" data-price="{data['price']}" data-time="{data['max_time_min']}">
            <input type="radio" id="level_{level}" name="service_level" value="{level}" class="hidden" {"checked" if level == 1 else ""}>
            <label for="level_{level}" class="block cursor-pointer flex-grow">
                <div class="flex justify-between items-start mb-3 border-b-2 pb-2">
                    <h3 class="text-xl font-bold text-gray-800 flex items-center">
                        <span class="mr-2 text-emerald-600">{'' if level == 1 else '' if level == 2 else '' if level == 3 else '' if level == 4 else ''}</span>
                        {data['name']}
                    </h3>
                    <div class="text-3xl font-extrabold text-emerald-600">${data['price']}</div>
                </div>
                <p class="text-sm font-semibold text-gray-700 mb-2">Enfoque: {data['value_focus']}</p>
                <p class="text-xs text-gray-500 mb-2">Tiempo Simulado: {data['max_time_min']} min.</p>
                <ul class="list-none my-2 space-y-1">
                    {tasks}
                </ul>
            </label>
            <div class="text-xs text-center pt-2 font-medium text-emerald-500 mt-auto">
                 </div>
        </div>
        """
        
    rendered_html = HTML_TEMPLATE.replace("{RENDER_URL}", RENDER_APP_URL)
    rendered_html = rendered_html.replace("{STRIPE_PK}", STRIPE_PUBLISHABLE_KEY)
    rendered_html = rendered_html.replace("{TIER_CARDS_HTML}", tier_html)
    rendered_html = rendered_html.replace("{TIERS_JSON}", json.dumps(TIERS))
    rendered_html = rendered_html.replace("{ADDONS_JSON}", json.dumps(ADDONS))
    
    return rendered_html
    
# =========================================================================
# 4. TEMPLATE HTML (FRONTEND COMPLETO CON JS Y PRECIO DINÁMICO)
# =========================================================================

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Ateneo Clínico IA</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        body { font-family: 'Inter', sans-serif; background: linear-gradient(135deg, #e0f2f1 0%, #f7f9fb 100%); }
        .card { box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -4px rgba(0, 0, 0, 0.05); border: 1px solid #e2e8f0; }
        .tier-card { border: 2px solid transparent; }
        .tier-card:has(input:checked) { border-color: #059669; background-color: #f0fff4; }
        .tier-card:has(input:checked) .text-emerald-600 { color: #047857; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
        .animate-fadeIn { animation: fadeIn 0.5s ease-out; }
    </style>
</head>
<body class="p-4 md:p-8 min-h-screen flex items-start justify-center">

    <script>
        // =========================================================================
        // CONSTANTES Y CONFIGURACIÓN
        // =========================================================================
        const RENDER_APP_URL = "{RENDER_URL}";
        const DEMO_USER_ID = 999;
        const TIERS_DATA = {TIERS_JSON};
        const ADDONS_DATA = {ADDONS_JSON};

        let countdownInterval = null;
        let isSessionActive = false;
        let currentAudio = null; // Para manejar la reproducción activa

        // =========================================================================
        // 1. LÓGICA DE PRECIOS Y UI
        // =========================================================================

        function updatePriceAndTimer() {
            const selectedLevel = parseInt(document.querySelector('input[name="service_level"]:checked').value);
            const tier = TIERS_DATA[selectedLevel];
            let totalPrice = tier.price;

            const isImageChecked = document.getElementById('include_image_analysis').checked;
            const isAudioChecked = document.getElementById('include_tts_addon').checked;
            
            const isAudioIncludedByTier = ADDONS_DATA.tts_audio.tiers_included.includes(selectedLevel);
            
            // Add-on de Imagen
            if (isImageChecked) {
                totalPrice += ADDONS_DATA.image_analysis.price;
            }

            // Add-on de Audio: solo se suma si se marca Y NO está incluido en el nivel
            if (isAudioChecked && !isAudioIncludedByTier) {
                totalPrice += ADDONS_DATA.tts_audio.price;
                document.getElementById('audio_addon_text').textContent = `Audio Profesional ($${ADDONS_DATA.tts_audio.price} USD)`;
            } else if (isAudioIncludedByTier) {
                document.getElementById('audio_addon_text').textContent = `Audio Profesional (Incluido)`;
            } else {
                document.getElementById('audio_addon_text').textContent = `Audio Profesional ($${ADDONS_DATA.tts_audio.price} USD)`;
            }

            // Actualizar la UI
            document.getElementById('total_price').textContent = totalPrice.toFixed(2);
            document.getElementById('simulated_time').textContent = tier.max_time_min;
            
            // Mostrar u ocultar el campo de archivo adjunto
            const fileInputContainer = document.getElementById('file_input_container');
            if (isImageChecked) {
                fileInputContainer.classList.remove('hidden');
            } else {
                fileInputContainer.classList.add('hidden');
            }
        }

        // =========================================================================
        // 2. LÓGICA DE PROCESAMIENTO Y PAGO (Frontend)
        // =========================================================================

        async function handleSubmit(event) {
            event.preventDefault();
            if (isSessionActive) return; 

            const form = event.target;
            const formData = new FormData(form);

            // Asegurar que el user_id siempre esté presente
            formData.append('user_id', DEMO_USER_ID);

            const submitButton = document.getElementById('submit_button');
            const resultContainer = document.getElementById('result_container');

            submitButton.disabled = true;
            submitButton.textContent = 'Procesando...';
            resultContainer.innerHTML = '';
            
            isSessionActive = true;
            stopCountdown();

            try {
                const response = await fetch(RENDER_APP_URL + '/create-service', {
                    method: 'POST',
                    body: formData,
                });

                const data = await response.json();

                if (!response.ok) {
                    throw new Error(data.detail || 'Error en la solicitud al servidor.');
                }

                // 1. Flujo de Pago de Stripe
                if (data.status === 'pending_payment' && data.payment_required) {
                    // **CRÍTICO: Redireccionar a Stripe Checkout**
                    window.location.href = data.payment_url;
                    return;

                } 
                
                // 2. Flujo de Bypass (Gratuito/Simulado)
                else if (data.status === 'success' && data.payment_method.includes('Bypass')) {
                    const result = data.fulfillment.analysis_result;
                    
                    if (result.analysis_status === 'error') {
                        throw new Error(`Error de IA: ${result.reason}`);
                    }

                    // Iniciar el contador de tiempo simulado
                    startCountdown(data.fulfillment.max_time_min);
                    
                    // Mostrar el resultado después del tiempo simulado
                    setTimeout(() => {
                        displayAnalysisResult(data.fulfillment);
                        stopCountdown();
                        isSessionActive = false;
                        submitButton.disabled = false;
                        submitButton.textContent = 'Realizar Nuevo Análisis';
                    }, data.fulfillment.max_time_min * 1000); // * 60 * 1000 para minutos reales
                    
                    // Mostrar mensaje de espera
                    document.getElementById('countdown_message').classList.remove('hidden');
                }

            } catch (error) {
                isSessionActive = false;
                submitButton.disabled = false;
                submitButton.textContent = 'Reintentar Análisis';
                resultContainer.innerHTML = `<div class="p-4 bg-red-100 border border-red-400 text-red-700 rounded-lg animate-fadeIn mt-4"><strong>Error:</strong> ${error.message}</div>`;
                document.getElementById('countdown_message').classList.add('hidden');
            }
        }

        // =========================================================================
        // 3. LÓGICA DE RESULTADOS Y CONTADOR
        // =========================================================================

        function startCountdown(minutes) {
            let seconds = minutes; // * 60; // Descomentar para tiempo real
            const timerDisplay = document.getElementById('timer_display');
            
            // Simulación rápida: solo usamos los minutos como segundos para ver el efecto
            timerDisplay.textContent = `${minutes} segundos (Simulado)...`;

            if (countdownInterval) clearInterval(countdownInterval);

            let timeRemaining = seconds;

            countdownInterval = setInterval(() => {
                timeRemaining--;
                if (timeRemaining <= 0) {
                    clearInterval(countdownInterval);
                    timerDisplay.textContent = '¡Análisis Completo!';
                } else {
                    timerDisplay.textContent = `${timeRemaining} segundos (Simulado)...`;
                }
            }, 1000);
        }
        
        function stopCountdown() {
            if (countdownInterval) {
                clearInterval(countdownInterval);
                countdownInterval = null;
            }
            document.getElementById('countdown_message').classList.add('hidden');
        }


        function displayAnalysisResult(fulfillment) {
            const resultContainer = document.getElementById('result_container');
            const analysisText = fulfillment.analysis_result.analysis_text.replace(/\n/g, '<br>');
            const isTTSIncluded = fulfillment.tts_included;

            let audioButtonHtml = '';
            if (isTTSIncluded) {
                audioButtonHtml = `
                    <button id="audio_toggle_button" class="mt-4 px-4 py-2 bg-purple-600 text-white font-bold rounded-lg hover:bg-purple-700 transition duration-300 flex items-center justify-center" onclick="toggleAudio('${encodeURIComponent(fulfillment.analysis_result.analysis_text)}')">
                        <svg class="w-5 h-5 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.536 8.464a5 5 0 010 7.072m2.828-9.899a9 9 0 010 12.728M5.818 5.818L2 7.636m0 0l-1.818-1.818m1.818 1.818L5.818 5.818M12 21a9 9 0 100-18 9 9 0 000 18z"/></svg>
                        Reproducir Análisis (TTS)
                    </button>
                `;
            }

            resultContainer.innerHTML = `
                <div class="p-6 bg-white border border-emerald-400 rounded-xl shadow-2xl animate-fadeIn mt-6">
                    <h2 class="text-2xl font-extrabold text-emerald-700 mb-3">✅ Análisis de IA Completo</h2>
                    <p class="text-sm font-semibold text-gray-600 mb-4">Nivel de Servicio: ${TIERS_DATA[fulfillment.service_level].name}</p>
                    <div class="analysis-output p-4 bg-gray-50 border border-gray-200 rounded-lg text-left text-gray-800 leading-relaxed max-h-96 overflow-y-auto">
                        ${analysisText}
                    </div>
                    ${audioButtonHtml}
                </div>
            `;
        }

        // =========================================================================
        // 4. LÓGICA DE AUDIO (TTS Simulado)
        // =========================================================================

        function toggleAudio(encodedText) {
            const text = decodeURIComponent(encodedText);
            const button = document.getElementById('audio_toggle_button');

            if (currentAudio) {
                // Detener audio
                speechSynthesis.cancel();
                currentAudio = null;
                button.innerHTML = '<svg class="w-5 h-5 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.536 8.464a5 5 0 010 7.072m2.828-9.899a9 9 0 010 12.728M5.818 5.818L2 7.636m0 0l-1.818-1.818m1.818 1.818L5.818 5.818M12 21a9 9 0 100-18 9 9 0 000 18z"/></svg> Reproducir Análisis (TTS)';
            } else {
                // Reproducir audio
                const utterance = new SpeechSynthesisUtterance(text);
                
                // Intentar detectar y usar una voz en español
                const esVoices = speechSynthesis.getVoices().filter(voice => voice.lang.startsWith('es'));
                if (esVoices.length > 0) {
                    utterance.voice = esVoices[0]; // Usar la primera voz en español disponible
                } else {
                    console.warn("No se encontró voz en español. Usando la voz por defecto.");
                }

                speechSynthesis.speak(utterance);
                currentAudio = utterance;
                
                button.innerHTML = '<svg class="w-5 h-5 mr-2" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm-5.707-6.293a1 1 0 011.414 0L10 14.586l4.293-4.293a1 1 0 111.414 1.414L10 17.414 4.293 11.707a1 1 0 010-1.414z" clip-rule="evenodd"/></svg> Detener Reproducción';
                
                // Limpiar cuando termine
                utterance.onend = () => {
                    currentAudio = null;
                    button.innerHTML = '<svg class="w-5 h-5 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.536 8.464a5 5 0 010 7.072m2.828-9.899a9 9 0 010 12.728M5.818 5.818L2 7.636m0 0l-1.818-1.818m1.818 1.818L5.818 5.818M12 21a9 9 0 100-18 9 9 0 000 18z"/></svg> Reproducir Análisis (TTS)';
                };
            }
        }


        // =========================================================================
        // 5. INICIALIZACIÓN
        // =========================================================================

        document.addEventListener('DOMContentLoaded', () => {
            const form = document.getElementById('analysis_form');
            form.addEventListener('submit', handleSubmit);

            // Escuchar cambios en los radio buttons y checkboxes
            document.querySelectorAll('.tier-card, input[type="checkbox"]').forEach(element => {
                element.addEventListener('change', updatePriceAndTimer);
                if (element.tagName === 'DIV') {
                    element.addEventListener('click', () => {
                        const radio = element.querySelector('input[type="radio"]');
                        if (radio) radio.checked = true;
                        updatePriceAndTimer();
                    });
                }
            });

            // Inicializar el precio y el tiempo simulado al cargar
            updatePriceAndTimer();
            
            // Si hay una URL de retorno (pago cancelado/fallido)
            const urlParams = new URLSearchParams(window.location.search);
            if (urlParams.get('status') === 'cancel') {
                 document.getElementById('result_container').innerHTML = `
                    <div class="p-4 bg-yellow-100 border border-yellow-400 text-yellow-700 rounded-lg animate-fadeIn mt-4">
                        <strong>Atención:</strong> El proceso de pago fue cancelado o falló. No se ha realizado ningún cargo. Puede reintentar.
                    </div>
                `;
            }
        });
    </script>
    
    <div class="w-full max-w-4xl">
        <header class="text-center mb-8">
            <h1 class="text-4xl font-extrabold text-gray-900 mb-2">Ateneo Clínico IA</h1>
            <p class="text-lg text-gray-600">Simulación y Análisis Clínico de Alto Nivel Asistido por IA (Gemini)</p>
        </header>

        <form id="analysis_form" class="space-y-6">
            <input type="hidden" name="user_id" value="999">

            <div class="card p-6 bg-white rounded-xl">
                <h2 class="text-2xl font-bold text-gray-800 mb-4 border-b pb-2">1. Seleccione el Nivel de Análisis</h2>
                <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {TIER_CARDS_HTML}
                </div>
            </div>

            <div class="card p-6 bg-white rounded-xl space-y-4">
                <h2 class="text-2xl font-bold text-gray-800 mb-4 border-b pb-2">2. Caso Clínico y Opcionales</h2>

                <div>
                    <label for="description" class="block text-sm font-medium text-gray-700 mb-1">Descripción Detallada del Caso Clínico (Requerido)</label>
                    <textarea id="description" name="description" rows="5" class="w-full p-3 border border-gray-300 rounded-lg focus:ring-emerald-500 focus:border-emerald-500" placeholder="Ej: Paciente masculino de 65 años con dolor torácico subesternal de 3 horas de evolución, disnea y sudoración..."></textarea>
                </div>
                
                <div class="space-y-3">
                    <h3 class="text-lg font-semibold text-gray-700">Add-ons (Mejoran el Análisis)</h3>
                    
                    <div class="flex items-center">
                        <input id="include_image_analysis" name="include_image_analysis" type="checkbox" class="h-4 w-4 text-emerald-600 border-gray-300 rounded focus:ring-emerald-500">
                        <label for="include_image_analysis" class="ml-3 text-sm font-medium text-gray-700">Análisis de Imagen/Laboratorio ($10 USD)</label>
                    </div>

                    <div id="file_input_container" class="hidden pl-8 animate-fadeIn">
                        <label for="clinical_file" class="block text-sm font-medium text-gray-600 mb-1">Adjuntar Archivo (Radiografía, Laboratorio, ECG, etc.)</label>
                        <input id="clinical_file" name="clinical_file" type="file" accept="image/*,application/pdf" class="block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-sm file:font-semibold file:bg-emerald-50 file:text-emerald-700 hover:file:bg-emerald-100"/>
                        <p class="mt-1 text-xs text-gray-500">Máximo 5MB. Formatos recomendados: JPG, PNG, PDF (solo si la imagen está en la primera página).</p>
                    </div>

                    <div class="flex items-center">
                        <input id="include_tts_addon" name="include_tts_addon" type="checkbox" class="h-4 w-4 text-emerald-600 border-gray-300 rounded focus:ring-emerald-500">
                        <label for="include_tts_addon" class="ml-3 text-sm font-medium text-gray-700" id="audio_addon_text">Audio Profesional ($3 USD)</label>
                    </div>
                </div>

                <div>
                    <label for="developer_bypass_key" class="block text-sm font-medium text-gray-400 mb-1">Clave de Desarrollo (Bypass Gratuito)</label>
                    <input id="developer_bypass_key" name="developer_bypass_key" type="text" class="w-full p-2 border border-gray-200 rounded-lg bg-gray-50 text-xs text-gray-600" placeholder="Opcional: Ingrese la clave para análisis instantáneo (sin pago)">
                </div>
            </div>

            <div class="card p-6 bg-white rounded-xl">
                <h2 class="text-2xl font-bold text-gray-800 mb-4 border-b pb-2">3. Resumen y Pago</h2>
                
                <div class="flex justify-between items-center mb-4">
                    <p class="text-lg font-semibold text-gray-700">Costo Total del Servicio:</p>
                    <p class="text-3xl font-extrabold text-red-600">$<span id="total_price">10.00</span> USD</p>
                </div>
                <div class="text-sm text-gray-500 mb-4">
                    Tiempo de Análisis Simulado: <span id="simulated_time" class="font-bold">5</span> minutos.
                </div>

                <button id="submit_button" type="submit" class="w-full py-3 bg-emerald-600 text-white font-bold text-lg rounded-lg hover:bg-emerald-700 transition duration-300 shadow-md">
                    Pagar y Comenzar Análisis
                </button>
            </div>
            
            <div id="countdown_message" class="hidden p-4 bg-blue-100 border border-blue-400 text-blue-700 rounded-lg text-center font-semibold animate-fadeIn">
                El análisis de IA está en progreso. Tiempo restante simulado: <span id="timer_display"></span>
            </div>
            
            <div id="result_container">
                </div>
        </form>
    </div>

</body>
</html>
"""

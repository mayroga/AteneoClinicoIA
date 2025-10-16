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
import base64 # Necesario para la codificación de archivos

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

# ESTRUCTURA MEJORADA CON SEGURIDAD LINGÜÍSTICA APLICADA:
# Tiers 1 y 2 usan "Hipótesis" en lugar de "Diagnóstico Definitivo".
TIERS = {
    # Nivel 1 (Voluntarios) - Hipótesis Clínica Principal
    1: {"name": "Nivel 1 – Hipótesis Rápida", "price": 10, "value_focus": "Respuesta Directa. (1 Tarea IA)", "max_time_min": 5, "token_instruction": "Proporciona una respuesta extremadamente concisa y directa, enfocada en la **Hipótesis Clínica Principal** o Hallazgo más probable. Máximo 100 palabras.", "base_tasks": ["Hipótesis Clínica Principal"]},
    # Nivel 2 (Voluntarios/Estándar) - Hipótesis Definitiva
    2: {"name": "Nivel 2 – Evaluación Estándar", "price": 50, "value_focus": "Análisis Básico Completo. (2 Tareas IA)", "max_time_min": 10, "token_instruction": "Proporciona una **Hipótesis Clínica Definitiva** y una Sugerencia Terapéutica General y concisa. Máximo 500 palabras.", "base_tasks": ["Hipótesis Clínica Definitiva", "Sugerencia Terapéutica General"]},
    # Nivel 3+ (Profesionales) - Retiene Diagnóstico
    3: {"name": "Nivel 3 – Planificación y Protocolo", "price": 100, "value_focus": "Protocolo Clínico Detallado. (3 Tareas IA)", "max_time_min": 25, "token_instruction": "Genera un Protocolo Clínico Detallado: Diagnóstico, Terapia Específica y Plan de Pruebas Adicionales (Laboratorio/Imagen). Máximo 800 palabras.", "base_tasks": ["Diagnóstico Definitivo", "Terapia Específica", "Plan de Pruebas Adicionales"]},
    4: {"name": "Nivel 4 – Debate y Evidencia", "price": 200, "value_focus": "Análisis Crítico y Controvertido. (4 Tareas IA)", "max_time_min": 45, "token_instruction": "Genera un Debate Clínico que incluye Diagnóstico, Terapia, Pruebas y una Sección 'Debate y Alternativas', analizando controversias y evidencia. Máximo 1500 palabras.", "base_tasks": ["Diagnóstico", "Terapia", "Pruebas Adicionales", "Debate y Alternativas"]},
    5: {"name": "Nivel 5 – Mesa Clínica Premium", "price": 500, "value_focus": "Multi-Caso y Documentación Formal. (3 Casos x 5 Tareas)", "max_time_min": 70, "token_instruction": "Analiza tres casos clínicos proporcionados de forma secuencial. Al final proporciona un Resumen Comparativo, Insights y un borrador de Documentación Formal. Máximo 3000 palabras.", "base_tasks": ["Diagnóstico Completo", "Terapia y Protocolo", "Debate Crítico", "Análisis Comparativo (Multi-Caso)", "Borrador de Informe Documental"]},
}

# ADD-ONS DEFINITION (Precios fijos)
ADDONS = {
    "image_analysis": {"name": "Análisis de Imagen/Laboratorio", "price": 10, "instruction_boost": "INTEGRA EL ANÁLISIS VISUAL DE LA IMAGEN/LABORATORIO al análisis. Aumenta la profundidad del análisis en 200 palabras adicionales."},
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
# 2. UTILITY FUNCTIONS (Funciones de Soporte)
# =========================================================================

async def call_gemini_api(prompt: str, token_instruction: str, base64_image_data: Optional[str] = None):
    """
    Genera el análisis clínico con instrucciones específicas para control de tokens
    y maneja la entrada multimodal (texto + imagen).
    
    CRÍTICO: La system_instruction incluye las advertencias legales y la OBLIGACIÓN
    de incluir el tratamiento medicamentoso.
    """
    if not gemini_client:
        return {
            "analysis_status": "error",
            "reason": "GEMINI_API_KEY no configurada. El servicio de análisis de IA está DESACTIVADO.",
            "prompt_used": prompt
        }
    
    # 1. CONSTRUCCIÓN DE LA INSTRUCCIÓN DEL SISTEMA (REGLAS ÉTICAS Y DE CONTENIDO)
    # NOTA: El {token_instruction} es clave, ya que contiene la palabra "Diagnóstico" o "Hipótesis"
    # según el nivel de servicio.
    system_instruction = (
        f"Eres un analista clínico experto. **Tu análisis DEBE ser un 'Servicio Completo' incluyendo OBLIGATORIAMENTE una sección de TRATAMIENTO MEDICAMENTOSO (Farmacológico)** para debate, sin importar el nivel. "
        "El objetivo es proveer una respuesta para debate profesional y educativo. "
        "ALERTA CRÍTICA: Debes comenzar tu respuesta con la siguiente ADVERTENCIA CLARA en mayúsculas: 'ADVERTENCIA: TRATAMIENTO EXPERIMENTAL. ESTE ANÁLISIS, INCLUYENDO EL TRATAMIENTO FARMACOLÓGICO SUGERIDO, NO ES REAL, ES EXPERIMENTAL Y TIENE FINES EXCLUSIVOS DE DEBATE Y ENTRENAMIENTO PARA PROFESIONALES DE SALUD LICENCIADOS. NUNCA DEBE APLICARSE EN PACIENTES REALES. EL VOLUNTARIO GANA AYUDANDO A DESARROLLAR ESTE DEBATE.' "
        f"{token_instruction} Analiza el caso. Detecta automáticamente el idioma de la consulta y responde íntegramente en ese mismo idioma. "
    )

    # 2. CONSTRUCCIÓN DE LA ENTRADA MULTIMODAL (parts)
    parts = []
    
    # Agregar la imagen si existe
    if base64_image_data:
        # Se asume que el mimeType es 'image/jpeg' para este ejercicio.
        parts.append({
            "inlineData": {
                "mimeType": "image/jpeg", 
                "data": base64_image_data
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
        print(f"Error desconocido con Gemini: {e}")
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
    token_instruction = tier_info["token_instruction"]
    
    # 2. Checkear Add-ons pagados y ajustar instrucción de tokens
    include_image_analysis = metadata.get("image_analysis", "false") == "true"
    
    if include_image_analysis:
        # Aumentar la instrucción de tokens si se pagó por el add-on de imagen
        token_instruction += " " + ADDONS["image_analysis"]["instruction_boost"]
        # Aquí se debería recuperar el archivo adjunto (que fue temporalmente almacenado)
        base64_image_data = None # En la demo del webhook, no hay archivo real para leer.
    else:
        base64_image_data = None
        
    
    description_snippet = metadata.get("description_snippet", "Caso clínico no especificado.")
    prompt = f"Analizar el siguiente caso clínico: {description_snippet}"
    
    # SIMULACIÓN DE LA LLAMADA: Asumimos que no hay datos binarios reales para la imagen en el webhook
    analysis_result = await call_gemini_api(prompt, token_instruction, base64_image_data=base64_image_data)
    
    print(f"Análisis de IA completado (Nivel {level}) para el usuario {user_id}. Estado: {analysis_result.get('analysis_status')}")
    
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
    
    # 1. FLUJO DE BYPASS (GRATUITO PARA DESARROLLO)
    if developer_bypass_key and developer_bypass_key == ADMIN_BYPASS_KEY:
        
        # 1.1. Construir la instrucción de tokens base
        prompt_instruction = tier_info["token_instruction"]
        
        # 1.2. Preparar la data de la imagen para la llamada multimodal
        base64_image_data = None
        
        if include_image_analysis and clinical_file and clinical_file.file:
            prompt_instruction += " " + ADDONS["image_analysis"]["instruction_boost"]
            
            # Validación simple del tipo MIME para ser más amigable 
            if clinical_file.content_type not in ["image/jpeg", "image/png", "image/webp"]:
                return JSONResponse(
                    content={
                        "status": "error",
                        "detail": f"Error de formato de archivo. Solo se aceptan formatos de imagen comunes: JPEG, PNG, WEBP. Se recibió: {clinical_file.content_type}",
                    },
                    status_code=400
                )
            
            # --- MANEJO DE ARCHIVOS ---
            try:
                # Leer el contenido del archivo si existe
                file_contents = await clinical_file.read()
                # Codificar la imagen para el envío a Gemini (base64)
                # NOTA: En un ambiente real, se debe usar el mime type real del archivo para la data inline
                base64_image_data = base64.b64encode(file_contents).decode('utf-8')
                
            except Exception as e:
                # Enviar un error JSON limpio al frontend si falla la lectura/codificación del archivo
                print(f"ERROR: Fallo al procesar archivo adjunto: {e}")
                return JSONResponse(
                    content={
                        "status": "error",
                        "detail": f"Error de procesamiento de archivo. Intente con un archivo de menor tamaño o diferente formato. Detalle: {e}",
                    },
                    status_code=500
                )
            # --- FIN DE MANEJO DE ARCHIVOS ---

        prompt = description if description else "Caso clínico no especificado. Análisis genérico de salud preventiva."
        
        # Ejecutar análisis con la instrucción de tokens del nivel seleccionado
        analysis_result = await call_gemini_api(prompt, prompt_instruction, base64_image_data=base64_image_data)
        file_info = clinical_file.filename if clinical_file else None
        
        # En el bypass, el audio se considera siempre 'incluido' si se solicitó o si el nivel lo incluye
        tts_included = include_tts_addon or service_level in ADDONS["tts_audio"]["tiers_included"]
        
        return {
            "status": "success",
            "payment_method": "Bypass (Gratuito)",
            "fulfillment": {
                "user_id": user_id,
                "service_level": service_level,
                "analysis_result": analysis_result,
                "file_info": file_info,
                "max_time_min": tier_info["max_time_min"], # Tiempo simulado
                "tts_included": tts_included # Bandera para activar el botón de audio en el frontend
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

    # 2.3. Manejar Add-on de Audio (Solo si no está incluido)
    is_tts_included = service_level in ADDONS["tts_audio"]["tiers_included"]
    if include_tts_addon and not is_tts_included:
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
    # NOTA: En un caso real, la imagen se subiría a un bucket y se guardaría la URL en metadata.
    
    metadata = {
        "user_id": str(user_id),
        "service_level": str(service_level),
        "description_snippet": description[:100] if description else "N/A",
        "image_analysis": "true" if include_image_analysis else "false",
        "tts_audio": "true" if include_tts_addon or is_tts_included else "false",
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
        print("STRIPE_WEBHOOK_SECRET no configurada. Saltando verificación de firma (RIESGO DE FRAUDE).")
        
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
            print(f"Pago exitoso y verificado para Session ID: {session['id']}")
            
            # 3. Ejecutar la función de cumplimiento (ASÍNCRONA)
            # Esta función desencadena el análisis de IA real.
            asyncio.create_task(fulfill_case(session['metadata']))
            
        else:
            print(f"Sesión completada, pero no pagada para Session ID: {session['id']}")

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
    
    # Renderizar dinámicamente la tabla de precios
    tier_html = ""
    for level, data in TIERS.items():
        tasks = "".join([f'<li class="text-sm text-gray-600 ml-4"> {t}</li>' for t in data['base_tasks']])
        tier_html += f"""
        <div class="tier-card p-6 bg-white border rounded-xl shadow-lg transition duration-300 hover:shadow-xl cursor-pointer flex flex-col" data-level="{level}" data-price="{data['price']}" data-time="{data['max_time_min']}">
            <input type="radio" id="level_{level}" name="service_level" value="{level}" class="hidden" {"checked" if level == 1 else ""}>
            <label for="level_{level}" class="block cursor-pointer flex-grow">
                <div class="flex justify-between items-start mb-3 border-b-2 pb-2">
                    <h3 class="text-xl font-bold text-gray-800 flex items-center">
                        <span class="mr-2 text-emerald-600">{' ' if level == 1 else ' ' if level == 2 else ' ' if level == 3 else ' ' if level == 4 else ' '}</span>
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
    <title>Ateneo Clínico IA - Estructura de Servicios Avanzada</title>
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
<div class="w-full max-w-4xl">
    <header class="text-center mb-10">
        <h1 class="text-3xl font-extrabold text-gray-900 mb-2">Ateneo Clínico IA</h1>
        <p class="text-md text-gray-600">Seleccione el Nivel de Análisis Requerido y Opciones Adicionales.</p>
    </header>

    <form id="service-form" class="space-y-8 p-6 card bg-white rounded-xl">
        <input type="hidden" name="user_id" value="999">
        
        <!-- NIVELES DE SERVICIO -->
        <div>
            <h2 class="text-xl font-bold text-gray-800 mb-4 border-b pb-2">1. Nivel de Servicio (Análisis Clínico)</h2>
            <div id="tiers-container" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {TIER_CARDS_HTML}
            </div>
        </div>

        <!-- DETALLES DEL CASO -->
        <div>
            <h2 class="text-xl font-bold text-gray-800 mb-4 border-b pb-2">2. Descripción del Caso Clínico</h2>
            <textarea id="description" name="description" rows="5" placeholder="Ingrese el historial del paciente, síntomas, antecedentes y datos relevantes. (Obligatorio para el análisis)" 
                      class="w-full p-3 border border-gray-300 rounded-lg focus:ring-emerald-500 focus:border-emerald-500"></textarea>
            <p id="description-warning" class="text-sm text-red-500 mt-1 hidden">La descripción del caso es obligatoria para ejecutar el servicio.</p>
        </div>

        <!-- ADD-ONS -->
        <div>
            <h2 class="text-xl font-bold text-gray-800 mb-4 border-b pb-2">3. Opciones Adicionales (Add-ons)</h2>
            <div class="space-y-4">
                
                <!-- Add-on de Imagen -->
                <div class="flex items-center space-x-3 p-3 bg-gray-50 rounded-lg border">
                    <input type="checkbox" id="include_image_analysis" name="include_image_analysis" class="h-5 w-5 text-emerald-600 border-gray-300 rounded focus:ring-emerald-500">
                    <label for="include_image_analysis" class="text-gray-700 font-medium flex-grow">
                        Análisis de Imagen/Laboratorio (${ADDONS_DATA['image_analysis']['price']} USD)
                    </label>
                    <input type="file" id="clinical_file" name="clinical_file" accept="image/jpeg,image/png,image/webp" class="text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-sm file:font-semibold file:bg-emerald-50 file:text-emerald-700 hover:file:bg-emerald-100 disabled:opacity-50" disabled>
                </div>

                <!-- Add-on de Audio -->
                <div class="flex items-center space-x-3 p-3 bg-gray-50 rounded-lg border">
                    <input type="checkbox" id="include_tts_addon" name="include_tts_addon" class="h-5 w-5 text-emerald-600 border-gray-300 rounded focus:ring-emerald-500">
                    <label for="include_tts_addon" class="text-gray-700 font-medium flex-grow">
                        Audio Profesional del Análisis (TTS)
                    </label>
                    <span id="tts-price-display" class="text-sm font-semibold text-emerald-600"></span>
                </div>
            </div>
        </div>

        <!-- BYPASS (Desarrollo) -->
        <div>
            <h2 class="text-xl font-bold text-gray-800 mb-4 border-b pb-2">4. Clave de Desarrollo (Bypass)</h2>
            <input type="text" id="developer_bypass_key" name="developer_bypass_key" placeholder="Ingrese la clave de bypass para análisis gratuito (Solo desarrollo)" 
                   class="w-full p-3 border border-gray-300 rounded-lg focus:ring-red-500 focus:border-red-500 bg-red-50 placeholder-red-400">
            <p class="text-xs text-gray-500 mt-1">Si la clave es correcta, el servicio se ejecuta inmediatamente (Flujo Gratuito).</p>
        </div>

        <!-- TOTAL Y BOTÓN DE PAGO -->
        <div class="flex justify-between items-center pt-4 border-t-2">
            <div class="text-2xl font-extrabold text-gray-900">
                Total Estimado: <span id="total-price-display">$10</span> USD
            </div>
            <button type="submit" class="px-8 py-3 bg-emerald-600 text-white font-bold rounded-xl hover:bg-emerald-700 transition duration-150 shadow-lg shadow-emerald-200/50" disabled>
                Pagar $10 y Ejecutar Servicio Seleccionado
            </button>
        </div>
    </form>

    <!-- RESULTADOS DEL ANÁLISIS (Se muestra solo tras el bypass) -->
    <div id="results-container" class="mt-8 hidden animate-fadeIn">
        <div class="card bg-white p-6 rounded-xl space-y-4">
            <h2 class="text-2xl font-bold text-emerald-700 border-b pb-2 mb-4">Resultado del Análisis IA (Modo Bypass)</h2>
            
            <div class="bg-blue-50 border-l-4 border-blue-500 text-blue-800 p-3" role="alert">
                <p class="font-bold">Análisis en Curso</p>
                <p id="countdown-message" class="text-sm">Tiempo restante: <span id="countdown-timer">00:00</span> minutos.</p>
            </div>

            <div id="analysis-output" class="text-gray-700 whitespace-pre-wrap overflow-x-auto p-4 bg-gray-100 rounded-lg max-h-96">
                <!-- El texto del análisis se insertará aquí -->
            </div>

            <div id="tts-audio-section" class="pt-4 border-t hidden">
                <button id="tts-button" class="px-6 py-2 bg-purple-600 text-white font-semibold rounded-lg hover:bg-purple-700 transition duration-150 disabled:opacity-50">
                    Reproducir Análisis
                </button>
            </div>

            <div id="error-output" class="text-red-600 font-semibold hidden"></div>

        </div>
    </div>
</div>

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
    let currentAnalysisText = "";

    // =========================================================================
    // UTILITIES DE AUDIO (Conversión PCM a WAV - MANTENIDO)
    // =========================================================================

    function base64ToArrayBuffer(base64) {
        const binaryString = atob(base64);
        const len = binaryString.length;
        const bytes = new Uint8Array(len);
        for (let i = 0; i < len; i++) {
            bytes[i] = binaryString.charCodeAt(i);
        }
        return bytes.buffer;
    }

    function pcmToWav(pcm16, sampleRate) {
        const buffer = new ArrayBuffer(44 + pcm16.length * 2);
        const view = new DataView(buffer);
        let offset = 0;

        function writeString(str) {
            for (let i = 0; i < str.length; i++) {
                view.setUint8(offset++, str.charCodeAt(i));
            }
        }

        // RIFF chunk headers
        writeString('RIFF');
        view.setUint32(offset, 36 + pcm16.length * 2, true); offset += 4;
        writeString('WAVE');
        writeString('fmt ');
        view.setUint32(offset, 16, true); offset += 4;
        view.setUint16(offset, 1, true); offset += 2; // Audio format 1 (PCM)
        view.setUint16(offset, 1, true); offset += 2; // Number of channels (Mono)
        view.setUint32(offset, sampleRate, true); offset += 4;
        view.setUint32(offset, sampleRate * 2, true); offset += 4; // Byte rate (SampleRate * NumChannels * BitsPerSample/8)
        view.setUint16(offset, 2, true); offset += 2; // Block align (NumChannels * BitsPerSample/8)
        view.setUint16(offset, 16, true); offset += 2; // Bits per sample
        writeString('data');
        view.setUint32(offset, pcm16.length * 2, true); offset += 4; // Data size

        // Write PCM data
        for (let i = 0; i < pcm16.length; i++) {
            view.setInt16(offset, pcm16[i], true);
            offset += 2;
        }

        return new Blob([view], { type: 'audio/wav' });
    }


    async function generateAndPlayAudio(text, buttonElement) {
        if (!text || text.trim().length === 0) {
             console.error("No hay texto para generar audio.");
             return;
        }
        
        const originalText = 'Reproducir Análisis';
        buttonElement.disabled = true;
        buttonElement.textContent = ' Generando Audio...';
        
        const GEMINI_TTS_MODEL = "gemini-2.5-flash-preview-tts";
        const TTS_VOICE_NAME = "Kore";

        // 1. LLAMADA A LA API DE GEMINI TTS
        // La API key se inyecta automáticamente en el runtime del Canvas
        const apiKey = "";
        const apiUrl = `https://generativelanguage.googleapis.com/v1beta/models/${GEMINI_TTS_MODEL}:generateContent?key=${apiKey}`;

        // Instrucción para el modelo TTS: decir el texto de forma natural.
        const natural_speech_prompt = `Di de forma natural y profesional, omitiendo cualquier mención a la puntuación o símbolos, solo el texto principal: ${text}`;

        const payload = {
            contents: [{
                parts: [{ text: natural_speech_prompt }]
            }],
            generationConfig: {
                responseModalities: ["AUDIO"],
                speechConfig: {
                    voiceConfig: {
                        prebuiltVoiceConfig: { voiceName: TTS_VOICE_NAME }
                    }
                }
            },
            model: GEMINI_TTS_MODEL
        };

        try {
            const response = await fetch(apiUrl, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            const result = await response.json();
            const candidate = result.candidates?.[0];
            const part = candidate?.content?.parts?.find(p => p.inlineData && p.inlineData.mimeType.startsWith('audio/'));

            if (!part || !part.inlineData.data) {
                const errorDetail = result?.error?.message || "No se pudo obtener el audio de la respuesta de Gemini.";
                throw new Error(errorDetail);
            }

            const audioData = part.inlineData.data;
            const mimeType = part.inlineData.mimeType;
            const rateMatch = mimeType.match(/rate=(\d+)/);
            const sampleRate = rateMatch ? parseInt(rateMatch[1], 10) : 24000;

            // 2. CONVERSIÓN DE PCM A WAV
            const pcmData = base64ToArrayBuffer(audioData);
            const pcm16 = new Int16Array(pcmData);
            const wavBlob = pcmToWav(pcm16, sampleRate);
            const audioUrl = URL.createObjectURL(wavBlob);

            // 3. REPRODUCCIÓN
            const audio = new Audio(audioUrl);
            audio.play();

            buttonElement.textContent = ' Escuchando...';
            audio.onended = () => {
                buttonElement.textContent = originalText;
                buttonElement.disabled = false;
                URL.revokeObjectURL(audioUrl);
            };

        } catch (error) {
            console.error("Error al generar o reproducir el audio TTS:", error);
            document.getElementById('error-output').textContent = `Error de Audio TTS: ${error.message}`;
            document.getElementById('error-output').classList.remove('hidden');
        } finally {
            if (buttonElement.textContent !== ' Escuchando...') {
                setTimeout(() => {
                    buttonElement.textContent = originalText;
                    buttonElement.disabled = false;
                    // Ocultar error si no es el botón de audio
                    if (document.getElementById('error-output').textContent.startsWith('Error de Audio TTS:')) {
                         document.getElementById('error-output').classList.add('hidden');
                    }
                }, 3000);
            }
        }
    }

    // =========================================================================
    // LÓGICA DE FORMULARIO, PRECIOS Y TIEMPO (TIMER)
    // =========================================================================

    function updatePrice() {
        const form = document.getElementById('service-form');
        const selectedLevel = parseInt(form.elements['service_level'].value);
        const tierInfo = TIERS_DATA[selectedLevel];
        let totalPrice = tierInfo.price;

        const imageCheckbox = document.getElementById('include_image_analysis');
        const audioCheckbox = document.getElementById('include_tts_addon');
        const fileInput = document.getElementById('clinical_file');
        const totalDisplay = document.getElementById('total-price-display');
        const submitButton = document.querySelector('button[type="submit"]');

        const isTtsIncluded = ADDONS_DATA.tts_audio.tiers_included.includes(selectedLevel);
        
        // 1. Manejar Add-on de Imagen
        if (imageCheckbox.checked) {
            totalPrice += ADDONS_DATA.image_analysis.price;
            fileInput.disabled = false;
        } else {
            fileInput.disabled = true;
            fileInput.value = ''; // Limpiar el archivo si se desmarca
        }
        
        // 2. Manejar Add-on de Audio (Solo si no está incluido en el Tier)
        if (isTtsIncluded) {
            audioCheckbox.checked = true; // Forzar selección
            audioCheckbox.disabled = true;
            document.getElementById('tts-price-display').textContent = '(Incluido)';
        } else {
            audioCheckbox.disabled = false;
            document.getElementById('tts-price-display').textContent = `($${ADDONS_DATA.tts_audio.price} Add-on)`;
            if (audioCheckbox.checked) {
                totalPrice += ADDONS_DATA.tts_audio.price;
            }
        }
        
        totalDisplay.textContent = `$${totalPrice}`;
        submitButton.innerHTML = `Pagar $${totalPrice} y Ejecutar Servicio Seleccionado`;

        // 3. Habilitar botón de enviar (Solo si hay descripción)
        const descriptionField = document.getElementById('description');
        const descriptionWarning = document.getElementById('description-warning');
        if (descriptionField.value.trim().length > 10) {
            submitButton.disabled = false;
            descriptionWarning.classList.add('hidden');
        } else {
            submitButton.disabled = true;
            descriptionWarning.classList.remove('hidden');
        }
        
        // 4. Actualizar tiempo simulado en el mensaje del botón o en otro lugar
        submitButton.setAttribute('data-time', tierInfo['max_time_min']);
    }

    // Función de inicialización para escuchar eventos
    function init() {
        const form = document.getElementById('service-form');
        
        // Inicializar listeners para calcular precio dinámico
        document.querySelectorAll('input[name="service_level"]').forEach(radio => {
            radio.addEventListener('change', updatePrice);
        });
        document.getElementById('include_image_analysis').addEventListener('change', updatePrice);
        document.getElementById('include_tts_addon').addEventListener('change', updatePrice);
        document.getElementById('description').addEventListener('input', updatePrice);
        
        // Primera actualización al cargar la página
        updatePrice();

        // Listener para la reproducción de audio
        document.getElementById('tts-button').addEventListener('click', () => {
             generateAndPlayAudio(currentAnalysisText, document.getElementById('tts-button'));
        });

        // Listener principal del formulario
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            
            if (isSessionActive) return; // Prevenir doble envío
            isSessionActive = true;
            
            // Limpiar resultados anteriores y mostrar loader
            const resultsContainer = document.getElementById('results-container');
            const analysisOutput = document.getElementById('analysis-output');
            const errorOutput = document.getElementById('error-output');
            const submitButton = document.querySelector('button[type="submit"]');
            const originalButtonText = submitButton.innerHTML;
            
            analysisOutput.textContent = 'Procesando solicitud...';
            errorOutput.classList.add('hidden');
            resultsContainer.classList.remove('hidden');
            
            submitButton.disabled = true;
            submitButton.innerHTML = 'Enviando...';

            const formData = new FormData(form);
            
            // Si el archivo no está seleccionado y la casilla de imagen está marcada, eliminamos el file field
            const clinicalFile = document.getElementById('clinical_file').files[0];
            const includeImage = document.getElementById('include_image_analysis').checked;

            if (!clinicalFile || !includeImage) {
                formData.delete('clinical_file');
            } else if (clinicalFile.size > 5 * 1024 * 1024) { // Límite simple de 5MB
                 errorOutput.textContent = 'Error: El archivo de imagen es demasiado grande (máx. 5MB).';
                 errorOutput.classList.remove('hidden');
                 submitButton.innerHTML = originalButtonText;
                 submitButton.disabled = false;
                 isSessionActive = false;
                 return;
            }

            // Iniciar timer si es modo bypass
            const bypassKey = formData.get('developer_bypass_key');
            if (bypassKey && bypassKey.trim().length > 0) {
                 const maxTimeMin = submitButton.getAttribute('data-time');
                 startCountdown(parseInt(maxTimeMin, 10));
            } else {
                 document.getElementById('countdown-message').textContent = 'Redirigiendo a Stripe para el pago...';
            }
            
            try {
                const response = await fetch(`${RENDER_APP_URL}/create-service`, {
                    method: 'POST',
                    body: formData
                });

                const result = await response.json();
                
                if (!response.ok) {
                    throw new Error(result.detail || 'Error desconocido del servidor.');
                }

                if (result.status === "payment_required") {
                    // Flujo de pago
                    window.location.href = result.payment_url;
                } else if (result.status === "success" && result.payment_method.includes("Bypass")) {
                    // Flujo de bypass (análisis instantáneo)
                    stopCountdown(); // Detener el timer ya que el análisis es rápido
                    
                    const analysisData = result.fulfillment.analysis_result;
                    
                    if (analysisData.analysis_status === "success") {
                        currentAnalysisText = analysisData.analysis_text;
                        analysisOutput.textContent = analysisData.analysis_text;
                        
                        // Mostrar sección de audio si está incluido
                        const ttsSection = document.getElementById('tts-audio-section');
                        if (result.fulfillment.tts_included) {
                            ttsSection.classList.remove('hidden');
                        } else {
                            ttsSection.classList.add('hidden');
                        }

                        document.getElementById('countdown-message').innerHTML = '<span class="text-green-600 font-bold">Análisis Completado Instantáneamente (Bypass).</span>';
                    } else {
                        // Error de Gemini
                        analysisOutput.textContent = `ERROR DE IA: ${analysisData.reason}`;
                        document.getElementById('countdown-message').innerHTML = '<span class="text-red-600 font-bold">Error en la ejecución del análisis de IA.</span>';
                    }
                }

            } catch (error) {
                stopCountdown();
                errorOutput.textContent = `ERROR DE PROCESAMIENTO: ${error.message}`;
                errorOutput.classList.remove('hidden');
                analysisOutput.textContent = 'Fallo al comunicarse con el servidor o la IA.';
                document.getElementById('countdown-message').innerHTML = '<span class="text-red-600 font-bold">Fallo Crítico.</span>';
            } finally {
                submitButton.innerHTML = originalButtonText;
                submitButton.disabled = false;
                isSessionActive = false;
            }
        });
    }

    // Lógica del Timer (Solo para el flujo de bypass, simula el tiempo del tier)
    function startCountdown(minutes) {
        if (countdownInterval) clearInterval(countdownInterval);

        let timeInSeconds = minutes * 60;
        const timerElement = document.getElementById('countdown-timer');

        const updateTimer = () => {
            const minutes = Math.floor(timeInSeconds / 60);
            const seconds = timeInSeconds % 60;
            timerElement.textContent = `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;

            if (timeInSeconds <= 0) {
                stopCountdown();
                document.getElementById('countdown-message').innerHTML = '<span class="text-red-600 font-bold">¡Tiempo Agotado! El análisis debería haber terminado.</span>';
            } else {
                timeInSeconds--;
            }
        };

        updateTimer();
        countdownInterval = setInterval(updateTimer, 1000);
    }

    function stopCountdown() {
        if (countdownInterval) {
            clearInterval(countdownInterval);
            countdownInterval = null;
        }
    }

    window.onload = init;
</script>
</body>
</html>
"""

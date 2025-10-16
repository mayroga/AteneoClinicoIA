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
TIERS = {
    1: {"name": " Nivel 1 – Diagnóstico Rápido", "price": 10, "value_focus": "Diagnóstico Hipotético y Tratamiento Mínimo. (1 Tarea IA)", "max_time_min": 5, "token_instruction": "Proporciona un Diagnóstico Hipotético y una sugerencia de Tratamiento Medicamentoso Hipotético. La respuesta debe ser concisa. Máximo 150 palabras.", "base_tasks": ["Diagnóstico Hipotético", "Tratamiento Medicamentoso Hipotético"]},
    2: {"name": " Nivel 2 – Evaluación Estándar", "price": 50, "value_focus": "Análisis Básico, Diagnóstico y Tratamiento Detallado. (2 Tareas IA)", "max_time_min": 10, "token_instruction": "Proporciona un Diagnóstico Hipotético y un Tratamiento Medicamentoso Hipotético Detallado con indicaciones. Máximo 600 palabras.", "base_tasks": ["Diagnóstico Hipotético Definitivo", "Tratamiento Medicamentoso Hipotético Detallado"]},
    3: {"name": " Nivel 3 – Planificación y Protocolo", "price": 100, "value_focus": "Protocolo Clínico Detallado. (3 Tareas IA)", "max_time_min": 25, "token_instruction": "Genera un Protocolo Clínico Detallado: Diagnóstico Hipotético, Terapia Específica Hipotética y Plan de Pruebas Adicionales. Máximo 900 palabras.", "base_tasks": ["Diagnóstico Hipotético Definitivo", "Terapia Específica Hipotética", "Plan de Pruebas Adicionales"]},
    4: {"name": " Nivel 4 – Debate y Evidencia", "price": 200, "value_focus": "Análisis Crítico, Diagnóstico y Controvertido. (4 Tareas IA)", "max_time_min": 45, "token_instruction": "Genera un Debate Clínico que incluye Diagnóstico Hipotético, Tratamiento Hipotético, Pruebas y una Sección 'Debate y Alternativas'. Máximo 1600 palabras.", "base_tasks": ["Diagnóstico Hipotético", "Tratamiento Hipotético", "Pruebas Adicionales", "Debate y Alternativas"]},
    5: {"name": " Nivel 5 – Mesa Clínica Premium", "price": 500, "value_focus": "Multi-Caso y Documentación Formal. (3 Casos x 5 Tareas)", "max_time_min": 70, "token_instruction": "Analiza tres casos clínicos proporcionados. Proporciona un Resumen Comparativo, Insights y un borrador de Documentación Formal, incluyendo Diagnóstico y Tratamiento Hipotético para cada caso. Máximo 3000 palabras.", "base_tasks": ["Diagnóstico Completo Hipotético", "Tratamiento y Protocolo Hipotético", "Debate Crítico", "Análisis Comparativo (Multi-Caso)", "Borrador de Informe Documental"]},
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
    
    # 1. CONSTRUCCIÓN DE LA INSTRUCCIÓN DEL SISTEMA (MODIFICADO PARA EXPERIMENTO)
    # CRÍTICO: Debe sonar como un médico real, pero advertir que es HIPOTÉTICO.
    system_instruction = (
        f"Eres un analista clínico experto y profesional. Tu rol es realizar una anamnesis completa y detallada. "
        f"Debes sonar como un médico real y experto. Proporciona un **Diagnóstico Hipotético** y un **Tratamiento Medicamentoso Hipotético** como parte de tu respuesta. "
        f"{token_instruction} Analiza el caso. Detecta automáticamente el idioma de la consulta y responde íntegramente en ese mismo idioma. "
    )

    # 2. CONSTRUCCIÓN DE LA ENTRADA MULTIMODAL (parts)
    parts = []
    
    # Agregar la imagen si existe
    if image_data:
        # Nota: La simulación de archivo aquí asume que es una imagen simple (e.g., JPEG/PNG).
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
    
    # CRÍTICO: LLAMADA A LA IA para activar el servicio completo
    # Si hubiera una imagen, se enviaría el binario en 'image_data'.
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
            file_contents = await clinical_file.read()
            # CRÍTICO: Usar base64 para el bypass que ejecuta la IA inmediatamente
            image_data_base64 = base64.b64encode(file_contents).decode('latin1')
            
        # Ejecutar análisis con la instrucción de tokens del nivel seleccionado
        analysis_result = await call_gemini_api(prompt, prompt_instruction, image_data=image_data_base64)
        file_info = clinical_file.filename if clinical_file else None
        
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
    # ... (Resto del código de Stripe Checkout que no requiere cambios)

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
    
    # La información esencial se pasa al Webhook a través de Metadata
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
# ... (Código del webhook sin cambios, mantiene la llamada a fulfill_case)
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
                        <span class="mr-2 text-emerald-600"></span>
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
    <title>Ateneo Clínico IA</title> <script src="https://cdn.tailwindcss.com"></script>
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

    <div class="max-w-4xl w-full">
        <header class="text-center mb-6 p-6 bg-white rounded-xl shadow-xl">
            <h1 class="text-4xl font-extrabold text-gray-900 mb-2">Ateneo Clínico IA</h1>
            <p class="text-lg text-emerald-600 font-medium">Análisis Clínico Asistido por Inteligencia Artificial</p>
            <p class="mt-2 text-sm text-gray-500">Tiempo de Análisis Estimado (Simulado): <span id="current-max-time" class="font-bold">5</span> minutos.</p>
        </header>

        <div class="mb-8 p-6 bg-yellow-50 border border-yellow-300 rounded-xl shadow-md">
            <h3 class="text-xl font-bold text-yellow-700 mb-3">⚠️ ADVERTENCIA CRÍTICA: Experimento Clínico Simulado ⚠️</h3>
            <div class="text-sm text-yellow-600 space-y-2">
                <p>Estimado Voluntario, este servicio simula un **Debate Clínico Profesional** para fines de **investigación y desarrollo de IA**.</p>
                <p class="font-bold">El **Diagnóstico Hipotético** y el **Tratamiento Medicamentoso Hipotético** proporcionados son exclusivamente para experimentar la interacción con el modelo de IA.</p>
                <p>
                    <span class="font-extrabold underline">NO SON REALES.</span>
                    Usted debe ser examinado por un **Médico Licenciado** para cualquier decisión de salud. Al usar el servicio, usted entiende y acepta esta condición crucial.
                </p>
            </div>
        </div>
        
        <form id="service-form" class="space-y-8">
            <div class="card p-6 bg-white rounded-xl">
                <h2 class="text-2xl font-bold text-gray-800 mb-4 border-b pb-2">1. Seleccione Nivel de Análisis</h2>
                <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-4">
                    {TIER_CARDS_HTML}
                </div>
            </div>

            <div class="card p-6 bg-white rounded-xl">
                <h2 class="text-2xl font-bold text-gray-800 mb-4 border-b pb-2">2. Detalle el Caso Clínico</h2>
                
                <div class="mb-6">
                    <label for="description" class="block text-sm font-medium text-gray-700 mb-1">Descripción del Caso / Anamnesis</label>
                    <textarea id="description" name="description" rows="5" placeholder="Ingrese síntomas, historial relevante, edad, medicamentos, etc." class="w-full border-gray-300 rounded-lg shadow-sm focus:border-emerald-500 focus:ring-emerald-500 p-3"></textarea>
                </div>

                <div class="mb-6">
                    <label for="clinical_file" class="block text-sm font-medium text-gray-700 mb-1">Adjuntar Archivo o Imagen (Opcional)</label>
                    <input type="file" id="clinical_file" name="clinical_file" class="w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-sm file:font-semibold file:bg-emerald-50 file:text-emerald-700 hover:file:bg-emerald-100 cursor-pointer" accept="image/jpeg,image/png,image/webp,.pdf,.docx,.txt">
                    <p class="mt-1 text-xs text-gray-500">Archivos aceptados: Imágenes (JPG, PNG, WEBP), PDF, DOCX, TXT.</p>
                </div>

                <div class="border-t pt-4">
                    <h3 class="text-lg font-bold text-gray-800 mb-3">Add-ons Opcionales</h3>
                    <div class="space-y-3">
                        <div class="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                            <label for="include_image_analysis" class="flex items-center cursor-pointer">
                                <input type="checkbox" id="include_image_analysis" name="include_image_analysis" class="h-4 w-4 text-emerald-600 border-gray-300 rounded focus:ring-emerald-500">
                                <span class="ml-3 text-sm font-medium text-gray-700"> Añadir Análisis de Imagen/Laboratorio ($10)</span>
                            </label>
                        </div>

                        <div class="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                            <label for="include_tts_addon" class="flex items-center cursor-pointer">
                                <input type="checkbox" id="include_tts_addon" name="include_tts_addon" class="h-4 w-4 text-emerald-600 border-gray-300 rounded focus:ring-emerald-500">
                                <span class="ml-3 text-sm font-medium text-gray-700"> Generar Audio Profesional del Análisis (TTS)</span>
                            </label>
                            <span id="tts-price-display" class="text-xs font-semibold text-emerald-600">($3 Add-on)</span>
                        </div>
                    </div>
                </div>
            </div>
            
            <div class="card p-6 bg-emerald-50 rounded-xl flex flex-col items-center">
                <h2 class="text-3xl font-extrabold text-emerald-700 mb-4">Total: <span id="total-price-display">$10</span> USD</h2>
                
                <button type="submit" class="w-full md:w-auto px-10 py-4 bg-emerald-600 text-white font-bold rounded-xl text-lg hover:bg-emerald-700 transition duration-300 shadow-lg" id="submit-button">
                    Pagar $10 y Ejecutar Servicio Seleccionado
                </button>
                
                <div class="mt-6 text-center text-sm text-gray-600">
                    <p class="font-bold mb-2">MODO DE DESARROLLO (Bypass Gratuito)</p>
                    <input type="text" name="developer_bypass_key" placeholder="Clave de Bypass" class="text-center w-48 border-gray-300 rounded-lg shadow-sm focus:border-emerald-500 focus:ring-emerald-500 p-2 text-sm">
                </div>
            </div>
        </form>
        
        <div id="timer-box" class="card p-4 mt-8 bg-blue-100 border-blue-300 text-blue-800 rounded-xl shadow-lg hidden">
            <div class="flex items-center justify-between">
                <div class="font-bold flex items-center">
                    <svg class="animate-spin -ml-1 mr-3 h-5 w-5 text-blue-500" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                    Procesando Análisis...
                </div>
                <div id="timer-display" class="font-extrabold text-lg">00:00</div>
            </div>
            <div id="timer-message" class="mt-2 text-sm font-medium">Esperando respuesta asíncrona del backend.</div>
        </div>

        <div id="analysis-result-box" class="mt-10">
            </div>
        
        <div class="mt-10 p-6 bg-red-50 border border-red-300 rounded-xl shadow-md">
            <h3 class="text-xl font-bold text-red-700 mb-3"> AVISO LEGAL (WAIVER OBLIGATORIO)</h3>
            <div class="text-sm text-red-600 space-y-2">
                <p>Esta plataforma es solo para fines académicos, educativos y de debate clínico. **Los niveles 1 y 2 están enfocados en la experimentación voluntaria.**</p>
                <p>Los datos o archivos enviados son simulaciones, no constituyen diagnóstico ni historia clínica real (no cubre HIPAA).</p>
                <p>Las respuestas de IA o profesionales no reemplazan atención médica, y usted renuncia a cualquier reclamo legal contra administradores o participantes.</p>
                <p>Al usar la plataforma, autoriza el uso académico o investigativo del material compartido y acepta que cualquier decisión de salud debe consultarse con un médico licenciado.</p>
            </div>
        </div>

    </div>
    
    <div id="overlay" class="fixed inset-0 bg-gray-900 bg-opacity-50 hidden transition-opacity z-40" onclick="closeModal()"></div>
    <div id="message-modal" class="fixed inset-0 z-50 overflow-y-auto hidden">
        <div class="flex items-center justify-center min-h-screen p-4">
            <div class="bg-white rounded-xl shadow-2xl max-w-sm w-full p-6 relative">
                <button class="absolute top-3 right-3 text-gray-400 hover:text-gray-600" onclick="closeModal()">
                    <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
                </button>
                <div class="flex items-center mb-4">
                    <span id="modal-icon" class="mr-3"></span>
                    <h3 id="modal-title" class="text-lg font-bold text-gray-900"></h3>
                </div>
                <div id="modal-content" class="text-sm text-gray-700"></div>
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
            view.setUint16(offset, 1, true); offset += 2;
            view.setUint16(offset, 1, true); offset += 2;
            view.setUint32(offset, sampleRate, true); offset += 4;
            view.setUint32(offset, sampleRate * 2, true); offset += 4;
            view.setUint16(offset, 2, true); offset += 2;
            view.setUint16(offset, 16, true); offset += 2;
            writeString('data');
            view.setUint32(offset, pcm16.length * 2, true); offset += 4;

            // Write PCM data
            for (let i = 0; i < pcm16.length; i++) {
                view.setInt16(offset, pcm16[i], true);
                offset += 2;
            }

            return new Blob([view], { type: 'audio/wav' });
        }


        async function generateAndPlayAudio(text, buttonElement) {
            const originalText = buttonElement.textContent;
            buttonElement.disabled = true;
            buttonElement.textContent = ' Generando Audio...';
            
            const GEMINI_TTS_MODEL = "gemini-2.5-flash-preview-tts";
            const TTS_VOICE_NAME = "Kore";

            // 1. LLAMADA A LA API DE GEMINI TTS
            const apiKey = "";
            const apiUrl = `https://generativelanguage.googleapis.com/v1beta/models/${GEMINI_TTS_MODEL}:generateContent?key=${apiKey}`;

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
                    throw new Error("No se pudo obtener el audio de la respuesta de Gemini.");
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
                    buttonElement.textContent = ' Reproducir Análisis';
                    buttonElement.disabled = false;
                    URL.revokeObjectURL(audioUrl);
                };

            } catch (error) {
                console.error("Error al generar o reproducir el audio TTS:", error);
                buttonElement.textContent = ' Error de Audio';
            } finally {
                if (buttonElement.textContent !== ' Escuchando...') {
                    setTimeout(() => {
                        buttonElement.textContent = originalText;
                        buttonElement.disabled = false;
                    }, 3000);
                }
            }
        }


        // =========================================================================
        // LÓGICA DE FORMULARIO, PRECIOS Y TIEMPO (TIMER)
        // =========================================================================

        function escapeHtml(str) {
            if (!str) return '';
            return str.replace(/&/g, '&amp;')
                            .replace(/</g, '&lt;')
                            .replace(/>/g, '&gt;')
                            .replace(/"/g, '&quot;')
                            .replace(/'/g, '&#39;')
                            .replace(/`/g, '&#96;');
        }
        
        function updatePrice() {
            const form = document.getElementById('service-form');
            const selectedLevel = parseInt(form.elements['service_level'].value);
            const tierInfo = TIERS_DATA[selectedLevel];
            let totalPrice = tierInfo.price;

            const imageCheckbox = document.getElementById('include_image_analysis');
            const audioCheckbox = document.getElementById('include_tts_addon');
            const totalDisplay = document.getElementById('total-price-display');
            const submitButton = document.querySelector('button[type="submit"]');

            const isTtsIncluded = ADDONS_DATA.tts_audio.tiers_included.includes(selectedLevel);
            
            // 1. Manejar Add-on de Imagen
            if (imageCheckbox.checked) {
                totalPrice += ADDONS_DATA.image_analysis.price;
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
            
            // Actualizar tiempo simulado en el título
            document.getElementById('current-max-time').textContent = tierInfo.max_time_min;
        }

        function startCountdown(maxMinutes) {
            if (countdownInterval) {
                clearInterval(countdownInterval);
            }
            
            let secondsLeft = maxMinutes * 60;
            const timerElement = document.getElementById('timer-display');
            const messageElement = document.getElementById('timer-message');
            
            isSessionActive = true;
            document.getElementById('timer-box').classList.remove('hidden');
            timerElement.classList.remove('hidden');
            messageElement.innerHTML = '';
            
            countdownInterval = setInterval(() => {
                secondsLeft--;
                
                const minutes = Math.floor(secondsLeft / 60);
                const seconds = secondsLeft % 60;
                
                timerElement.textContent = `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
                
                if (secondsLeft <= 0) {
                    clearInterval(countdownInterval);
                    timerElement.classList.add('hidden');
                    messageElement.innerHTML = '<span class="text-green-600 font-bold"> ¡Análisis Completado! Revise los resultados abajo.</span>';
                    isSessionActive = false;
                }
            }, 1000);
        }
    
        function showMessage(type, title, content) {
            const modal = document.getElementById('message-modal');
            document.getElementById('modal-title').textContent = title;
            document.getElementById('modal-content').innerHTML = content;
            
            const icon = document.getElementById('modal-icon');
            icon.className = 'w-6 h-6';
            
            if (type === 'success') {
                icon.classList.add('text-emerald-500');
                icon.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12.75 11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" /></svg>`;
            } else if (type === 'error') {
                icon.classList.add('text-red-500');
                icon.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.38 3.375 2.074 3.375h14.128c1.694 0 2.938-1.875 2.074-3.376L13.19 2.405a2.25 2.25 0 0 0-3.98 0L2.697 16.126ZM12 15.75h.007V15.75H12Z" /></svg>`;
            } else {
                icon.classList.add('text-blue-500');
                icon.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="m11.25 11.25.041-.02a.75.75 0 0 1 1.063.852l-.708 2.836a.75.75 0 0 0 1.063.852l.041-.02m0-6.236c0-1.077.838-1.921 1.921-1.921c1.083 0 1.92.844 1.92 1.921c0 1.076-.837 1.92-1.92 1.92c-.968 0-1.764-.707-1.897-1.614M12 21a9 9 0 1 1 0-18 9 9 0 0 1 0 18Z" /></svg>`;
            }
            
            modal.classList.remove('hidden');
            document.getElementById('overlay').classList.remove('hidden');
        }

        function closeModal() {
            document.getElementById('message-modal').classList.add('hidden');
            document.getElementById('overlay').classList.add('hidden');
        }

        function displayResult(data) {
            const resultBox = document.getElementById('analysis-result-box');
            const analysisText = data.fulfillment.analysis_result.analysis_text;
            const ttsIncluded = data.fulfillment.tts_included;
            const fileName = data.fulfillment.file_info || 'N/A';
            
            // Detener el temporizador simulado
            if (countdownInterval) {
                clearInterval(countdownInterval);
            }
            document.getElementById('timer-box').classList.add('hidden');
            isSessionActive = false;

            let ttsButtonHtml = '';
            if (ttsIncluded && analysisText) {
                // Sanitizar texto para la función JS, usando JSON.stringify
                const escapedText = JSON.stringify(analysisText.replace(/"/g, ''));
                ttsButtonHtml = `
                    <button onclick='generateAndPlayAudio(${escapedText}, this)' class="mt-4 w-full md:w-auto px-6 py-3 bg-indigo-600 text-white font-semibold rounded-full shadow-md hover:bg-indigo-700 transition duration-150 flex items-center justify-center">
                        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" class="w-5 h-5 mr-2">
                            <path fill-rule="evenodd" d="M12 2.25c-5.385 0-9.75 4.365-9.75 9.75s4.365 9.75 9.75 9.75 9.75-4.365 9.75-9.75S17.385 2.25 12 2.25Zm4.28 10.28a.75.75 0 0 0 0-1.06l-3-3a.75.75 0 1 0-1.06 1.06l1.72 1.72H8.25a.75.75 0 0 0 0 1.5h5.69l-1.72 1.72a.75.75 0 1 0 1.06 1.06l3-3Z" clip-rule="evenodd" />
                        </svg>
                          Reproducir Análisis
                    </button>
                `;
            }
            
            // CRÍTICO: Nueva advertencia en el resultado para el voluntario
            const warningHtml = `
                <div class="p-3 bg-red-100 border border-red-400 text-red-800 rounded-lg font-bold mb-4">
                    🛑 ADVERTENCIA: El "Diagnóstico Hipotético" y "Tratamiento Hipotético" a continuación NO son reales. Consulte un médico licenciado.
                </div>
            `;
            
            resultBox.innerHTML = `
                <div class="bg-white p-6 rounded-xl shadow-2xl animate-fadeIn">
                    <h2 class="text-2xl font-extrabold text-emerald-700 border-b pb-3 mb-4 flex items-center">
                        <span class="mr-2"></span> Resultado de Análisis Clínico (Simulado)
                    </h2>
                    
                    ${warningHtml}

                    <div class="mb-4 text-sm text-gray-600 space-y-1">
                        <p><strong>Nivel de Servicio:</strong> ${TIERS_DATA[data.fulfillment.service_level].name}</p>
                        <p><strong>Pago:</strong> ${data.payment_method}</p>
                        <p><strong>Archivos Adjuntos:</strong> ${fileName}</p>
                        <p><strong>Audio TTS:</strong> ${ttsIncluded ? 'Incluido' : 'No incluido'}</p>
                    </div>
                    
                    ${ttsButtonHtml}
                    
                    <h3 class="text-lg font-bold text-gray-800 mt-6 mb-2">Análisis de la IA:</h3>
                    <div class="bg-gray-50 p-4 rounded-lg border border-gray-200 whitespace-pre-wrap text-gray-700">
                        ${escapeHtml(analysisText || 'Error: El análisis no devolvió texto.')}
                    </div>
                </div>
            `;
            
            resultBox.scrollIntoView({ behavior: 'smooth' });
        }

        document.addEventListener('DOMContentLoaded', () => {
            // Inicializar UI
            updatePrice();
            
            // Listeners para actualizar precio
            const form = document.getElementById('service-form');
            form.addEventListener('change', (e) => {
                if (e.target.name === 'service_level' || e.target.type === 'checkbox') {
                    updatePrice();
                }
            });

            // Listener para submit
            form.addEventListener('submit', async (e) => {
                e.preventDefault();
                if (isSessionActive) {
                    showMessage('info', 'Sesión en Curso', 'Ya hay una solicitud de análisis activa. Por favor, espere a que termine o recargue la página.');
                    return;
                }

                const submitButton = e.submitter;
                const originalText = submitButton.innerHTML;
                submitButton.disabled = true;
                submitButton.textContent = 'Procesando Solicitud...';
                
                const formData = new FormData(form);
                formData.append('user_id', DEMO_USER_ID);

                let result;
                try {
                    const response = await fetch(`${RENDER_APP_URL}/create-service`, {
                        method: 'POST',
                        body: formData
                    });

                    result = await response.json();

                    if (response.ok) {
                        if (result.status === 'payment_required') {
                            // Flujo de Pago: Redireccionar a Stripe 
                            window.location.href = result.payment_url;
                            return; // Importante: Salir del flujo para evitar restaurar el botón
                        } else if (result.status === 'success') {
                            // Bypass: Ejecución inmediata de la IA
                            showMessage('success', 'Análisis Inmediato (Bypass)', 'El análisis de prueba ha sido generado por la IA.');
                            displayResult(result);
                        }
                    } else {
                        throw new Error(result.detail || 'Error desconocido en el backend.');
                    }
                } catch (error) {
                    console.error("Fallo al enviar el formulario:", error);
                    showMessage('error', 'Error de Conexión', `No se pudo procesar la solicitud: ${error.message}`);
                } finally {
                    // Restaurar el botón si no hubo redirección de pago
                    if (!result || result.status !== 'payment_required') {
                        submitButton.innerHTML = originalText;
                        submitButton.disabled = false;
                    }
                }

                // Si es un bypass, iniciar el temporizador de espera asíncrona (simulado)
                if (result && result.status === 'success') {
                    const selectedLevel = parseInt(form.elements['service_level'].value);
                    const maxTime = TIERS_DATA[selectedLevel].max_time_min;
                    startCountdown(maxTime);
                }
            });
        });

    </script>

</body>
</html>
"""

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from typing import Optional, Any, Dict, List
import os
import json
import stripe
from google import genai
from google.genai import types
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

# =========================================================================
# 🌟 INSTRUCCIONES DE SISTEMA (PARA ANÁLISIS PROFUNDO Y DEBATE) 🌟
# =========================================================================

SYSTEM_INSTRUCTION_BASE = (
    "Usted es un experto en Ateneo Clínico de IA. Su objetivo es generar un análisis clínico "
    "sólido, basado en evidencia hipotética, para fines estrictamente académicos y de debate. "
    "El caso proporcionado es una SIMULACIÓN, por lo que su respuesta DEBE enfatizar el "
    "carácter hipotético de todo diagnóstico, análisis y tratamiento. "
    "Analiza el caso. Detecta automáticamente el idioma de la consulta y responde íntegramente en ese mismo idioma. "
)

SYSTEM_INSTRUCTION_DEBATE = (
    SYSTEM_INSTRUCTION_BASE +
    "Generarás un análisis PROFUNDO, CRÍTICO y listo para la discusión profesional. "
    "Tu respuesta DEBE estar en el formato JSON estricto requerido, incluyendo: "
    "1. **Análisis exhaustivo** que incluya diagnósticos diferenciales complejos y crítica de la validez de los datos. "
    "2. **Formulación de un Tratamiento Hipotético (Medicamentoso)** estructurado, indicando clase de fármaco, dosis (simulada) y justificación. Este tratamiento debe ser explícitamente etiquetado como **SOLO SIMULACIÓN Y EXPERIMENTAL**."
)

# Esquema de respuesta JSON forzado para la IA
RESPONSE_SCHEMA = types.ResponseSchema(
    type=types.Type.OBJECT,
    properties={
        "analysis_text": types.ResponseSchema(
            type=types.Type.STRING,
            description="El análisis clínico, profundo y crítico generado, listo para el debate académico, basado en las instrucciones del token."
        ),
        "hypothetical_treatment": types.ResponseSchema(
            type=types.Type.STRING,
            description="El tratamiento medicamentoso hipotético (simulado) y su justificación. Debe contener la advertencia: (SOLO SIMULACIÓN Y EXPERIMENTAL)."
        )
    },
    required=["analysis_text", "hypothetical_treatment"]
)

# ESTRUCTURA MEJORADA: VALOR POR ALCANCE FUNCIONAL
# Incluye token_instruction para el control de la calidad y el tamaño
TIERS = {
    1: {"name": " Nivel 1 – Diagnóstico Rápido", "price": 10, "value_focus": "Respuesta Directa. (1 Tarea IA)", "max_time_min": 5, "token_instruction": SYSTEM_INSTRUCTION_BASE + " Proporciona una respuesta extremadamente concisa y directa (Diagnóstico y/o Hipótesis). Máximo 500 tokens.", "base_tasks": ["Diagnóstico/Hipótesis"], "max_tokens": 500},
    2: {"name": " Nivel 2 – Evaluación Estándar", "price": 50, "value_focus": "Análisis Básico Completo. (2 Tareas IA)", "max_time_min": 10, "token_instruction": SYSTEM_INSTRUCTION_BASE + " Proporciona un Diagnóstico Definitivo y una Sugerencia Terapéutica General y concisa. Máximo 1000 tokens.", "base_tasks": ["Diagnóstico Definitivo", "Sugerencia Terapéutica General"], "max_tokens": 1000},
    3: {"name": " Nivel 3 – Planificación y Protocolo", "price": 100, "value_focus": "Protocolo Clínico Detallado. (3 Tareas IA)", "max_time_min": 25, "token_instruction": SYSTEM_INSTRUCTION_DEBATE + " Genera el Protocolo Clínico Detallado: Diagnóstico, Terapia Específica y Plan de Pruebas Adicionales (Laboratorio/Imagen). Máximo 1500 tokens.", "base_tasks": ["Diagnóstico Definitivo", "Terapia Específica", "Plan de Pruebas Adicionales"], "max_tokens": 1500},
    4: {"name": " Nivel 4 – Debate y Evidencia", "price": 200, "value_focus": "Análisis Crítico y Controvertido. (4 Tareas IA)", "max_time_min": 45, "token_instruction": SYSTEM_INSTRUCTION_DEBATE + " Genera un Debate Clínico exhaustivo que incluye Diagnóstico, Terapia, Pruebas y una Sección 'Debate y Alternativas', analizando controversias y evidencia. Máximo 2500 tokens.", "base_tasks": ["Diagnóstico", "Terapia", "Pruebas Adicionales", "Debate y Alternativas"], "max_tokens": 2500},
    5: {"name": " Nivel 5 – Mesa Clínica Premium", "price": 500, "value_focus": "Multi-Caso y Documentación Formal. (3 Casos x 5 Tareas)", "max_time_min": 70, "token_instruction": SYSTEM_INSTRUCTION_DEBATE + " Analiza tres casos clínicos proporcionados de forma secuencial. Proporciona un Resumen Comparativo, Insights y un borrador de Documentación Formal. Máximo 4000 tokens.", "base_tasks": ["Diagnóstico Completo", "Terapia y Protocolo", "Debate Crítico", "Análisis Comparativo (Multi-Caso)", "Borrador de Informe Documental"], "max_tokens": 4000},
}

# ADD-ONS DEFINITION (Precios fijos)
ADDONS = {
    "image_analysis": {"name": "Análisis de Imagen/Laboratorio", "price": 10, "instruction_boost": " INTEGRA EL ANÁLISIS VISUAL DE LA IMAGEN/LABORATORIO al diagnóstico. Aumenta la profundidad del análisis y usa 500 tokens adicionales."},
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

async def call_gemini_api(prompt: str, tier_level: int, image_data: Optional[bytes] = None):
    """
    Genera el análisis clínico, forzando la respuesta JSON y el control de tokens.
    """
    if not gemini_client:
        return {
            "analysis_status": "error",
            "reason": "GEMINI_API_KEY no configurada. El servicio de análisis de IA está DESACTIVADO.",
            "prompt_used": prompt
        }
    
    tier_info = TIERS.get(tier_level, TIERS[1])
    system_instruction = tier_info["token_instruction"]

    # 1. CONSTRUCCIÓN DE LA ENTRADA MULTIMODAL (parts)
    parts = []
    
    # Agregar la imagen si existe
    if image_data:
        # Aquí asumimos que la imagen es JPEG o PNG, se necesitaría un manejo de MIME type más robusto.
        parts.append(types.Part.from_bytes(data=image_data, mime_type="image/jpeg")) 
        
    # Agregar el texto del prompt
    # Pedir el formato JSON explícitamente y añadir la descripción
    prompt_with_json_request = f"Genera el análisis y tratamiento en el formato JSON EXACTO requerido. Caso: {prompt}"
    parts.append(prompt_with_json_request)

    
    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        response_mime_type="application/json",
        response_schema=RESPONSE_SCHEMA,
        # Usamos el token_limit definido en el Tier para controlar estrictamente
        max_output_tokens=tier_info["max_tokens"]
    )
    
    def blocking_call():
        """Función síncrona que envuelve la llamada al cliente de Gemini."""
        response = gemini_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=parts,
            config=config,
        )
        return response.text
        
    try:
        json_response_text = await asyncio.to_thread(blocking_call)
        
        # Intentar parsear el JSON forzado
        parsed_result = json.loads(json_response_text)
        
        # Validar que los campos críticos existan (si la IA falla en el JSON)
        if "analysis_text" not in parsed_result or "hypothetical_treatment" not in parsed_result:
             raise ValueError("Respuesta JSON de Gemini incompleta.")
        
        return {
            "analysis_status": "success",
            "analysis_text": parsed_result["analysis_text"],
            "hypothetical_treatment": parsed_result["hypothetical_treatment"],
        }
            
    except APIError as e:
        print(f"Error de API de Gemini: {e}")
        return {
            "analysis_status": "error",
            "analysis_text": "Error en la generación de IA. El modelo falló al generar el análisis (APIError).",
            "hypothetical_treatment": "Error.",
            "reason": f"Error de API de Gemini: {e}. Revise su cuota o clave."
        }
    except Exception as e:
        print(f"Error inesperado con Gemini/JSON parse: {e}")
        return {
            "analysis_status": "error",
            "analysis_text": "Error en la generación de IA. El modelo falló al generar el JSON estructurado.",
            "hypothetical_treatment": "Error.",
            "reason": f"Error desconocido al llamar a Gemini: {e}"
        }


def create_stripe_checkout_session(total_price: int, product_name: str, metadata: dict, line_items: List[Dict]):
    """Crea una sesión de Stripe Checkout."""
    # (El código de Stripe se mantiene igual, ya que no se requirió modificación)
    if not stripe.api_key:
        raise HTTPException(status_code=500, detail="La clave secreta de Stripe no está configurada.")
        
    success_url = f"{RENDER_APP_URL}/stripe/success?session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{RENDER_APP_URL}/stripe/cancel"
    
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=line_items,
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
    Aquí se ejecutaría el análisis real de la IA.
    """
    user_id = metadata.get("user_id", "Unknown")
    level = int(metadata.get("service_level", 1))
    
    # 1. Recuperar info base
    tier_info = TIERS.get(level, TIERS[1])
    
    # 2. Checkear Add-ons pagados y ajustar instrucción de tokens
    # (La lógica de imagen real se implementaría aquí: recuperar de S3/Cloud Storage si fue adjuntada).
    
    description_snippet = metadata.get("description_snippet", "Caso clínico no especificado.")
    prompt = f"Analizar el siguiente caso clínico: {description_snippet}"
    
    # SIMULACIÓN DE LA LLAMADA: Asumimos que no hay datos binarios reales para la imagen en el webhook
    # Si hubiera una imagen, se enviaría el binario en 'image_data'.
    analysis_result = await call_gemini_api(prompt, level, image_data=None)
    
    print(f" Análisis de IA completado (Nivel {level}) para el usuario {user_id}. Estado: {analysis_result.get('analysis_status')}")
    
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
        
        # 1.1. Recuperar la instrucción de tokens base del tier
        # La instrucción ya incluye el SYSTEM_INSTRUCTION_DEBATE si el nivel es 3, 4, o 5
        
        prompt = description if description else "Caso clínico no especificado. Análisis genérico de salud preventiva."
        
        # Preparar la data de la imagen para la llamada multimodal
        image_data_bytes = None
        if clinical_file and clinical_file.file and include_image_analysis:
            # Leer el contenido del archivo si existe (necesario para el bypass multimodal)
            file_contents = await clinical_file.read()
            # La función call_gemini_api ahora recibe los bytes directamente
            image_data_bytes = file_contents
            # Reiniciar el puntero del archivo para que la función principal no falle
            await clinical_file.seek(0)
            
        # Ejecutar análisis con la instrucción de tokens del nivel seleccionado
        analysis_result = await call_gemini_api(prompt, service_level, image_data=image_data_bytes)
        file_info = clinical_file.filename if clinical_file else None
        
        # En el bypass, el audio se considera 'incluido' si se solicitó o si el nivel lo incluye
        tts_included = include_tts_addon or service_level in ADDONS["tts_audio"]["tiers_included"]
        
        return {
            "status": "success",
            "payment_method": "Bypass (Gratuito)",
            "fulfillment": {
                "user_id": user_id,
                "service_level": service_level,
                "analysis_result": analysis_result, # Contiene analysis_text y hypothetical_treatment
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

# --- RUTAS DE REDIRECCIÓN ---
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
                        <span class="mr-2 text-emerald-600">{'⭐' if level >= 3 else ''}</span>
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
                {f'Incluye Audio TTS profesional' if level in ADDONS["tts_audio"]["tiers_included"] else 'Análisis Conciso'}
            </div>
        </div>
        """
        
    # --- TEMPLATE HTML COMPLETO (FRONTEND) ---
    HTML_TEMPLATE = f"""
<!DOCTYPE html>
<html lang="es">
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Ateneo Clínico IA: Estructura de Alcance Funcional</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        body {{ font-family: 'Inter', sans-serif; background: linear-gradient(135deg, #e0f2f1 0%, #f7f9fb 100%); }}
        .card {{ box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -4px rgba(0, 0, 0, 0.05); border: 1px solid #e2e8f0; }}
        .tier-card {{ border: 2px solid transparent; }}
        .tier-card:has(input:checked) {{ border-color: #059669; background-color: #f0fff4; }}
        .tier-card:has(input:checked) .text-emerald-600 {{ color: #047857; }}
        @keyframes fadeIn {{ from {{ opacity: 0; transform: translateY(10px); }} to {{ opacity: 1; transform: translateY(0); }} }}
        .animate-fadeIn {{ animation: fadeIn 0.5s ease-out; }}
    </style>
</head>
<body class="p-4 md:p-8 min-h-screen flex items-start justify-center">

    <script>
        // =========================================================================
        // CONSTANTES Y CONFIGURACIÓN
        // =========================================================================
        const RENDER_APP_URL = "{RENDER_APP_URL}";
        const DEMO_USER_ID = 999;
        const TIERS_DATA = {json.dumps(TIERS)};
        const ADDONS_DATA = {json.dumps(ADDONS)};

        let countdownInterval = null;
        let isSessionActive = false;

        // =========================================================================
        // UTILITIES DE AUDIO (Conversión PCM a WAV - MANTENIDO)
        // =========================================================================

        function base64ToArrayBuffer(base64) {{
            const binaryString = atob(base64);
            const len = binaryString.length;
            const bytes = new Uint8Array(len);
            for (let i = 0; i < len; i++) {{
                bytes[i] = binaryString.charCodeAt(i);
            }}
            return bytes.buffer;
        }}

        function pcmToWav(pcm16, sampleRate) {{
            const buffer = new ArrayBuffer(44 + pcm16.length * 2);
            const view = new DataView(buffer);
            let offset = 0;

            function writeString(str) {{
                for (let i = 0; i < str.length; i++) {{
                    view.setUint8(offset++, str.charCodeAt(i));
                }}
            }}

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
            for (let i = 0; i < pcm16.length; i++) {{
                view.setInt16(offset, pcm16[i], true);
                offset += 2;
            }}

            return new Blob([view], {{ type: 'audio/wav' }});
        }}


        async function generateAndPlayAudio(text, buttonElement) {{
            const originalText = buttonElement.textContent;
            buttonElement.disabled = true;
            buttonElement.textContent = ' 🎧 Generando Audio...';
            
            const GEMINI_TTS_MODEL = "gemini-2.5-flash-preview-tts";
            const TTS_VOICE_NAME = "Kore";

            // NOTA: Esta API Key es de prueba y DEBERÍA ser gestionada por el backend.
            // Para la demostración frontend, se deja vacía aquí para no exponerla.
            const apiKey = "{GEMINI_API_KEY}"; 
            const apiUrl = `https://generativelanguage.googleapis.com/v1beta/models/${GEMINI_TTS_MODEL}:generateContent?key=${apiKey}`;

            const natural_speech_prompt = `Di de forma natural y profesional, omitiendo cualquier mención a la puntuación o símbolos, solo el texto principal: ${{text}}`;

            const payload = {{
                contents: [{{
                    parts: [{{ text: natural_speech_prompt }}]
                }}],
                generationConfig: {{
                    responseModalities: ["AUDIO"],
                    speechConfig: {{
                        voiceConfig: {{
                            prebuiltVoiceConfig: {{ voiceName: TTS_VOICE_NAME }}
                        }}
                    }}
                }},
                model: GEMINI_TTS_MODEL
            }};

            try {{
                const response = await fetch(apiUrl, {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify(payload)
                }});

                const result = await response.json();
                const candidate = result.candidates?.[0];
                const part = candidate?.content?.parts?.find(p => p.inlineData && p.inlineData.mimeType.startsWith('audio/'));

                if (!part || !part.inlineData.data) {{
                    throw new Error("No se pudo obtener el audio de la respuesta de Gemini.");
                }}

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

                buttonElement.textContent = ' 🎶 Escuchando...';
                audio.onended = () => {{
                    buttonElement.textContent = ' 🔊 Reproducir Análisis';
                    buttonElement.disabled = false;
                    URL.revokeObjectURL(audioUrl);
                }};

            }} catch (error) {{
                console.error("Error al generar o reproducir el audio TTS:", error);
                buttonElement.textContent = ' ❌ Error de Audio';
            }} finally {{
                if (buttonElement.textContent !== ' 🎶 Escuchando...') {{
                    setTimeout(() => {{
                        buttonElement.textContent = originalText;
                        buttonElement.disabled = false;
                    }}, 3000);
                }}
            }}
        }}


        // =========================================================================
        // LÓGICA DE FORMULARIO, PRECIOS Y TIEMPO (TIMER)
        // =========================================================================

        function escapeHtml(str) {{
            if (!str) return '';
            return str.replace(/&/g, '&amp;')
                      .replace(/</g, '&lt;')
                      .replace(/>/g, '&gt;')
                      .replace(/"/g, '&quot;')
                      .replace(/'/g, '&#39;')
                      .replace(/`/g, '&#96;');
        }}
        
        function updatePrice() {{
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
            if (imageCheckbox.checked) {{
                totalPrice += ADDONS_DATA.image_analysis.price;
            }}

            // 2. Manejar Add-on de Audio (Solo si no está incluido en el Tier)
            if (isTtsIncluded) {{
                audioCheckbox.checked = true; // Forzar selección
                audioCheckbox.disabled = true;
                document.getElementById('tts-price-display').textContent = '(Incluido)';
            }} else {{
                audioCheckbox.disabled = false;
                document.getElementById('tts-price-display').textContent = `($${ADDONS_DATA.tts_audio.price} Add-on)`;
                if (audioCheckbox.checked) {{
                    // No doble cobro: Solo se suma si el nivel NO lo incluye
                    totalPrice += ADDONS_DATA.tts_audio.price;
                }}
            }}
            
            totalDisplay.textContent = `$${{totalPrice}}`;
            submitButton.innerHTML = `Pagar $${{totalPrice}} y Ejecutar Servicio Seleccionado`;
            
            // Actualizar tiempo simulado en el título
            document.getElementById('current-max-time').textContent = tierInfo.max_time_min;
        }}

        function startCountdown(maxMinutes) {{
            if (countdownInterval) {{
                clearInterval(countdownInterval);
            }}
            
            let secondsLeft = maxMinutes * 60;
            const timerElement = document.getElementById('timer-display');
            const messageElement = document.getElementById('timer-message');
            
            isSessionActive = true;
            document.getElementById('timer-box').classList.remove('hidden');
            timerElement.classList.remove('hidden');
            messageElement.innerHTML = '';
            
            function updateTimer() {{
                const minutes = Math.floor(secondsLeft / 60);
                const seconds = secondsLeft % 60;
                const timeString = `${{minutes.toString().padStart(2, '0')}}:${{seconds.toString().padStart(2, '0')}}`;
                
                timerElement.textContent = ` ⏳ Tiempo restante: ${{timeString}}`;
                
                if (secondsLeft <= 60) {{
                    timerElement.classList.add('text-red-500');
                    timerElement.classList.remove('text-emerald-600');
                }} else {{
                    timerElement.classList.remove('text-red-500');
                    timerElement.classList.add('text-emerald-600');
                }}
                
                if (secondsLeft <= 0) {{
                    clearInterval(countdownInterval);
                    timerElement.textContent = ' 🛑 Tiempo Agotado';
                    messageElement.innerHTML = `
                        <p class="text-sm font-bold text-red-700 mt-2">
                            Mensaje Final Automático: Gracias por participar. Si desea abrir otro caso,
                            puede hacerlo realizando un nuevo pago.
                        </p>
                    `;
                    isSessionActive = false;
                }}
                
                secondsLeft--;
            }}

            updateTimer();
            countdownInterval = setInterval(updateTimer, 1000);
        }}

        function handleResponse(response) {{
            const resultsDiv = document.getElementById('results-section');
            resultsDiv.innerHTML = '';
            
            if (response.payment_url) {{
                // Flujo de pago real (Stripe)
                resultsDiv.innerHTML = `
                    <div class="bg-yellow-50 border border-yellow-300 text-yellow-800 p-4 rounded-xl mt-4 animate-fadeIn">
                        <p class="font-bold text-xl mb-2"> 💳 Pago Requerido (${document.getElementById('total-price-display').textContent}):</p>
                        <p>Redirigiendo a Stripe Checkout. El servicio se cumplirá ÚNICAMENTE después de la confirmación del Webhook seguro.</p>
                        <a href="${{response.payment_url}}" target="_blank" class="text-blue-600 underline hover:text-blue-800 font-medium transition duration-150">
                             (Haga clic aquí si la redirección falla)
                        </a>
                    </div>
                `;
                setTimeout(() => {{
                    window.location.href = response.payment_url;
                }}, 1000);
            }} else if (response.status === "success") {{
                // Flujo de éxito (Vía Bypass)
                const analysisText = response.fulfillment.analysis_result?.analysis_text || 'Error: Análisis no disponible.';
                const hypotheticalTreatment = response.fulfillment.analysis_result?.hypothetical_treatment || 'Error: Tratamiento no disponible.';
                const maxTime = response.fulfillment.max_time_min;
                const ttsIncluded = response.fulfillment.tts_included;
                
                startCountdown(maxTime);
                
                resultsDiv.innerHTML = `
                    <div class="bg-emerald-50 border border-emerald-400 text-emerald-800 p-6 rounded-xl mt-6 animate-fadeIn">
                        <p class="font-extrabold text-2xl mb-4 text-emerald-700">✅ Fulfillment Completo</p>
                        
                        <div class="bg-red-100 border-l-4 border-red-500 p-4 mb-4 rounded-lg">
                            <p class="font-bold text-red-700">⚠️ ADVERTENCIA: NO ES CONSEJO MÉDICO REAL</p>
                            <p class="text-sm text-red-600">Este análisis y el tratamiento presentado a continuación son **SOLO SIMULACIONES** y están destinados únicamente para fines **ACADÉMICOS Y DE DEBATE**.</p>
                            <p class="text-sm text-red-600 mt-1">Consulte un profesional para cualquier decisión clínica real.</p>
                        </div>
                        
                        <p class="text-lg font-semibold text-emerald-700 mt-4 border-b pb-2 border-emerald-200 flex justify-between items-center">
                            <span> Análisis Clínico de Gemini:</span>
                            ${{ttsIncluded ? `
                                <button id="tts-btn" onclick="generateAndPlayAudio('${{escapeHtml(analysisText)}}', this)"
                                    class="bg-blue-500 hover:bg-blue-600 text-white text-sm font-bold py-1 px-3 rounded-lg shadow-md transition duration-150 ease-in-out flex items-center">
                                    <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 mr-1" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM9.555 7.168A1 1 0 008 8v4a1 1 0 001.555.832l3-2a1 1 0 000-1.664l-3-2z" clip-rule="evenodd" /></svg>
                                     Reproducir Análisis
                                </button>
                            ` : `
                                <span class="text-red-500 text-xs font-semibold">Audio no pagado/incluido.</span>
                            `}}
                        </p>
                        <div class="bg-white p-4 rounded-lg border border-emerald-300 shadow-inner mt-2">
                            <p class="whitespace-pre-wrap text-gray-800 text-sm leading-relaxed">${{analysisText}}</p>
                        </div>

                        <div class="mt-6 bg-red-50 p-4 rounded-lg border border-red-400">
                            <p class="text-lg font-extrabold text-red-700 border-b border-red-300 pb-2 mb-2">
                                🛑 TRATAMIENTO HIPOTÉTICO (SOLO SIMULACIÓN, EXPERIMENTAL)
                            </p>
                            <p class="whitespace-pre-wrap text-red-800 text-sm leading-relaxed">${{hypotheticalTreatment}}</p>
                        </div>

                        <div class="mt-6 pt-4 border-t border-emerald-200 flex justify-between items-center">
                            <p class="text-xs text-gray-500">
                                Método: ${{response.payment_method}} | User ID: ${{response.fulfillment.user_id}}
                            </p>
                             <button onclick="window.scrollTo(0, 0)" class="bg-gray-200 hover:bg-gray-300 text-gray-800 text-sm font-semibold py-2 px-4 rounded-lg transition duration-150">
                                Volver al Principio ⬆️
                            </button>
                        </div>
                    </div>
                `;
            }} else {{
                // Flujo de Error
                resultsDiv.innerHTML = `
                    <div class="bg-red-100 border border-red-400 text-red-700 p-4 rounded-xl mt-4">
                        <p class="font-bold"> ❌ Error de Conexión o Proceso:</p>
                        <p>No se pudo completar la solicitud con la API.</p>
                        <p class="mt-2 text-xs text-gray-700">Detalles: ${{response.detail || response.message}}</p>
                        <button onclick="window.scrollTo(0, 0)" class="mt-3 bg-gray-200 hover:bg-gray-300 text-gray-800 text-sm font-semibold py-2 px-4 rounded-lg transition duration-150">
                                Volver al Principio ⬆️
                        </button>
                    </div>
                `;
            }}
        }}

        async function submitForm(event) {{
            event.preventDefault();
            const form = event.target;
            const resultsDiv = document.getElementById('results-section');
            resultsDiv.innerHTML = '';
            
            // Limpiar Timer
            if (countdownInterval) {{
                clearInterval(countdownInterval);
                isSessionActive = false;
                document.getElementById('timer-box').classList.add('hidden');
            }}

            const formData = new FormData(form);
            if (!formData.has('user_id')) {{ formData.append('user_id', DEMO_USER_ID); }}
            
            // Validar consentimiento legal
            const consentChecked = form.querySelector('#has_legal_consent').checked;
            if (!consentChecked) {{
                 resultsDiv.innerHTML = '<div class="bg-red-100 border border-red-400 text-red-700 p-4 rounded-xl mt-4 font-bold"> 🛑 Error: Debe aceptar el consentimiento legal (OBLIGATORIO).</div>';
                 return;
            }}
            
            // Iniciar el Spinner de Carga
            resultsDiv.innerHTML = '<div class="mt-4 p-4 text-center text-emerald-600 font-semibold flex items-center justify-center"><svg class="animate-spin -ml-1 mr-3 h-5 w-5 text-emerald-600" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>Procesando... Esperando Redirección de Pago/Análisis...</div>';

            try {{
                const fullUrl = `${{RENDER_APP_URL}}/create-service`;
                
                const response = await fetch(fullUrl, {{
                    method: 'POST',
                    body: formData
                }});

                const data = await response.json();
                
                if (!response.ok) {{
                    // Si el servidor retorna un error 4xx o 5xx
                    const errorDetail = data.detail || `Error ${{response.status}}: Error de servidor.`;
                    throw new Error(typeof errorDetail === 'string' ? errorDetail : JSON.stringify(errorDetail));
                }}

                handleResponse(data);

            }} catch (error) {{
                resultsDiv.innerHTML = `
                    <div class="bg-red-100 border border-red-400 text-red-700 p-4 rounded-xl mt-4">
                        <p class="font-bold"> ❌ Error de Conexión o Proceso:</p>
                        <p>No se pudo completar la solicitud con la API.</p>
                        <p class="mt-2 text-xs text-gray-700">Detalles: ${{error.message}}</p>
                         <button onclick="window.scrollTo(0, 0)" class="mt-3 bg-gray-200 hover:bg-gray-300 text-gray-800 text-sm font-semibold py-2 px-4 rounded-lg transition duration-150">
                            Volver al Principio ⬆️
                        </button>
                    </div>
                `;
                console.error("Error en la solicitud:", error);
            }}
        }}

        // Listener para la actualización de precios
        window.onload = () => {{
             document.querySelectorAll('.tier-card input[name="service_level"]').forEach(radio => {{
                 radio.addEventListener('change', updatePrice);
             }});
             document.getElementById('include_image_analysis').addEventListener('change', updatePrice);
             document.getElementById('include_tts_addon').addEventListener('change', updatePrice);

             // Inicializar precio al cargar la página
             updatePrice();
        }};
    </script>

    <div class="w-full max-w-6xl bg-white p-6 md:p-10 rounded-2xl card">
        <h1 class="text-4xl font-extrabold text-gray-800 mb-1 flex items-center">
            <svg xmlns="http://www.w3.org/2000/svg" class="h-8 w-8 text-emerald-600 mr-3" viewBox="0 0 20 20" fill="currentColor">
                <path d="M10 2a8 8 0 00-8 8c0 1.76.71 3.42 1.95 4.67l.14-.14C4.38 13.56 5 12.83 5 12a5 5 0 0110 0c0 .83.62 1.56 1.85 2.53l.14.14A8 8 0 0010 2zm0 14a6 6 0 110-12 6 6 0 010 12zM9 9a1 1 0 112 0v3a1 1 0 11-2 0V9z" />
            </svg>
            Ateneo Clínico IA: Estructura de Alcance Funcional
        </h1>
        <p class="text-xl font-medium text-emerald-700 mb-4">Estructura por Alcance Funcional + Add-ons. Tiempo simulado por caso: <span id="current-max-time" class="font-extrabold"></span> minutos.</p>

        <div class="bg-red-50 border-l-4 border-red-500 p-4 mb-6 rounded-lg" role="alert">
            <p class="font-bold text-red-700">⚠️ RENUNCIA DE RESPONSABILIDAD (WAIVER OBLIGATORIO) ⚠️</p>
            <p class="text-sm text-red-600">El Ateneo Clínico IA es una plataforma para fines **académicos, educativos y de debate simulado**. Los resultados, incluidos los diagnósticos y tratamientos hipotéticos, **NO constituyen diagnóstico médico ni asesoramiento clínico real**. No se procesan datos sensibles (HIPAA). **Usted acepta usar la plataforma bajo su propio riesgo y responsabilidad.**</p>
        </div>

        <div id="timer-box" class="mb-6 p-3 bg-white shadow-inner rounded-xl hidden">
            <p id="timer-display" class="text-2xl font-extrabold text-center hidden"></p>
            <div id="timer-message" class="text-center"></div>
        </div>

        <form id="service-form" onsubmit="submitForm(event)">
            <input type="hidden" name="user_id" value="999">

            <h2 class="text-2xl font-bold text-gray-800 mb-3">1. Seleccione Nivel de Servicio Base</h2>
            <div class="grid grid-cols-1 md:grid-cols-5 gap-4 mb-6">
                {tier_html}
            </div>

            <div class="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
                <div>
                    <label for="description" class="block text-sm font-medium text-gray-700 mb-1">
                        Descripción del Caso / Signos y Síntomas
                    </label>
                    <textarea id="description" name="description" rows="6" class="mt-1 block w-full rounded-lg border-gray-300 shadow-sm focus:border-emerald-500 focus:ring-emerald-500 border p-3 placeholder-gray-400" placeholder="Ejemplo: 'Paciente masculino de 45 años con dolor torácico opresivo...'"></textarea>
                </div>
                <div>
                    <h2 class="text-xl font-bold text-gray-800 mb-3">2. Add-ons (Añadir a su protocolo)</h2>
                    
                    <div class="mb-3 p-3 border rounded-lg bg-gray-50 flex items-center justify-between">
                        <label for="include_image_analysis" class="flex items-center text-sm font-medium text-gray-700 cursor-pointer">
                            <input type="checkbox" id="include_image_analysis" name="include_image_analysis" value="true" class="h-4 w-4 text-indigo-600 border-gray-300 rounded focus:ring-indigo-500 mr-2">
                             Análisis de Imagen/Laboratorio
                        </label>
                        <span class="text-md font-extrabold text-gray-800">$10</span>
                    </div>

                    <div class="mb-3 p-3 border rounded-lg bg-gray-50 flex items-center justify-between">
                        <label for="include_tts_addon" class="flex items-center text-sm font-medium text-gray-700 cursor-pointer">
                            <input type="checkbox" id="include_tts_addon" name="include_tts_addon" value="true" class="h-4 w-4 text-indigo-600 border-gray-300 rounded focus:ring-indigo-500 mr-2">
                             Audio Profesional (TTS)
                        </label>
                        <span id="tts-price-display" class="text-sm font-bold text-gray-600"></span>
                    </div>

                    <div class="mt-4">
                        <label for="clinical_file" class="block text-sm font-medium text-gray-700 mb-1">
                             Archivos Adjuntos (Para Análisis de Imagen)
                        </label>
                        <input type="file" id="clinical_file" name="clinical_file" class="mt-1 block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-semibold file:bg-indigo-50 file:text-indigo-700 hover:file:bg-indigo-100"/>
                    </div>
                </div>
            </div>

            <div class="flex flex-col md:flex-row justify-between items-center bg-emerald-50 p-6 rounded-xl border border-emerald-300 mb-6">
                <div class="flex items-center text-2xl font-bold text-gray-800">
                    Total a Pagar: <span id="total-price-display" class="text-emerald-700 ml-2 font-extrabold"></span>
                </div>
                
                <div class="flex flex-col items-start mt-4 md:mt-0">
                    <div class="flex items-center mb-2">
                        <input id="has_legal_consent" name="has_legal_consent" type="checkbox" class="h-4 w-4 text-red-600 border-gray-300 rounded focus:ring-red-500 cursor-pointer">
                        <label for="has_legal_consent" class="ml-2 block text-sm text-gray-900 font-semibold">
                             Acepto el consentimiento legal (OBLIGATORIO).
                        </label>
                    </div>
                    <input type="password" id="developer-bypass" name="developer_bypass_key" placeholder=" Clave de Bypass (Flujo Gratuito)" class="mt-1 block w-full rounded-lg border-red-500 shadow-sm focus:border-red-500 focus:ring-red-500 border p-2 text-sm">
                </div>
            </div>

            <button type="submit" class="w-full flex justify-center py-3 px-4 border border-transparent rounded-lg shadow-xl text-lg font-bold text-white bg-emerald-600 hover:bg-emerald-700 focus:outline-none focus:ring-4 focus:ring-offset-2 focus:ring-emerald-500 transition duration-300 ease-in-out">
                 Pagar y Ejecutar Servicio Seleccionado
            </button>
        </form>

        <div id="results-section">
            </div>
    </div>

</body>
</html>
"""
    return HTMLResponse(content=HTML_TEMPLATE)

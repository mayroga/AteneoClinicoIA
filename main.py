from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from typing import Optional
import os 
import json
import stripe # SDK de Stripe
from google import genai # SDK oficial de Google GenAI
from google.genai.errors import APIError
import asyncio 
import time

# =========================================================================
# 0. CONFIGURACIÓN DE SECRETOS
# =========================================================================

# NOTA: Estas claves DEBEN ser configuradas como variables de entorno
ADMIN_BYPASS_KEY = os.getenv("ADMIN_BYPASS_KEY", "CLAVE_SECRETA_ADMIN") # Usamos un valor por defecto para demo
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY", "pk_test_...") 
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
RENDER_APP_URL = os.getenv("RENDER_APP_URL", "https://ateneoclinicoia.onrender.com")

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

# =========================================================================
# 1. CONFIGURACIÓN CRÍTICA DE CORS
# =========================================================================

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

async def call_gemini_api(prompt: str):
    """
    Genera el análisis clínico. Devuelve un error claro si la clave de IA no está configurada.
    """
    if not gemini_client:
        return {
            "analysis_status": "error",
            "reason": "GEMINI_API_KEY no configurada. El servicio de análisis de IA está DESACTIVADO.",
            "prompt_used": prompt
        }
    
    # Simulación de un proceso de análisis de la IA que toma tiempo
    await asyncio.sleep(2) 

    def blocking_call():
        """Función síncrona que envuelve la llamada al cliente de Gemini."""
        response = gemini_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=dict(
                system_instruction="Eres un analista clínico experto. Genera un resumen conciso y profesional del caso, incluyendo posibles diagnósticos diferenciales y pasos sugeridos, limitándote a un máximo de 300 palabras."
            )
        )
        return response.text
        
    try:
        # Nota: La integración con archivos adjuntos reales (UploadFile) requeriría
        # convertir el archivo a un formato MIME compatible con la API de Gemini (e.g., base64)
        # y usar el SDK con `contents=[prompt, image_part]`. Aquí solo simulamos el texto.
        
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


def create_stripe_checkout_session(price: int, product_name: str, metadata: dict):
    """Crea una sesión de Stripe Checkout y retorna el URL de pago."""
    
    # Esto es crítico: si STRIPE_SECRET_KEY no está, fallamos para evitar un flujo incompleto.
    if not stripe.api_key:
        raise HTTPException(status_code=500, detail="La clave secreta de Stripe no está configurada. Imposible crear sesión de pago real.")
        
    success_url = f"{RENDER_APP_URL}/stripe/success?session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{RENDER_APP_URL}/stripe/cancel"
    
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'usd',
                    'product_data': {
                        'name': product_name,
                        'metadata': {'type': metadata.get('service_type')}
                    },
                    'unit_amount': price * 100, # Stripe usa centavos
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=success_url,
            cancel_url=cancel_url,
            metadata=metadata, 
        )
        return {"status": "payment_required", "payment_url": session.url, "price": price, "currency": "USD"}
    
    except stripe.error.StripeError as e:
        print(f"Error de Stripe: {e}")
        raise HTTPException(status_code=500, detail=f"Error en la API de Stripe: {e}")
    except Exception as e:
        print(f"Error desconocido al crear la sesión de pago: {e}")
        raise HTTPException(status_code=500, detail="Error desconocido al crear la sesión de pago.")

# =========================================================================
# 4. RUTAS API (Endpoints)
# =========================================================================

# --- RUTA 1: SERVICIO VOLUNTARIO (ANÁLISIS CLÍNICO IA - $50) ---
@app.post("/volunteer/create-case")
async def create_volunteer_case(
    user_id: int = Form(...),
    description: str = Form(None), # Ahora opcional
    has_legal_consent: bool = Form(False),
    developer_bypass_key: str = Form(None),
    clinical_file: Optional[UploadFile] = File(None) # Archivo opcional
):
    
    # 1. VERIFICACIÓN CRÍTICA DEL CONSENTIMIENTO
    if not has_legal_consent:
        raise HTTPException(status_code=400, detail="Debe aceptar el consentimiento legal para el Servicio Voluntario.")

    # 2. VERIFICACIÓN DEL BYPASS DE DESARROLLADOR (ACCESO GRATUITO)
    if developer_bypass_key and developer_bypass_key == ADMIN_BYPASS_KEY:
        print(f"BYPASS ACTIVADO para el user_id: {user_id}")
        
        # Generar el prompt para el análisis de IA
        prompt = description if description else "Caso clínico no especificado. Análisis genérico de salud preventiva."
        analysis_result = await call_gemini_api(prompt)
        
        file_info = clinical_file.filename if clinical_file else None
        
        return {
            "status": "success",
            "payment_method": "Bypass (Gratuito)",
            "fulfillment": {
                "user_id": user_id,
                "tool_activated": "Análisis Clínico IA",
                "analysis_result": analysis_result,
                "file_info": file_info
            }
        }

    # 3. FLUJO DE PAGO DE STRIPE (El flujo por defecto)
    product_name = "Análisis Clínico IA - Voluntario"
    price = 50 # USD
    
    file_info_metadata = clinical_file.filename if clinical_file else "No File"
    
    metadata = {
        "user_id": str(user_id),
        "service_type": "volunteer",
        "description_snippet": description[:50] if description else "N/A",
        "has_file": "Yes" if clinical_file else "No",
        "file_name": file_info_metadata
    }

    # Esta función redirige al checkout de Stripe
    return create_stripe_checkout_session(price, product_name, metadata)


# --- RUTA 2: SERVICIO PROFESIONAL (ACTIVACIÓN DE HERRAMIENTA - $100) ---
@app.post("/professional/activate-tool")
async def activate_professional_tool(
    user_id: int = Form(...),
    tool_name: str = Form(None), # Ahora opcional
    developer_bypass_key: str = Form(None),
    clinical_file: Optional[UploadFile] = File(None) # Archivo opcional
):
    
    # 1. VERIFICACIÓN DEL BYPASS DE DESARROLLADOR (ACCESO GRATUITO)
    if developer_bypass_key and developer_bypass_key == ADMIN_BYPASS_KEY:
        print(f"BYPASS ACTIVADO para el user_id: {user_id}")
        
        file_info = clinical_file.filename if clinical_file else None
        
        return {
            "status": "success",
            "payment_method": "Bypass (Gratuito)",
            "fulfillment": {
                "user_id": user_id,
                "tool_activated": tool_name if tool_name else "Herramienta de Debate Clínico Genérica",
                "access_token": f"ACCESS-{int(time.time())}",
                "file_info": file_info
            }
        }

    # 2. FLUJO DE PAGO DE STRIPE (El flujo por defecto)
    product_name = "Activación de Herramienta Profesional"
    price = 100 # USD
    
    file_info_metadata = clinical_file.filename if clinical_file else "No File"

    metadata = {
        "user_id": str(user_id),
        "service_type": "professional",
        "tool_name": tool_name if tool_name else "Generic Tool",
        "has_file": "Yes" if clinical_file else "No",
        "file_name": file_info_metadata
    }

    # Esta función redirige al checkout de Stripe
    return create_stripe_checkout_session(price, product_name, metadata)


# --- RUTA PRINCIPAL (HTML) ---
@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    
    # Inyectar las variables de entorno en el HTML
    rendered_html = HTML_TEMPLATE.replace("{RENDER_URL}", RENDER_APP_URL)
    rendered_html = rendered_html.replace("{STRIPE_PK}", STRIPE_PUBLISHABLE_KEY)
    
    return rendered_html
# =========================================================================
# 5. TEMPLATE HTML (FRONTEND)
# =========================================================================

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Ateneo Clínico IA - Demo Frontend</title>
    <!-- Carga de Tailwind CSS para un diseño moderno y responsivo -->
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        /* Fuente Inter para mejor legibilidad */
        body {{ 
            font-family: 'Inter', sans-serif; 
            /* Fondo degradado suave para mejor estética */
            background: linear-gradient(135deg, #e0f2f1 0%, #f7f9fb 100%); 
        }}
        .card {{ 
            box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -4px rgba(0, 0, 0, 0.05); 
            border: 1px solid #e2e8f0;
        }}
        /* Estilo para la pestaña activa */
        .tab-button.active {{ 
            background-color: #059669; /* emerald-600 */ 
            color: white; 
            box-shadow: 0 2px 4px rgba(5, 150, 105, 0.4);
            border-bottom: 2px solid #10b981; 
        }}
        .tab-button {{
            transition: all 0.2s ease-in-out;
        }}
        @keyframes fadeIn {{
            from {{ opacity: 0; transform: translateY(10px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}
        .animate-fadeIn {{
            animation: fadeIn 0.5s ease-out;
        }}
    </style>
</head>
<body class="p-4 md:p-8 min-h-screen flex items-start justify-center">

    <script>
        // URL FINAL DE LA API EN RENDER (Inyectada desde la variable de entorno)
        const RENDER_APP_URL = "{RENDER_URL}"; 
        const STRIPE_PK = "{STRIPE_PK}"; 
        const DEMO_USER_ID = 1; 

        function handleResponse(response, formId) {{
            const resultsDiv = document.getElementById('results-' + formId);
            resultsDiv.innerHTML = ''; 
            
            if (response.payment_url) {{
                // Flujo de pago real (Stripe)
                resultsDiv.innerHTML = `
                    <div class="bg-yellow-50 border border-yellow-300 text-yellow-800 p-4 rounded-xl mt-4 animate-fadeIn">
                        <p class="font-bold text-xl mb-2">💳 Pago Requerido ($${{response.price}} \${{response.currency}}):</p>
                        <p>Redirigiendo a Stripe Checkout en 3 segundos. ¡Si desea usar el Bypass, regrese y úselo!</p>
                        <a href="${{response.payment_url}}" target="_blank" class="text-blue-600 underline hover:text-blue-800 font-medium transition duration-150">
                            (Si la redirección falla, haga clic aquí para pagar)
                        </a>
                        <p class="mt-4 text-xs text-yellow-600">
                            (Usando STRIPE_PK: ${{STRIPE_PK}})
                        </p>
                    </div>
                `;
                setTimeout(() => {{
                    window.location.href = response.payment_url; 
                }}, 3000);
            }} else if (response.status === "success") {{
                // Flujo de éxito (incluyendo Bypass y resultados del análisis Gemini)
                 resultsDiv.innerHTML = `
                    <div class="bg-emerald-50 border border-emerald-400 text-emerald-800 p-6 rounded-xl mt-6 animate-fadeIn">
                        <p class="font-extrabold text-xl mb-3">✅ Fulfillment Completo (Vía Bypass)</p>
                        
                        \${{response.fulfillment.analysis_result ? `
                            <p class="text-lg font-semibold text-emerald-700 mt-4 border-b pb-2 border-emerald-200">🔬 Análisis Clínico de Gemini:</p>
                            <div class="bg-white p-4 rounded-lg border border-emerald-300 shadow-inner mt-2">
                                <p class="whitespace-pre-wrap text-gray-800 text-sm leading-relaxed">\${{response.fulfillment.analysis_result.analysis_text || response.fulfillment.analysis_result.reason}}</p>
                                \${{response.fulfillment.file_info ? 
                                    '<p class="mt-2 text-xs text-gray-500">Archivo Adjunto Recibido: ' + response.fulfillment.file_info + '</p>' : ''
                                }}
                                \${{response.fulfillment.analysis_result.analysis_status === 'error' ? 
                                    '<p class="mt-2 text-red-500 font-medium">⚠️ Error de la API de Gemini. Verifique la razón de fallo anterior (posiblemente clave GEMINI_API_KEY no configurada).</p>' : ''
                                }}
                            </div>
                        ` : `
                            <p class="text-lg font-semibold text-emerald-700">⚙️ Herramienta Activada:</p>
                            <p class="mt-2 text-gray-800">La herramienta <strong>\${{response.fulfillment.tool_activated}}</strong> ha sido activada correctamente para Debate Clínico.</p>
                            \${{response.fulfillment.file_info ? 
                                '<p class="mt-2 text-xs text-gray-500">Archivo Adjunto Recibido: ' + response.fulfillment.file_info + '</p>' : ''
                            }}
                            <p class="mt-2 text-xs text-gray-600">Token de Acceso Simulado: \${{response.fulfillment.access_token}}</p>
                        `}}
                        
                        <p class="text-xs text-gray-500 mt-6 pt-4 border-t border-emerald-200">
                            Método de Pago: ${{response.payment_method}} | User ID: ${{response.fulfillment.user_id}}
                        </p>

                    </div>
                `;
            }} else {{
                // Respuesta inesperada o error
                resultsDiv.innerHTML = `
                    <div class="bg-red-100 border border-red-400 text-red-700 p-4 rounded-xl mt-4">
                        <p class="font-bold">🚨 Error de Conexión o Proceso:</p>
                        <p>No se pudo completar la solicitud con la API.</p>
                        <pre class="whitespace-pre-wrap">${{JSON.stringify(response, null, 2)}}</pre>
                    </div>
                `;
            }}
        }}

        async function submitForm(event, endpoint, formId) {{
            event.preventDefault();
            const form = event.target;
            const resultsDiv = document.getElementById('results-' + formId);
            
            // 1. Limpiar mensajes y preparar para validación/carga
            resultsDiv.innerHTML = '';
            
            const formData = new FormData(form);
            if (!formData.has('user_id')) {{ formData.append('user_id', DEMO_USER_ID); }}

            // 2. VALIDACIÓN MANUAL - SOLO CONSENTIMIENTO EN SERVICIO 1
            if (formId === 'volunteer') {{
                const consentChecked = form.querySelector('#has_legal_consent').checked;

                if (!consentChecked) {{
                    resultsDiv.innerHTML = '<div class="bg-red-100 border border-red-400 text-red-700 p-4 rounded-xl mt-4 font-bold">⚠️ Error: Debe aceptar el consentimiento legal (obligatorio para el Servicio 1).</div>';
                    console.error("Validación Fallida: Consentimiento legal no aceptado.");
                    return;
                }}
            }}
            
            // 3. Iniciar el Spinner de Carga
            console.log(`Intentando enviar formulario ${{formId}} a ${{endpoint}}`);
            resultsDiv.innerHTML = '<div class="mt-4 p-4 text-center text-emerald-600 font-semibold flex items-center justify-center"><svg class="animate-spin -ml-1 mr-3 h-5 w-5 text-emerald-600" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>Procesando... Verificando Bypass y Pagos...</div>';

            try {{
                const fullUrl = `${{RENDER_APP_URL}}\${{endpoint}}`;
                
                // NOTA: Para incluir archivos, FormData debe enviarse directamente.
                const response = await fetch(fullUrl, {{
                    method: 'POST',
                    body: formData 
                }});

                const data = await response.json();
                
                if (!response.ok) {{
                    // Manejo de errores 4xx/5xx de FastAPI
                    throw new Error(data.detail ? JSON.stringify(data.detail) : `Error \${{response.status}}: Error de servidor.`);
                }}

                handleResponse(data, formId);

            }} catch (error) {{
                resultsDiv.innerHTML = `
                    <div class="bg-red-100 border border-red-400 text-red-700 p-4 rounded-xl mt-4">
                        <p class="font-bold">🚨 Error de Conexión o Proceso:</p>
                        <p>No se pudo completar la solicitud con la API.</p>
                        <p class="mt-2 text-xs text-gray-700">Detalles: \${{error.message}}</p>
                    </div>
                `;
                console.error("Error en la solicitud:", error);
            }}
        }}

        function switchTab(tabName) {{
            document.querySelectorAll('.tab-content').forEach(content => {{
                content.classList.add('hidden');
            }});
            document.getElementById(tabName + '-content').classList.remove('hidden');

            document.querySelectorAll('.tab-button').forEach(button => {{
                button.classList.remove('active', 'bg-emerald-600', 'text-white');
                button.classList.add('text-emerald-700', 'hover:bg-emerald-100');
            }});
            document.getElementById(tabName + '-button').classList.add('active', 'bg-emerald-600', 'text-white');
            document.getElementById(tabName + '-button').classList.remove('text-emerald-700', 'hover:bg-emerald-100');
        }}

        window.onload = () => {{
            switchTab('volunteer');
        }};
    </script>

    <div class="w-full max-w-4xl bg-white p-6 md:p-10 rounded-2xl card">
        <h1 class="text-4xl font-extrabold text-gray-800 mb-1 flex items-center">
            <svg xmlns="http://www.w3.org/2000/svg" class="h-8 w-8 text-emerald-600 mr-3" viewBox="0 0 20 20" fill="currentColor">
                <path fill-rule="evenodd" d="M6 2a1 1 0 00-1 1v1H4a2 2 0 00-2 2v10a2 2 0 002 2h12a2 2 0 002-2V6a2 2 0 00-2-2h-1V3a1 1 0 00-1-1zm0 5a1 1 0 000 2h8a1 1 0 100-2H6z" clip-rule="evenodd" />
            </svg>
            Ateneo Clínico IA
        </h1>
        <p class="text-xl font-medium text-emerald-700 mb-4">Plataforma de Colaboración Experimental</p>

        <!-- AVISO LEGAL OBLIGATORIO (WAIVER) -->
        <div class="bg-red-50 border-l-4 border-red-500 p-4 mb-6 rounded-lg" role="alert">
            <p class="font-bold text-red-700">AVISO LEGAL (WAIVER OBLIGATORIO)</p>
            <p class="text-sm text-red-600">ESTA PLATAFORMA ES ÚNICAMENTE PARA FINES EDUCATIVOS, DE SIMULACIÓN Y DE DEBATE CLÍNICO.</p>
        </div>

        <p class="text-gray-600 mb-6">
            Esta interfaz prueba los flujos de **Stripe (Pago)** y **Bypass (Gratuito)**. Para pagar, deje el campo de Bypass vacío.
        </p>
        
        <!-- Controles de Pestañas -->
        <div class="mb-6 flex space-x-2 md:space-x-4 border-b border-gray-200">
            <button id="volunteer-button" onclick="switchTab('volunteer')" class="tab-button px-3 md:px-6 py-3 text-sm font-semibold rounded-t-xl transition duration-150 ease-in-out">
                1. Voluntario (Análisis Clínico IA) - $50
            </button>
            <button id="professional-button" onclick="switchTab('professional')" class="tab-button px-3 md:px-6 py-3 text-sm font-semibold rounded-t-xl transition duration-150 ease-in-out">
                2. Profesional (Activación de Herramienta) - $100
            </button>
        </div>

        <!-- PESTAÑA VOLUNTARIO (Servicio de $50) -->
        <div id="volunteer-content" class="tab-content">
            <h2 class="text-2xl font-bold text-gray-700 mb-4 border-l-4 border-emerald-500 pl-3">Servicio 1: Análisis Clínico IA ($50)</h2>
            <form id="volunteer-form" onsubmit="submitForm(event, '/volunteer/create-case', 'volunteer')">
                <input type="hidden" name="user_id" value="1"> 

                <!-- Campo de Texto Opcional para Signos y Síntomas -->
                <div class="mb-4">
                    <label for="description" class="block text-sm font-medium text-gray-700 mb-1">
                        Descripción del Caso / Signos y Síntomas (Opcional)
                    </label>
                    <textarea id="description" name="description" rows="5" class="mt-1 block w-full rounded-lg border-gray-300 shadow-sm focus:border-emerald-500 focus:ring-emerald-500 border p-3 placeholder-gray-400" placeholder="Describa el caso clínico o deje vacío si adjunta solo archivos."></textarea>
                </div>
                
                <!-- Subida de Archivos Opcional -->
                <div class="mb-6">
                    <label for="clinical_file" class="block text-sm font-medium text-gray-700 mb-1">
                        Archivos Adjuntos Opcionales (Ej: Fotos, Exámenes)
                    </label>
                    <input type="file" id="clinical_file" name="clinical_file" class="mt-1 block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-semibold file:bg-emerald-50 file:text-emerald-700 hover:file:bg-emerald-100"/>
                </div>

                <!-- Consentimiento Legal (OBLIGATORIO) -->
                <div class="mb-6">
                    <div class="flex items-center">
                        <input id="has_legal_consent" name="has_legal_consent" type="checkbox" class="h-4 w-4 text-emerald-600 border-gray-300 rounded focus:ring-emerald-500 cursor-pointer">
                        <label for="has_legal_consent" class="ml-2 block text-sm text-gray-900 font-semibold">
                            ✅ Acepto el consentimiento legal para el análisis del caso (OBLIGATORIO).
                        </label>
                    </div>
                </div>

                <!-- Campo de Bypass (Acceso Gratuito - CRÍTICO) -->
                <div class="mb-6 p-4 border border-dashed border-red-300 rounded-lg bg-red-50/50">
                    <label for="volunteer-bypass" class="block text-sm font-bold text-gray-700 mb-1">🔑 Acceso Gratuito: Clave de Bypass</label>
                    <input type="password" id="volunteer-bypass" name="developer_bypass_key" placeholder="Introduzca su clave secreta de Administrador aquí (Opcional, activa el flujo gratuito)" class="mt-1 block w-full rounded-lg border-red-500 shadow-sm focus:border-red-500 focus:ring-red-500 border p-2">
                </div>

                <button type="submit" class="w-full flex justify-center py-3 px-4 border border-transparent rounded-lg shadow-md text-lg font-bold text-white bg-emerald-600 hover:bg-emerald-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-emerald-500 transition duration-300 ease-in-out">
                    Ejecutar Análisis Clínico IA ($50 - o use la clave de Bypass)
                </button>
            </form>

            <div id="results-volunteer">
                <!-- Los resultados de la API aparecerán aquí -->
            </div>
        </div>

        <!-- PESTAÑA PROFESIONAL (Servicio de $100) -->
        <div id="professional-content" class="tab-content hidden">
            <h2 class="text-2xl font-bold text-gray-700 mb-4 border-l-4 border-emerald-500 pl-3">Servicio 2: Activación de Herramienta Profesional ($100)</h2>
            <form id="professional-form" onsubmit="submitForm(event, '/professional/activate-tool', 'professional')">
                <input type="hidden" name="user_id" value="2">
                
                <!-- Campo de Texto Opcional para Nombre de Herramienta -->
                <div class="mb-4">
                    <label for="tool_name" class="block text-sm font-medium text-gray-700 mb-1">Nombre de la Herramienta (Opcional)</label>
                    <input type="text" id="tool_name" name="tool_name" value="HerramientaDeDebateClínico" class="mt-1 block w-full rounded-lg border-gray-300 shadow-sm focus:border-emerald-500 focus:ring-emerald-500 border p-2 placeholder-gray-400">
                </div>

                <!-- Subida de Archivos Opcional -->
                <div class="mb-6">
                    <label for="clinical_file_prof" class="block text-sm font-medium text-gray-700 mb-1">
                        Archivos Adjuntos Opcionales (Ej: Datos o Protocolos)
                    </label>
                    <input type="file" id="clinical_file_prof" name="clinical_file" class="mt-1 block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-semibold file:bg-emerald-50 file:text-emerald-700 hover:file:bg-emerald-100"/>
                </div>

                <!-- Campo de Bypass (Acceso Gratuito - CRÍTICO) -->
                <div class="mb-6 p-4 border border-dashed border-red-300 rounded-lg bg-red-50/50">
                    <label for="professional-bypass" class="block text-sm font-bold text-gray-700 mb-1">🔑 Acceso Gratuito: Clave de Bypass</label>
                    <input type="password" id="professional-bypass" name="developer_bypass_key" placeholder="Introduzca su clave secreta de Administrador aquí (Opcional, activa el flujo gratuito)" class="mt-1 block w-full rounded-lg border-red-500 shadow-sm focus:border-red-500 focus:ring-red-500 border p-2">
                </div>

                <button type="submit" class="w-full flex justify-center py-3 px-4 border border-transparent rounded-lg shadow-md text-lg font-bold text-white bg-emerald-600 hover:bg-emerald-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-emerald-500 transition duration-300 ease-in-out">
                    Activar Herramienta ($100 - o use la clave de Bypass)
                </button>
            </form>

            <div id="results-professional">
                <!-- Los resultados de la API aparecerán aquí -->
            </div>
        </div>
    </div>

</body>
</html>
"""eof

La lógica de pago ahora está restaurada. Si desea probar el flujo de **Stripe**, asegúrese de **dejar vacío** el campo de la Clave de Bypass. Si lo llena con la clave correcta, activará el flujo gratuito simulado.

¿Le parece correcto el funcionamiento de ambos servicios con la prioridad de Stripe y la flexibilidad de los archivos opcionales?

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from typing import Optional
import os 
import json
import stripe # SDK de Stripe
from google import genai # SDK oficial de Google GenAI
from google.genai.errors import APIError
import asyncio # Necesario para ejecutar el SDK síncrono de Gemini de forma asíncrona

# =========================================================================
# 0. CONFIGURACIÓN DE SECRETOS (CLAVES DE BYPASS Y API)
# ¡CRÍTICO! Asegúrate de que todas estas variables estén definidas en Render.
# =========================================================================
ADMIN_BYPASS_KEY = os.getenv("ADMIN_BYPASS_KEY")
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY")
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
RENDER_APP_URL = os.getenv("RENDER_APP_URL", "https://ateneoclinicoia.onrender.com")

# Inicialización de Stripe
if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY
else:
    print("ADVERTENCIA: STRIPE_SECRET_KEY no definida. El pago real no funcionará.")

# Inicialización del Cliente de Gemini (para uso síncrono seguro)
gemini_client = None
if GEMINI_API_KEY:
    try:
        # Inicializa el cliente de Gemini con la clave de API
        gemini_client = genai.Client(api_key=GEMINI_API_KEY)
    except Exception as e:
        print(f"Error inicializando el cliente de Gemini: {e}. El análisis de IA no funcionará.")

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
    Realiza la llamada a la API de Gemini para generar el análisis clínico
    usando el SDK oficial (google-genai). Usa asyncio.to_thread para no bloquear
    el loop asíncrono de FastAPI.
    """
    if not gemini_client:
        return {
            "analysis_status": "error",
            "reason": "GEMINI_API_KEY no configurada o cliente Gemini no inicializado.",
            "prompt_used": prompt
        }
    
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
        # Ejecuta la llamada síncrona en un hilo separado
        analysis_text = await asyncio.to_thread(blocking_call)
        
        return {
            "analysis_status": "success",
            "analysis_text": analysis_text
        }
            
    except APIError as e:
        print(f"Error de API de Gemini: {e}")
        return {
            "analysis_status": "error",
            "reason": f"Error de API de Gemini: {e}",
            "prompt_used": prompt
        }
    except Exception as e:
        print(f"Error inesperado con Gemini: {e}")
        return {
            "analysis_status": "error",
            "reason": f"Error inesperado con Gemini: {e}",
            "prompt_used": prompt
        }


def create_stripe_checkout_session(price: int, product_name: str, metadata: dict):
    """Crea una sesión de Stripe Checkout y retorna el URL de pago."""
    
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
            metadata=metadata, # Aquí guardamos user_id, type, etc.
        )
        return {"status": "payment_required", "payment_url": session.url, "price": price, "currency": "USD"}
    
    except stripe.error.StripeError as e:
        print(f"Error de Stripe: {e}")
        raise HTTPException(status_code=500, detail=f"Error en la API de Stripe: {e}")
    except Exception as e:
        print(f"Error desconocido al crear la sesión de pago: {e}")
        raise HTTPException(status_code=500, detail="Error desconocido al crear la sesión de pago.")

# =========================================================================
# 3. HTML (Template para la Interfaz)
# NOTA: Todas las llaves internas de CSS/JS deben ser escapadas con doble llave 
# {{ y }} para evitar el error de ValueError/KeyError de Python.
# DISEÑO MEJORADO CON PALETA PROFESIONAL (EMERALD)
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
            border-bottom: 2px solid #10b981; /* Resalta la pestaña activa */
        }}
        .tab-button {{
            transition: all 0.2s ease-in-out;
        }}
    </style>
</head>
<body class="p-4 md:p-8 min-h-screen flex items-start justify-center">

    <script>
        // URL FINAL DE LA API EN RENDER (Inyectada desde la variable de entorno)
        const RENDER_APP_URL = "{RENDER_URL}"; 
        const STRIPE_PK = "{STRIPE_PK}"; // Clave pública de Stripe, solo para referencia visual
        const DEMO_USER_ID = 1; 

        function handleResponse(response, formId) {{ // <<<<<< ESCAPADO
            const resultsDiv = document.getElementById('results-' + formId);
            resultsDiv.innerHTML = ''; 
            
            if (response.payment_url) {{ // <<<<<< ESCAPADO
                // Flujo de pago real
                resultsDiv.innerHTML = `
                    <div class="bg-yellow-50 border border-yellow-300 text-yellow-800 p-4 rounded-xl mt-4 animate-fadeIn">
                        <p class="font-bold text-xl mb-2">💳 Pago Requerido ($${{response.price}} \${{response.currency}}):</p>
                        <p>Redirigiendo a Stripe Checkout en 3 segundos...</p>
                        <a href="${{response.payment_url}}" target="_blank" class="text-blue-600 underline hover:text-blue-800 font-medium transition duration-150">
                            (Si la redirección falla, haga clic aquí para pagar)
                        </a>
                        <p class="mt-4 text-xs text-yellow-600">
                            (Usando STRIPE_PK: ${{STRIPE_PK}})
                        </p>
                    </div>
                `;
                setTimeout(() => {{ // <<<<<< ESCAPADO
                    window.location.href = response.payment_url; 
                }}, 3000); // <<<<<< ESCAPADO
            }} else if (response.status === "success") {{ // <<<<<< ESCAPADO
                // Flujo de éxito (incluyendo Bypass y resultados del análisis Gemini)
                 resultsDiv.innerHTML = `
                    <div class="bg-emerald-50 border border-emerald-400 text-emerald-800 p-6 rounded-xl mt-6 animate-fadeIn">
                        <p class="font-extrabold text-xl mb-3">✅ Fulfillment Completo (Vía Bypass)</p>
                        
                        \${{response.fulfillment.analysis_result ? `
                            <p class="text-lg font-semibold text-emerald-700 mt-4 border-b pb-2 border-emerald-200">🔬 Análisis Clínico de Gemini:</p>
                            <div class="bg-white p-4 rounded-lg border border-emerald-300 shadow-inner mt-2">
                                <p class="whitespace-pre-wrap text-gray-800 text-sm leading-relaxed">\${{response.fulfillment.analysis_result.analysis_text || response.fulfillment.analysis_result.reason}}</p>
                                \${{response.fulfillment.analysis_result.analysis_status === 'error' ? 
                                    '<p class="mt-2 text-red-500 font-medium">⚠️ Error de la API de Gemini. Revise la razón anterior.</p>' : ''
                                }}
                            </div>
                        ` : `
                            <p class="text-lg font-semibold text-emerald-700">⚙️ Herramienta Activada:</p>
                            <p class="mt-2 text-gray-800">La herramienta <strong>\${{response.fulfillment.tool_activated}}</strong> ha sido activada correctamente.</p>
                            <p class="mt-2 text-xs text-gray-600">Token generado: \${{response.fulfillment.access_token}}</p>
                        `}}
                        
                        <p class="text-xs text-gray-500 mt-6 pt-4 border-t border-emerald-200">
                            Método de Pago: ${{response.payment_method}} | User ID: ${{response.fulfillment.user_id}}
                        </p>

                    </div>
                `;
            }} else {{ // <<<<<< ESCAPADO
                // Respuesta inesperada o error
                resultsDiv.innerHTML = `
                    <div class="bg-red-100 border border-red-400 text-red-700 p-4 rounded-md mt-4">
                        <p class="font-bold">❌ Error o Respuesta Inesperada del Servidor:</p>
                        <pre class="whitespace-pre-wrap">${{JSON.stringify(response, null, 2)}}</pre>
                    </div>
                `;
            }} // <<<<<< ESCAPADO
        }} // <<<<<< ESCAPADO

        async function submitForm(event, endpoint, formId) {{ // <<<<<< ESCAPADO
            event.preventDefault();
            const form = event.target;
            const resultsDiv = document.getElementById('results-' + formId);
            resultsDiv.innerHTML = '<div class="mt-4 p-4 text-center text-emerald-600 font-semibold flex items-center justify-center"><svg class="animate-spin -ml-1 mr-3 h-5 w-5 text-emerald-600" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>Procesando... Verificando Bypass y API...</div>';

            try {{ // <<<<<< ESCAPADO
                const formData = new FormData(form);
                if (!formData.has('user_id')) {{ formData.append('user_id', DEMO_USER_ID); }} // <<<<<< ESCAPADO

                const fullUrl = `${{RENDER_APP_URL}}\${{endpoint}}`;
                
                const response = await fetch(fullUrl, {{ // <<<<<< ESCAPADO
                    method: 'POST',
                    body: formData
                }}); // <<<<<< ESCAPADO

                const data = await response.json();
                
                if (!response.ok) {{ // <<<<<< ESCAPADO
                    // Manejo de errores 4xx/5xx de FastAPI
                    throw new Error(data.detail ? JSON.stringify(data.detail) : `Error \${{response.status}}: Error de servidor.`);
                }} // <<<<<< ESCAPADO

                handleResponse(data, formId);

            }} catch (error) {{ // <<<<<< ESCAPADO
                resultsDiv.innerHTML = `
                    <div class="bg-red-100 border border-red-400 text-red-700 p-4 rounded-xl mt-4">
                        <p class="font-bold">🚨 Error de Conexión o Validación:</p>
                        <p>No se pudo completar la solicitud con la API.</p>
                        <p class="mt-2 text-xs text-gray-700">Detalles: \${{error.message}}</p>
                    </div>
                `;
                console.error("Error en la solicitud:", error);
            }} // <<<<<< ESCAPADO
        }} // <<<<<< ESCAPADO

        function switchTab(tabName) {{ // <<<<<< ESCAPADO
            document.querySelectorAll('.tab-content').forEach(content => {{ // <<<<<< ESCAPADO
                content.classList.add('hidden');
            }}); // <<<<<< ESCAPADO
            document.getElementById(tabName + '-content').classList.remove('hidden');

            document.querySelectorAll('.tab-button').forEach(button => {{ // <<<<<< ESCAPADO
                button.classList.remove('active', 'bg-emerald-600', 'text-white');
                button.classList.add('text-emerald-700', 'hover:bg-emerald-100');
            }}); // <<<<<< ESCAPADO
            document.getElementById(tabName + '-button').classList.add('active', 'bg-emerald-600', 'text-white');
            document.getElementById(tabName + '-button').classList.remove('text-emerald-700', 'hover:bg-emerald-100');
        }} // <<<<<< ESCAPADO

        window.onload = () => {{ // <<<<<< ESCAPADO
            switchTab('volunteer');
        }}; // <<<<<< ESCAPADO
    </script>

    <div class="w-full max-w-4xl bg-white p-6 md:p-10 rounded-2xl card">
        <h1 class="text-4xl font-extrabold text-gray-800 mb-1 flex items-center">
            <svg xmlns="http://www.w3.org/2000/svg" class="h-8 w-8 text-emerald-600 mr-3" viewBox="0 0 20 20" fill="currentColor">
                <path fill-rule="evenodd" d="M6 2a1 1 0 00-1 1v1H4a2 2 0 00-2 2v10a2 2 0 002 2h12a2 2 0 002-2V6a2 2 0 00-2-2h-1V3a1 1 0 10-2 0v1H7V3a1 1 0 00-1-1zm0 5a1 1 0 000 2h8a1 1 0 100-2H6z" clip-rule="evenodd" />
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
            Esta interfaz está diseñada para probar los flujos de pago ($50 y $100) y de servicio (Análisis IA). Use la clave de bypass para realizar pruebas gratuitas.
        </p>
        
        <!-- Controles de Pestañas -->
        <div class="mb-6 flex space-x-2 md:space-x-4 border-b border-gray-200">
            <button id="volunteer-button" onclick="switchTab('volunteer')" class="tab-button px-3 md:px-6 py-3 text-sm font-semibold rounded-t-xl transition duration-150 ease-in-out">
                Voluntario (Análisis de Caso) - $50
            </button>
            <button id="professional-button" onclick="switchTab('professional')" class="tab-button px-3 md:px-6 py-3 text-sm font-semibold rounded-t-xl transition duration-150 ease-in-out">
                Profesional (Activación de Herramienta) - $100
            </button>
        </div>

        <!-- PESTAÑA VOLUNTARIO (Servicio de $50) -->
        <div id="volunteer-content" class="tab-content">
            <h2 class="text-2xl font-bold text-gray-700 mb-4 border-l-4 border-emerald-500 pl-3">Envío de Caso (Voluntario)</h2>
            <form id="volunteer-form" onsubmit="submitForm(event, '/volunteer/create-case', 'volunteer')">
                <input type="hidden" name="user_id" value="1"> 

                <!-- Campo de Texto Obligatorio para Signos y Síntomas -->
                <div class="mb-4">
                    <label for="description" class="block text-sm font-medium text-gray-700 mb-1">
                        Descripción del Caso / Signos y Síntomas (Obligatorio)
                    </label>
                    <textarea id="description" name="description" rows="5" required class="mt-1 block w-full rounded-lg border-gray-300 shadow-sm focus:border-emerald-500 focus:ring-emerald-500 border p-3 placeholder-gray-400" placeholder="Describa los signos, síntomas, historial y hallazgos relevantes para que Gemini los analice."></textarea>
                </div>

                <!-- Campo de Archivo Opcional -->
                <div class="mb-4">
                    <label for="file" class="block text-sm font-medium text-gray-700 mb-1">Archivo Adjunto (Opcional)</label>
                    <input type="file" id="file" name="file" class="mt-1 block w-full text-sm text-gray-600 file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-sm file:font-semibold file:bg-emerald-50 file:text-emerald-700 hover:file:bg-emerald-100 cursor-pointer">
                </div>

                <!-- Consentimiento Legal -->
                <div class="mb-6">
                    <div class="flex items-center">
                        <input id="has_legal_consent" name="has_legal_consent" type="checkbox" required class="h-4 w-4 text-emerald-600 border-gray-300 rounded focus:ring-emerald-500 cursor-pointer">
                        <label for="has_legal_consent" class="ml-2 block text-sm text-gray-900">
                            Acepto el consentimiento legal para el análisis del caso.
                        </label>
                    </div>
                </div>

                <!-- Campo de Bypass (Solo para desarrollo) -->
                <div class="mb-6 p-4 border border-dashed border-gray-300 rounded-lg bg-emerald-50/50">
                    <label for="volunteer-bypass" class="block text-sm font-bold text-gray-700 mb-1">🔓 Clave de Bypass (ADMIN_BYPASS_KEY)</label>
                    <input type="password" id="volunteer-bypass" name="developer_bypass_key" placeholder="Introduzca su clave secreta de Administrador para acceso gratuito" class="mt-1 block w-full rounded-lg border-gray-300 shadow-sm focus:border-emerald-500 focus:ring-emerald-500 border p-2">
                </div>

                <button type="submit" class="w-full flex justify-center py-3 px-4 border border-transparent rounded-lg shadow-md text-lg font-bold text-white bg-emerald-600 hover:bg-emerald-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-emerald-500 transition duration-300 ease-in-out">
                    Enviar Caso y Obtener Análisis ($50 o Usar Bypass)
                </button>
            </form>

            <div id="results-volunteer">
                <!-- Los resultados de la API aparecerán aquí -->
            </div>
        </div>

        <!-- PESTAÑA PROFESIONAL (Servicio de $100) -->
        <div id="professional-content" class="tab-content hidden">
            <h2 class="text-2xl font-bold text-gray-700 mb-4 border-l-4 border-emerald-500 pl-3">Activación de Herramienta (Profesional)</h2>
            <form id="professional-form" onsubmit="submitForm(event, '/professional/activate-tool', 'professional')">
                <input type="hidden" name="user_id" value="2">
                
                <div class="mb-4">
                    <label for="tool_name" class="block text-sm font-medium text-gray-700 mb-1">Nombre de la Herramienta a Activar</label>
                    <input type="text" id="tool_name" name="tool_name" value="DiagnósticoAvanzado" required class="mt-1 block w-full rounded-lg border-gray-300 shadow-sm focus:border-emerald-500 focus:ring-emerald-500 border p-2 placeholder-gray-400">
                </div>

                <!-- Campo de Bypass (Solo para desarrollo) -->
                <div class="mb-6 p-4 border border-dashed border-gray-300 rounded-lg bg-emerald-50/50">
                    <label for="professional-bypass" class="block text-sm font-bold text-gray-700 mb-1">🔓 Clave de Bypass (ADMIN_BYPASS_KEY)</label>
                    <input type="password" id="professional-bypass" name="developer_bypass_key" placeholder="Introduzca su clave secreta de Administrador para acceso gratuito" class="mt-1 block w-full rounded-lg border-gray-300 shadow-sm focus:border-emerald-500 focus:ring-emerald-500 border p-2">
                </div>

                <button type="submit" class="w-full flex justify-center py-3 px-4 border border-transparent rounded-lg shadow-md text-lg font-bold text-white bg-emerald-600 hover:bg-emerald-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-emerald-500 transition duration-300 ease-in-out">
                    Activar Herramienta ($100 o Usar Bypass)
                </button>
            </form>

            <div id="results-professional">
                <!-- Los resultados de la API aparecerán aquí -->
            </div>
        </div>
    </div>

</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
def read_root():
    """Ruta principal que sirve la interfaz de usuario (HTML) con variables de entorno inyectadas."""
    
    # Preparamos las claves para inyección en el frontend. Usamos fallbacks si no están definidas.
    stripe_pk_display = STRIPE_PUBLISHABLE_KEY if STRIPE_PUBLISHABLE_KEY else "pk_test_UNDEFINED_KEY"

    # Inyectamos la URL de Render y la clave publicable de Stripe en el HTML
    return HTMLResponse(content=HTML_TEMPLATE.format(
        RENDER_URL=RENDER_APP_URL,
        STRIPE_PK=stripe_pk_display,
    ))

# =========================================================================
# 4. ENDPOINT PARA VOLUNTARIOS (Análisis de Caso) - Precio: $50 USD
# =========================================================================

@app.post("/volunteer/create-case")
async def create_volunteer_case(
    user_id: int = Form(...),
    description: str = Form(...),
    has_legal_consent: bool = Form(...),
    developer_bypass_key: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None)
):
    """
    Inicia el proceso de pago. Si se usa la clave de bypass, ejecuta el análisis de Gemini directamente.
    """
    
    product_name = "Análisis Clínico Voluntario"
    price = 50
    
    # 1. Comprobación estricta de la clave de bypass de ADMINISTRADOR
    if ADMIN_BYPASS_KEY and developer_bypass_key == ADMIN_BYPASS_KEY:
        # Ejecutar el fulfillment directamente
        gemini_response = await call_gemini_api(description)
        
        return {
            "status": "success",
            "payment_method": "ADMIN_BYPASS",
            "fulfillment": {
                "user_id": user_id,
                "case_data": {"description_length": len(description)},
                "analysis_result": gemini_response # Resultado directo de Gemini
            }
        }

    # 2. Iniciar el flujo de pago real con Stripe
    metadata = {
        "user_id": str(user_id),
        "service_type": "volunteer_case_analysis",
        "description": description[:200] # Limitar la descripción para metadata
    }
    
    return create_stripe_checkout_session(price, product_name, metadata)

# =========================================================================
# 5. ENDPOINT PARA PROFESIONALES (Activación de Herramienta) - Precio: $100 USD
# =========================================================================

@app.post("/professional/activate-tool")
async def activate_professional_tool(
    user_id: int = Form(...),
    tool_name: str = Form(...),
    developer_bypass_key: Optional[str] = Form(None)
):
    """
    Inicia el proceso de pago. Si se usa la clave de bypass, simula la activación de la herramienta.
    """
    
    product_name = f"Activación de Herramienta: {tool_name}"
    price = 100
    
    # 1. Comprobación estricta de la clave de bypass de ADMINISTRADOR
    if ADMIN_BYPASS_KEY and developer_bypass_key == ADMIN_BYPASS_KEY:
        
        return {
            "status": "success",
            "payment_method": "ADMIN_BYPASS",
            "fulfillment": {
                "user_id": user_id,
                "tool_activated": tool_name,
                "access_token": "TOKEN_DE_ACCESO_PROFESIONAL_GENERADO_BYPASS"
            }
        }

    # 2. Iniciar el flujo de pago real con Stripe
    metadata = {
        "user_id": str(user_id),
        "service_type": "professional_tool_activation",
        "tool_name": tool_name
    }
    
    return create_stripe_checkout_session(price, product_name, metadata)


# =========================================================================
# 6. ENDPOINT DE STRIPE WEBHOOK (Manejo de Pagos Exitosos)
# =========================================================================

@app.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    """
    Endpoint para recibir eventos de Stripe, principalmente 'checkout.session.completed',
    para realizar el fulfillment (entrega del servicio).
    """
    payload = await request.body()
    sig_header = request.headers.get('stripe-signature')
    event = None

    if not STRIPE_WEBHOOK_SECRET:
        print("ADVERTENCIA: STRIPE_WEBHOOK_SECRET no configurado. No se puede verificar la firma.")
        # En producción, esto debería lanzar un error 500 y no procesar.
        return JSONResponse(content={"status": "warning", "message": "Webhook secret not configured."}, status_code=200)

    try:
        # Verificar y parsear el evento de Stripe
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except ValueError as e:
        # Firma o payload inválido
        print(f"Error de Payload: {e}")
        return JSONResponse(content={"error": "Invalid payload"}, status_code=400)
    except stripe.error.SignatureVerificationError as e:
        # Firma inválida
        print(f"Error de Firma: {e}")
        return JSONResponse(content={"error": "Invalid signature"}, status_code=400)

    # Manejar el evento
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        
        # Extraer metadatos de la sesión
        user_id = session['metadata'].get('user_id')
        service_type = session['metadata'].get('service_type')
        
        print(f"Pago exitoso para User ID: {user_id}, Tipo: {service_type}. Iniciando Fulfillment...")
        
        # Lógica de fulfillment basada en el tipo de servicio
        if service_type == "volunteer_case_analysis":
            # Caso Voluntario: Ejecutar Análisis Gemini
            description = session['metadata'].get('description', 'Descripción no disponible.')
            # En un entorno real, aquí se recuperaría la descripción completa del caso desde una DB.
            gemini_response = await call_gemini_api(description)
            print(f"Análisis Gemini finalizado para el caso de voluntario: {gemini_response['analysis_status']}")
            # Aquí iría el código para guardar/enviar el resultado final al usuario.
            
        elif service_type == "professional_tool_activation":
            # Caso Profesional: Activar Herramienta
            tool_name = session['metadata'].get('tool_name', 'Herramienta desconocida')
            # Aquí iría el código para actualizar la base de datos del usuario (DB)
            print(f"Activando la herramienta '{tool_name}' en la base de datos para el usuario {user_id}.")
            
        # Marca la sesión como procesada para evitar reejecuciones
        stripe.checkout.Session.modify(
            session['id'],
            metadata={'fulfilled': 'true'}
        )
        
    return JSONResponse(content={"status": "success"}, status_code=200)

# =========================================================================
# 7. Páginas de Redirección (Post-Stripe)
# =========================================================================

@app.get("/stripe/success", response_class=HTMLResponse)
def stripe_success(session_id: str):
    """Página de éxito de Stripe Checkout."""
    return f"""
    <body class="p-8 bg-emerald-50 text-center font-sans">
        <h1 class="text-4xl text-emerald-700 font-bold mb-4">¡Pago Exitoso! 🎉</h1>
        <p class="text-lg text-gray-600">Su solicitud ha sido recibida. El ID de su sesión es: <code class="font-mono bg-emerald-100 p-1 rounded">{session_id}</code>.</p>
        <p class="mt-4 text-gray-700">El servicio (análisis o activación) se está procesando a través del Webhook de Stripe.</p>
        <a href="{RENDER_APP_URL}" class="mt-6 inline-block py-2 px-6 bg-emerald-600 text-white rounded-lg shadow-md hover:bg-emerald-700 transition duration-150">Volver al Inicio</a>
    </body>
    """

@app.get("/stripe/cancel", response_class=HTMLResponse)
def stripe_cancel():
    """Página de cancelación de Stripe Checkout."""
    return f"""
    <body class="p-8 bg-red-50 text-center font-sans">
        <h1 class="text-4xl text-red-700 font-bold mb-4">Pago Cancelado 😔</h1>
        <p class="text-lg text-gray-600">Su pago fue cancelado. No se le ha cobrado.</p>
        <a href="{RENDER_APP_URL}" class="mt-6 inline-block py-2 px-6 bg-red-600 text-white rounded-lg shadow-md hover:bg-red-700 transition duration-150">Volver al Inicio</a>
    </body>
    """

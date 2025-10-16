from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from typing import Optional
import os 
import json
import httpx # Necesario para realizar llamadas HTTP asíncronas (e.g., a la API de Gemini)
import stripe # SDK de Stripe

# =========================================================================
# 0. CONFIGURACIÓN DE SECRETOS (CLAVES DE BYPASS Y API)
# Se leen directamente de las variables de entorno de Render.
# ¡CRÍTICO! Asegúrate de que todas estas variables estén definidas en Render.
# =========================================================================
ADMIN_BYPASS_KEY = os.getenv("ADMIN_BYPASS_KEY")
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY")
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
RENDER_APP_URL = os.getenv("RENDER_APP_URL", "https://ateneoclinicoia.onrender.com")

# Inicialización de Stripe con la clave secreta
if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY
else:
    print("ADVERTENCIA: STRIPE_SECRET_KEY no definida. El pago real no funcionará.")

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
    Realiza la llamada a la API de Gemini para generar el análisis clínico.
    Esta función se ejecuta al completar el pago (webhook) o al usar el bypass.
    """
    if not GEMINI_API_KEY:
        return {
            "analysis_status": "error",
            "reason": "GEMINI_API_KEY no configurada. No se pudo generar el análisis.",
            "prompt_used": prompt
        }
    
    # URL de la API de Gemini (usando un modelo flash para velocidad)
    api_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
    
    headers = {
        "Content-Type": "application/json"
    }

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "systemInstruction": "Eres un analista clínico experto. Genera un resumen conciso y profesional del caso, incluyendo posibles diagnósticos diferenciales y pasos sugeridos, limitándote a un máximo de 300 palabras.",
        "config": {
            "apiKey": GEMINI_API_KEY
        }
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(api_url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            
            gemini_result = response.json()
            analysis_text = gemini_result.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "Análisis no disponible.")
            
            return {
                "analysis_status": "success",
                "analysis_text": analysis_text
            }
            
    except httpx.HTTPError as e:
        return {
            "analysis_status": "error",
            "reason": f"Error HTTP al llamar a Gemini: {e}",
            "prompt_used": prompt
        }
    except Exception as e:
        return {
            "analysis_status": "error",
            "reason": f"Error inesperado en la API de Gemini: {e}",
            "prompt_used": prompt
        }

def create_stripe_checkout_session(price: int, product_name: str, metadata: dict):
    """Crea una sesión de Stripe Checkout y retorna el URL de pago."""
    
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
                        'metadata': {'type': metadata.get('type')}
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
    
    except stripe.error.InvalidRequestError as e:
        print(f"Error de solicitud de Stripe: {e}")
        raise HTTPException(status_code=500, detail=f"Error en la configuración de Stripe: {e}")
    except Exception as e:
        print(f"Error inesperado de Stripe: {e}")
        raise HTTPException(status_code=500, detail="Error desconocido al crear la sesión de pago.")

# =========================================================================
# 3. HTML (Template para la Interfaz)
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
        body { font-family: 'Inter', sans-serif; background-color: #f7f9fb; }
        .card { box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -2px rgba(0, 0, 0, 0.06); }
        /* Estilo para la pestaña activa */
        .tab-button.active { background-color: #10b981; color: white; }
    </style>
</head>
<body class="p-4 md:p-8 min-h-screen flex items-start justify-center">

    <script>
        // URL FINAL DE LA API EN RENDER (Inyectada desde la variable de entorno)
        const RENDER_APP_URL = "{RENDER_URL}"; 
        const STRIPE_PK = "{STRIPE_PK}"; // Clave pública de Stripe, solo para referencia visual
        const DEMO_USER_ID = 1; 

        function handleResponse(response, formId) {
            const resultsDiv = document.getElementById('results-' + formId);
            resultsDiv.innerHTML = ''; 
            
            if (response.payment_url) {
                // Flujo de pago real
                resultsDiv.innerHTML = `
                    <div class="bg-yellow-100 border border-yellow-400 text-yellow-700 p-4 rounded-md mt-4">
                        <p class="font-bold">Pago Requerido ($${response.price} ${response.currency}):</p>
                        <p>Redirigiendo a Stripe Checkout en 3 segundos...</p>
                        <a href="${response.payment_url}" target="_blank" class="text-blue-600 underline hover:text-blue-800">
                            (Si la redirección falla, haga clic aquí para pagar)
                        </a>
                        <p class="mt-2 text-xs text-yellow-600">
                            Usando STRIPE_PK (Public Key): ${STRIPE_PK}
                        </p>
                    </div>
                `;
                setTimeout(() => {
                    window.location.href = response.payment_url; 
                }, 3000);
            } else if (response.status === "success") {
                // Flujo de éxito (incluyendo Bypass y resultados del análisis Gemini)
                 resultsDiv.innerHTML = `
                    <div class="bg-green-100 border border-green-400 text-green-700 p-4 rounded-md mt-4">
                        <p class="font-bold">✅ Operación Exitosa (Bypass/Pago Realizado):</p>
                        <pre class="whitespace-pre-wrap">${JSON.stringify(response, null, 2)}</pre>
                    </div>
                `;
            } else {
                // Respuesta inesperada o error
                resultsDiv.innerHTML = `
                    <div class="bg-red-100 border border-red-400 text-red-700 p-4 rounded-md mt-4">
                        <p class="font-bold">Error o Respuesta Inesperada:</p>
                        <pre class="whitespace-pre-wrap">${JSON.stringify(response, null, 2)}</pre>
                    </div>
                `;
            }
        }

        async function submitForm(event, endpoint, formId) {
            event.preventDefault();
            const form = event.target;
            const resultsDiv = document.getElementById('results-' + formId);
            resultsDiv.innerHTML = '<div class="mt-4 p-4 text-center text-blue-500 font-semibold">Procesando... Verificando API...</div>';

            try {
                const formData = new FormData(form);
                if (!formData.has('user_id')) { formData.append('user_id', DEMO_USER_ID); }

                const fullUrl = `${RENDER_APP_URL}${endpoint}`;
                
                const response = await fetch(fullUrl, {
                    method: 'POST',
                    body: formData
                });

                const data = await response.json();
                
                if (!response.ok) {
                    throw new Error(data.detail ? JSON.stringify(data.detail) : `Error ${response.status}: Error de servidor.`);
                }

                handleResponse(data, formId);

            } catch (error) {
                resultsDiv.innerHTML = `
                    <div class="bg-red-100 border border-red-400 text-red-700 p-4 rounded-md mt-4">
                        <p class="font-bold">Error de Conexión o Validación:</p>
                        <p>No se pudo completar la solicitud con la API.</p>
                        <p class="mt-2 text-xs text-gray-700">Detalles: ${error.message}</p>
                    </div>
                `;
                console.error("Error en la solicitud:", error);
            }
        }

        function switchTab(tabName) {
            document.querySelectorAll('.tab-content').forEach(content => {
                content.classList.add('hidden');
            });
            document.getElementById(tabName + '-content').classList.remove('hidden');

            document.querySelectorAll('.tab-button').forEach(button => {
                button.classList.remove('active', 'bg-green-600', 'text-white');
                button.classList.add('text-green-700', 'hover:bg-green-100');
            });
            document.getElementById(tabName + '-button').classList.add('active', 'bg-green-600', 'text-white');
            document.getElementById(tabName + '-button').classList.remove('text-green-700', 'hover:bg-green-100');
        }

        window.onload = () => {
            switchTab('volunteer');
        };
    </script>

    <div class="w-full max-w-4xl bg-white p-6 md:p-10 rounded-xl card">
        <h1 class="text-3xl font-extrabold text-gray-800 mb-1">Ateneo Clínico IA Demo</h1>
        <p class="text-lg font-medium text-green-700 mb-4">Plataforma de Colaboración Experimental</p>

        <!-- AVISO LEGAL OBLIGATORIO (WAIVER) -->
        <div class="bg-red-50 border-l-4 border-red-500 p-4 mb-6 rounded-md" role="alert">
            <p class="font-bold text-red-700">AVISO LEGAL (WAIVER OBLIGATORIO)</p>
            <p class="text-sm text-red-600">ESTA PLATAFORMA ES ÚNICAMENTE PARA FINES EDUCATIVOS, DE SIMULACIÓN Y DE DEBATE CLÍNICO.</p>
        </div>

        <p class="text-gray-600 mb-6">
            Esta es una interfaz de prueba para los dos servicios de pago. Use la clave de bypass de administrador para saltar el pago de Stripe.
        </p>
        
        <!-- Controles de Pestañas -->
        <div class="mb-6 flex space-x-4 border-b border-gray-200">
            <button id="volunteer-button" onclick="switchTab('volunteer')" class="tab-button px-4 py-2 text-sm font-medium rounded-t-lg transition duration-150 ease-in-out">
                Voluntario (Análisis de Caso) - $50
            </button>
            <button id="professional-button" onclick="switchTab('professional')" class="tab-button px-4 py-2 text-sm font-medium rounded-t-lg transition duration-150 ease-in-out">
                Profesional (Activación de Herramienta) - $100
            </button>
        </div>

        <!-- PESTAÑA VOLUNTARIO (Servicio de $50) -->
        <div id="volunteer-content" class="tab-content">
            <h2 class="text-2xl font-semibold text-gray-700 mb-4">Envío de Caso (Voluntario) - Precio: $50 USD</h2>
            <form id="volunteer-form" onsubmit="submitForm(event, '/volunteer/create-case', 'volunteer')">
                <input type="hidden" name="user_id" value="1"> 

                <!-- Campo de Texto Obligatorio para Signos y Síntomas -->
                <div class="mb-4">
                    <label for="description" class="block text-sm font-medium text-gray-700">
                        Descripción del Caso / Signos y Síntomas (Obligatorio)
                    </label>
                    <textarea id="description" name="description" rows="5" required class="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-green-500 focus:ring-green-500 border p-3" placeholder="Describa los signos, síntomas, historial y hallazgos relevantes para que Gemini los analice."></textarea>
                </div>

                <!-- Campo de Archivo Opcional -->
                <div class="mb-4">
                    <label for="file" class="block text-sm font-medium text-gray-700">Archivo Adjunto (Opcional)</label>
                    <input type="file" id="file" name="file" class="mt-1 block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-sm file:font-semibold file:bg-green-50 file:text-green-700 hover:file:bg-green-100">
                </div>

                <!-- Consentimiento Legal -->
                <div class="mb-6">
                    <div class="flex items-center">
                        <input id="has_legal_consent" name="has_legal_consent" type="checkbox" required class="h-4 w-4 text-green-600 border-gray-300 rounded focus:ring-green-500">
                        <label for="has_legal_consent" class="ml-2 block text-sm text-gray-900">
                            Acepto el consentimiento legal para el análisis del caso.
                        </label>
                    </div>
                </div>

                <!-- Campo de Bypass (Solo para desarrollo) -->
                <div class="mb-6 p-4 border rounded-lg bg-gray-50">
                    <label for="volunteer-bypass" class="block text-sm font-medium text-gray-700">Clave de Bypass (ADMIN_BYPASS_KEY)</label>
                    <input type="password" id="volunteer-bypass" name="developer_bypass_key" placeholder="Introduzca su clave secreta de Administrador" class="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-green-500 focus:ring-green-500 border p-2">
                </div>

                <button type="submit" class="w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-base font-medium text-white bg-green-600 hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-green-500 transition duration-150 ease-in-out">
                    Enviar Caso (Pagar $50 o Usar Bypass)
                </button>
            </form>

            <div id="results-volunteer">
                <!-- Los resultados de la API aparecerán aquí -->
            </div>
        </div>

        <!-- PESTAÑA PROFESIONAL (Servicio de $100) -->
        <div id="professional-content" class="tab-content hidden">
            <h2 class="text-2xl font-semibold text-gray-700 mb-4">Activación de Herramienta (Profesional) - Precio: $100 USD</h2>
            <form id="professional-form" onsubmit="submitForm(event, '/professional/activate-tool', 'professional')">
                <input type="hidden" name="user_id" value="2">
                
                <div class="mb-4">
                    <label for="tool_name" class="block text-sm font-medium text-gray-700">Nombre de la Herramienta a Activar</label>
                    <input type="text" id="tool_name" name="tool_name" value="DiagnósticoAvanzado" required class="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-green-500 focus:ring-green-500 border p-2">
                </div>

                <!-- Campo de Bypass (Solo para desarrollo) -->
                <div class="mb-6 p-4 border rounded-lg bg-gray-50">
                    <label for="professional-bypass" class="block text-sm font-medium text-gray-700">Clave de Bypass (ADMIN_BYPASS_KEY)</label>
                    <input type="password" id="professional-bypass" name="developer_bypass_key" placeholder="Introduzca su clave secreta de Administrador" class="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-green-500 focus:ring-green-500 border p-2">
                </div>

                <button type="submit" class="w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-base font-medium text-white bg-green-600 hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-green-500 transition duration-150 ease-in-out">
                    Activar Herramienta (Pagar $100 o Usar Bypass)
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
# RUTA: /volunteer/create-case
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
# RUTA: /professional/activate-tool
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
# RUTA: /stripe/webhook
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
        raise HTTPException(status_code=400, detail="Webhook secret not configured.")

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
            # En un entorno real, aquí se procesaría el caso completo, no solo el fragmento de metadata.
            gemini_response = await call_gemini_api(description)
            print(f"Análisis Gemini finalizado para el caso de voluntario: {gemini_response['analysis_status']}")
            # Aquí iría el código para guardar/enviar el resultado al usuario.
            
        elif service_type == "professional_tool_activation":
            # Caso Profesional: Activar Herramienta
            tool_name = session['metadata'].get('tool_name', 'Herramienta desconocida')
            print(f"Activando la herramienta '{tool_name}' para el usuario {user_id}.")
            # Aquí iría el código para actualizar la base de datos del usuario, generar un token, etc.
            
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
    <body class="p-8 bg-green-50 text-center">
        <h1 class="text-4xl text-green-700 font-bold mb-4">¡Pago Exitoso!</h1>
        <p class="text-lg text-gray-600">Su solicitud ha sido recibida. El ID de su sesión es: <code class="font-mono">{session_id}</code>.</p>
        <p class="mt-4 text-gray-700">El servicio (análisis o activación) se está procesando a través del Webhook de Stripe.</p>
        <a href="{RENDER_APP_URL}" class="mt-6 inline-block py-2 px-4 bg-green-600 text-white rounded-lg hover:bg-green-700">Volver al Inicio</a>
    </body>
    """

@app.get("/stripe/cancel", response_class=HTMLResponse)
def stripe_cancel():
    """Página de cancelación de Stripe Checkout."""
    return f"""
    <body class="p-8 bg-red-50 text-center">
        <h1 class="text-4xl text-red-700 font-bold mb-4">Pago Cancelado</h1>
        <p class="text-lg text-gray-600">Su pago fue cancelado. No se le ha cobrado.</p>
        <a href="{RENDER_APP_URL}" class="mt-6 inline-block py-2 px-4 bg-red-600 text-white rounded-lg hover:bg-red-700">Volver al Inicio</a>
    </body>
    """

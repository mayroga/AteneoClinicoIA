from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from typing import Optional

# Inicialización de la aplicación FastAPI
app = FastAPI(title="Ateneo Clínico IA Backend API")

# =========================================================================
# 1. CONFIGURACIÓN CRÍTICA DE CORS
# =========================================================================

origins = [
    "*",  # Permite todos los orígenes para facilitar las pruebas
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================================================================
# FUNCIÓN CRÍTICA: Servir el HTML en la ruta raíz (/)
# Esto soluciona el problema de acceso: la URL principal ahora muestra la interfaz.
# =========================================================================

HTML_CONTENT = """
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
        // URL FINAL DE LA API EN RENDER, CONFIRMADA POR EL USUARIO.
        const RENDER_APP_URL = "https://ateneoclinicoia.onrender.com"; 
        
        // ID de usuario de ejemplo para las pruebas
        const DEMO_USER_ID = 1; 

        /**
         * Maneja la respuesta del servidor (éxito, pago o error).
         * @param {Object} response - La respuesta JSON de la API.
         * @param {string} formId - El ID del formulario ('volunteer' o 'professional').
         */
        function handleResponse(response, formId) {
            const resultsDiv = document.getElementById('results-' + formId);
            resultsDiv.innerHTML = ''; // Limpiar resultados anteriores
            
            if (response.payment_url) {
                // Si la API devuelve una URL de pago (Stripe)
                resultsDiv.innerHTML = `
                    <div class="bg-yellow-100 border border-yellow-400 text-yellow-700 p-4 rounded-md mt-4">
                        <p class="font-bold">Pago Requerido:</p>
                        <p>Redirigiendo a la simulación de pago en 3 segundos...</p>
                        <a href="${response.payment_url}" target="_blank" class="text-blue-600 underline hover:text-blue-800">
                            (Si la redirección falla, haga clic aquí para pagar)
                        </a>
                    </div>
                `;
                // Redirigir automáticamente
                setTimeout(() => {
                    window.location.href = response.payment_url;
                }, 3000);
            } else {
                // Si la API devuelve un mensaje (Bypass o Éxito directo, si no se requiere pago)
                resultsDiv.innerHTML = `
                    <div class="bg-green-100 border border-green-400 text-green-700 p-4 rounded-md mt-4">
                        <p class="font-bold">Respuesta del Servidor (Éxito/Bypass):</p>
                        <pre class="whitespace-pre-wrap">${JSON.stringify(response, null, 2)}</pre>
                    </div>
                `;
            }
        }

        /**
         * Función principal de envío de formularios, maneja la conexión con la API.
         * @param {Event} event - El evento de envío del formulario.
         * @param {string} endpoint - La ruta de la API (ej: '/volunteer/create-case').
         * @param {string} formId - El ID del formulario ('volunteer' o 'professional').
         */
        async function submitForm(event, endpoint, formId) {
            event.preventDefault();
            const form = event.target;
            const resultsDiv = document.getElementById('results-' + formId);
            resultsDiv.innerHTML = '<div class="mt-4 p-4 text-center text-blue-500 font-semibold">Procesando... Verificando API...</div>';

            try {
                const formData = new FormData(form);
                
                // Asegurar que el user_id esté en el FormData
                if (!formData.has('user_id')) {
                    formData.append('user_id', DEMO_USER_ID);
                }

                // Construir la URL completa
                const fullUrl = `${RENDER_APP_URL}${endpoint}`;
                console.log(`Intentando conectar con: ${fullUrl}`); 
                
                const response = await fetch(fullUrl, {
                    method: 'POST',
                    body: formData // FormData se usa automáticamente con 'multipart/form-data'
                });

                const data = await response.json();
                
                if (!response.ok) {
                    throw new Error(data.detail || `Error ${response.status}: Error de conexión o validación.`);
                }

                handleResponse(data, formId);

            } catch (error) {
                // Manejo de errores de conexión (ej: Failed to fetch si la API está caída)
                resultsDiv.innerHTML = `
                    <div class="bg-red-100 border border-red-400 text-red-700 p-4 rounded-md mt-4">
                        <p class="font-bold">Error de Conexión (Failed to fetch):</p>
                        <p>No se pudo conectar con la API en <code>${RENDER_APP_URL}</code>.</p>
                        <p class="mt-2 text-sm">
                            1. **Verifique la URL:** Asegúrese de que la URL de su API en Render es accesible.
                            2. **Verifique el Estado:** Confirme que su servidor de Render está activo.
                            3. **CORS:** Confirme que su <code>main.py</code> tiene la configuración de CORS adecuada.
                        </p>
                        <p class="mt-2 text-xs text-gray-700">Detalles: ${error.message}</p>
                    </div>
                `;
                console.error("Error en la solicitud:", error);
            }
        }

        /**
         * Lógica para cambiar de pestaña en la interfaz.
         * @param {string} tabName - El nombre de la pestaña a mostrar ('volunteer' o 'professional').
         */
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

        // Inicializar al cargar la página
        window.onload = () => {
            switchTab('volunteer'); // Muestra la pestaña de voluntario por defecto
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
            Esta es una interfaz de prueba para los dos servicios de pago: 
            <span class="font-semibold text-green-700">Voluntario ($50)</span> y 
            <span class="font-semibold text-green-700">Profesional ($100)</span>.
        </p>
        
        <!-- Controles de Pestañas -->
        <div class="mb-6 flex space-x-4 border-b border-gray-200">
            <button id="volunteer-button" onclick="switchTab('volunteer')" class="tab-button px-4 py-2 text-sm font-medium rounded-t-lg transition duration-150 ease-in-out">
                Voluntario (Análisis de Caso)
            </button>
            <button id="professional-button" onclick="switchTab('professional')" class="tab-button px-4 py-2 text-sm font-medium rounded-t-lg transition duration-150 ease-in-out">
                Profesional (Activación de Herramienta)
            </button>
        </div>

        <!-- PESTAÑA VOLUNTARIO (Servicio de $50) -->
        <div id="volunteer-content" class="tab-content">
            <h2 class="text-2xl font-semibold text-gray-700 mb-4">Envío de Caso (Voluntario) - Precio: $50 USD</h2>
            <form id="volunteer-form" onsubmit="submitForm(event, '/volunteer/create-case', 'volunteer')">
                <input type="hidden" name="user_id" value="1"> 
                <p class="mb-4 text-sm text-gray-500">
                    ID de Usuario (demo): <span class="font-mono bg-gray-100 p-1 rounded">1</span>
                </p>

                <!-- Campo de Texto Obligatorio para Signos y Síntomas -->
                <div class="mb-4">
                    <label for="description" class="block text-sm font-medium text-gray-700">
                        Descripción del Caso / Signos y Síntomas (Obligatorio)
                    </label>
                    <textarea id="description" name="description" rows="5" required class="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-green-500 focus:ring-green-500 border p-3" placeholder="Describa los signos, síntomas, historial y hallazgos relevantes. Solo con el texto es suficiente para enviar y procesar el caso."></textarea>
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
                    <label for="volunteer-bypass" class="block text-sm font-medium text-gray-700">Clave de Bypass (Opcional - Desarrollador)</label>
                    <input type="password" id="volunteer-bypass" name="developer_bypass_key" placeholder="Clave secreta" class="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-green-500 focus:ring-green-500 border p-2">
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
                <p class="mb-4 text-sm text-gray-500">
                    ID de Usuario (demo): <span class="font-mono bg-gray-100 p-1 rounded">2</span> (Asumido como rol 'professional')
                </p>
                
                <div class="mb-4">
                    <label for="tool_name" class="block text-sm font-medium text-gray-700">Nombre de la Herramienta a Activar</label>
                    <input type="text" id="tool_name" name="tool_name" value="DiagnósticoAvanzado" required class="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-green-500 focus:ring-green-500 border p-2">
                </div>

                <!-- Campo de Bypass (Solo para desarrollo) -->
                <div class="mb-6 p-4 border rounded-lg bg-gray-50">
                    <label for="professional-bypass" class="block text-sm font-medium text-gray-700">Clave de Bypass (Opcional - Desarrollador)</label>
                    <input type="password" id="professional-bypass" name="developer_bypass_key" placeholder="Clave secreta" class="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-green-500 focus:ring-green-500 border p-2">
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
    """Ruta principal que sirve la interfaz de usuario (HTML)."""
    # Ahora devuelve la página HTML en lugar del JSON.
    return HTML_CONTENT

# =========================================================================
# 2. ENDPOINT PARA VOLUNTARIOS (Análisis de Caso) - Precio: $50 USD
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
    Simula el proceso de creación de un caso por parte de un voluntario.
    Requiere un pago o una clave de bypass.
    """
    
    # 1. Lógica de Bypass (Para desarrolladores)
    if developer_bypass_key == "DEBUG_VOLUNTEER":
        file_name = file.filename if file else "No se adjuntó archivo"
        
        # En un entorno real, aquí se procesaría el caso con la IA
        return {
            "status": "success",
            "message": "Bypass de pago activado. Caso de voluntario procesado.",
            "data": {
                "user_id": user_id,
                "description_length": len(description),
                "file_uploaded": file_name,
                "consent_given": has_legal_consent
            }
        }

    # 2. Lógica de Pago (Simulación de Stripe)
    
    # Nota CRÍTICA: La URL devuelta al frontend DEBE contener 'payment_url'
    # para que la lógica de redirección del HTML se active.
    
    return {
        "status": "payment_required",
        "payment_url": "https://simulacion.stripe.com/checkout/volunteer_50usd",
        "price": 50,
        "currency": "USD"
    }

# =========================================================================
# 3. ENDPOINT PARA PROFESIONALES (Activación de Herramienta) - Precio: $100 USD
# RUTA: /professional/activate-tool
# =========================================================================

@app.post("/professional/activate-tool")
async def activate_professional_tool(
    user_id: int = Form(...),
    tool_name: str = Form(...),
    developer_bypass_key: Optional[str] = Form(None)
):
    """
    Simula la activación de una herramienta avanzada por parte de un profesional.
    Requiere un pago o una clave de bypass.
    """
    
    # 1. Lógica de Bypass (Para desarrolladores)
    if developer_bypass_key == "DEBUG_PROFESSIONAL":
        
        # En un entorno real, aquí se desbloquearía el acceso a la herramienta
        return {
            "status": "success",
            "message": f"Bypass de pago activado. Herramienta '{tool_name}' desbloqueada.",
            "access_token": "TOKEN_DE_ACCESO_PROFESIONAL_GENERADO"
        }

    # 2. Lógica de Pago (Simulación de Stripe)
    
    # Nota CRÍTICA: La URL devuelta al frontend DEBE contener 'payment_url'
    # para que la lógica de redirección del HTML se active.
    
    return {
        "status": "payment_required",
        "payment_url": "https://simulacion.stripe.com/checkout/professional_100usd",
        "price": 100,
        "currency": "USD"
    }

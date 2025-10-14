// --- CONFIGURACIÓN Y VARIABLES CLAVE ---
const APP_TITLE = "Ateneo Clínico IA";

// ✅ URL CORREGIDA Y CLAVES DE PRODUCCIÓN
// Asegúrate de que esta URL sea el dominio de tu backend de Render
const BASE_URL = 'https://ateneoclinicoia.onrender.com'; 
const RENDER_ADMIN_AUTH_ENDPOINT = `${BASE_URL}/api/admin-auth`; 
const RENDER_STRIPE_CHECKOUT_ENDPOINT = `${BASE_URL}/api/checkout`; // USAMOS /api/checkout
const RENDER_AI_ENDPOINT = `${BASE_URL}/api/analizar-caso`; 

// ✅ CLAVE PÚBLICA DE STRIPE (LIVE)
const STRIPE_PUBLISHABLE_KEY = 'pk_live_51NqPxQBOA5mT4t0PEoRVRc0Sj7DugiHvxhozC3BYh0q0hAx1N3HCLJe4xEp3MSuNMA6mQ7fAO4mvtppqLodrtqEn00pgJNQaxz'; 

const PROFESSIONAL_LEVELS = { 
    LEVEL_1: { id: 'LEVEL_1', name: 'Nivel 1 – Clínico Colaborador', description: 'Casos IA básicos, participa en debates moderados. Gana puntos de experiencia.', costMonthly: 160, costQuarterly: 420, caseLimit: 5, incentive: 'Panel de Expertos Activos', },
    LEVEL_2: { id: 'LEVEL_2', name: 'Nivel 2 – Clínico Experto', description: 'Casos moderadamente complejos. Sube tus propios casos para debate IA.', costMonthly: 220, costQuarterly: 600, caseLimit: 10, incentive: 'Acceso prioritario a resultados de aprendizaje de la IA.', },
    LEVEL_3: { id: 'LEVEL_3', name: 'Nivel 3 – Investigador Principal', description: 'Casos de alta complejidad/interdisciplinarios. Supervisión y publicaciones conjuntas con IA.', costMonthly: 300, costQuarterly: 840, caseLimit: 15, incentive: 'Posibilidad de aparecer como coautor en el IA Research Board.', },
};

// Estado Global (Manejado por Vanilla JS)
let state = {
    userId: 'anon_' + Math.random().toString(36).substring(2, 8),
    view: 'landing', 
    professionalSubView: 'dashboard',
    userProfile: null,
    volunteerStep: 1, 
    caseData: { description: '', file: null, aiResult: null, isProcessing: false, },
    currentCaseToReview: null,
    loading: true,
    error: null,
    adminLoginError: ''
};

// --- FUNCIONES CORE DE ESTADO Y UTILIDADES ---
const loadProfile = () => {
    const storedProfile = localStorage.getItem('userProfile');
    if (storedProfile) {
        state.userProfile = JSON.parse(storedProfile);
        state.view = state.userProfile.role || 'landing';
    } else {
        state.userProfile = { userId: state.userId, role: 'landing', score: 0 };
        saveProfile(state.userProfile);
    }
};

const saveProfile = (updates) => {
    state.userProfile = { ...state.userProfile, ...updates };
    localStorage.setItem('userProfile', JSON.stringify(state.userProfile));
};

// 💡 CORRECCIÓN: Al actualizar el estado, no se llama a renderApp() si solo se cambian datos del caso
// Esto evita la pérdida de foco en el textarea y el input de archivo.
const setAppState = (updates, callback) => {
    state = { ...state, ...updates };
    if (updates.userProfile) {
        saveProfile(updates.userProfile);
    }
    renderApp(); // Se mantiene el renderizado para cambios de vista, no de input.
    if (callback) callback();
};

const Button = (text, onClick, primary = true, className = '', disabled = false) => `
    <button
        onclick="${onClick}"
        ${disabled ? 'disabled' : ''}
        class="px-6 py-3 rounded-xl font-bold transition-all duration-300 shadow-md ${primary ? 'bg-blue-600 text-white hover:bg-blue-700 active:shadow-none' : 'bg-white text-gray-700 border border-gray-300 hover:bg-gray-100'} ${disabled ? 'opacity-50 cursor-not-allowed' : ''} ${className}"
    >
        ${text}
    </button>
`;

const getAssignedCases = () => {
    // Simulación de Casos Asignados (Mock Data)
    return [
        { id: 'case_001', difficulty: 'Alto', summary: 'Revisar paciente con posible síndrome de Marfan, los ecocardiogramas son inconcluyentes y se requiere una segunda opinión para validar la IA.', assignedTime: Date.now() - 3600000, aiResult: { diagnosis: "Probable Marfan, revisar gen FBN1", treatment: "Eco y resonancia." } },
        { id: 'case_002', difficulty: 'Medio', summary: 'Caso de pediatría con fiebre y exantema atípico que no responde al tratamiento estándar.', assignedTime: Date.now() - 7200000, aiResult: { diagnosis: "Diagnóstico Viral Atípico", treatment: "Tratamiento de soporte." } },
        { id: 'case_003', difficulty: 'Básico', summary: 'Revisión de caso simple de dolor de cabeza crónico en paciente joven.', assignedTime: Date.now() - 10800000, aiResult: { diagnosis: "Cefalea tensional", treatment: "Analgésicos simples." } },
    ];
};


// --- LÓGICA DE EVENTOS Y FETCH REAL ---

window.selectUserRole = (role) => {
    if (role === 'volunteer') {
        setAppState({ view: 'volunteer', userProfile: { ...state.userProfile, role: 'volunteer' }, volunteerStep: 1 });
    } else if (role === 'professional') {
        setAppState({ view: 'professional', userProfile: { ...state.userProfile, role: 'professional' }, professionalSubView: 'dashboard' });
    } else {
         setAppState({ view: 'landing', userProfile: { ...state.userProfile, role: 'landing' } });
    }
};

// 💡 CORRECCIÓN: Función de actualización de datos, no llama a renderApp()
window.updateCaseData = (key, value) => { state.caseData[key] = value; }; // NO renderApp()

window.handleFileChange = (inputElement) => {
    const file = inputElement.files[0];
    if (file) {
        const mockFile = { name: `anon_file_${Date.now()}_${file.name.substring(0, 10)}...`, type: file.type, size: file.size };
        setAppState({ caseData: { ...state.caseData, file: mockFile } });
    }
};


// --- ADMIN BYPASS (Conexión a RENDER /api/admin-auth) ---

window.goToAdminLogin = () => { setAppState({ view: 'adminLogin', adminLoginError: '' }); }

window.submitAdminKey = async () => {
    const adminKey = document.getElementById('admin-key').value;
    if (!adminKey) { setAppState({ adminLoginError: 'Por favor, introduce la clave de acceso.' }); return; }
    setAppState({ loading: true, adminLoginError: '' });

    try {
        const response = await fetch(RENDER_ADMIN_AUTH_ENDPOINT, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ admin_key: adminKey }), // Usamos 'admin_key' para el backend
        });
        const result = await response.json();
        
        if (response.ok && result.success) {
            setAppState({ 
                view: 'professional', 
                professionalSubView: 'dashboard',
                userProfile: { 
                    ...state.userProfile, 
                    role: 'professional',
                    subscriptionLevel: 'LEVEL_3', // Acceso completo
                    isAdmin: true,
                    score: result.score || 999 
                },
                loading: false
            });
        } else {
            setAppState({ adminLoginError: result.message || 'Clave de acceso incorrecta.', loading: false });
        }
    } catch (error) {
        console.error("Error de autenticación admin:", error);
        setAppState({ adminLoginError: 'Error de conexión con el servicio de autenticación.', loading: false });
    }
};


// --- INTEGRACIÓN STRIPE (Conexión a RENDER /api/checkout) ---

window.submitVolunteerCase = async () => {
    if (!state.caseData.description.trim() || !state.caseData.file) { alert("Por favor, describe tu situación y sube un archivo."); return; }
    setAppState({ caseData: { ...state.caseData, isProcessing: true } });

    try {
        // 1. Llamar al backend para crear la sesión de Checkout
        const response = await fetch(RENDER_STRIPE_CHECKOUT_ENDPOINT, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                case_id: state.userId + Date.now(),
                case_description: state.caseData.description
            }),
        });

        const session = await response.json();
        
        if (!response.ok || !session.checkout_url) { 
            throw new Error(session.detail || "Fallo en el servidor al crear la sesión de pago.");
        }
        
        // 2. Redirigir a la URL de Stripe proporcionada por el backend
        window.location.href = session.checkout_url;

    } catch (error) {
        console.error("Error de Stripe/Checkout:", error);
        alert(`Fallo en el pago: ${error.message}.`);
        setAppState({ caseData: { ...state.caseData, isProcessing: false } });
    }
};

window.resetVolunteerCase = () => {
     setAppState({ volunteerStep: 1, caseData: { description: '', file: null, aiResult: null, isProcessing: false } });
};


// --- INTEGRACIÓN GEMINI (Conexión a RENDER /api/analizar-caso) ---

// 💡 CORRECCIÓN: Función de llamada a la IA estandarizada
const callGeminiAPI = async (prompt, role) => {
    // Si es Admin (usando Bypass), damos una respuesta inmediata de prueba
    if (state.userProfile?.isAdmin) { return { diagnosis: "DIAGNÓSTICO ADMIN/TEST: Acceso Bypass OK.", treatment: "Sin costo." }; }

    try {
        const response = await fetch(RENDER_AI_ENDPOINT, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ prompt: prompt, role: role }),
        });

        if (!response.ok) { 
            const errorResult = await response.json();
            throw new Error(errorResult.detail || `Error ${response.status} en el servicio de IA.`); 
        }
        const result = await response.json();
        
        return {
            diagnosis: result.response_text.substring(0, 100) + '...', // Usar el texto devuelto por el backend
            treatment: "Orientación generada por la IA.",
            confidence: '95%',
            iaResponseTime: '< 1 minuto',
        };
    } catch (error) {
        console.error("Error al llamar al backend de IA:", error);
        setAppState({ error: 'Fallo en la comunicación con la IA. Inténtalo más tarde.' });
        return { diagnosis: 'Error de conexión.', treatment: 'No se pudo generar el análisis.' };
    }
};

window.handleSubscriptionSelect = (levelId) => {
    const level = PROFESSIONAL_LEVELS[levelId];
    alert(`Simulación: Iniciando proceso de pago para ${level.name}. Se usaría Stripe Checkout aquí.`);
    setAppState({
        userProfile: { ...state.userProfile, subscriptionLevel: level.id, score: state.userProfile.score || 0 },
        professionalSubView: 'dashboard'
    });
};

// 💡 NUEVA FUNCIÓN: Envía el caso del profesional para ser analizado por la IA
window.submitProfessionalCase = async () => {
    const caseDesc = document.getElementById('professional-case-description').value;

    if (!caseDesc.trim()) { alert("Por favor, ingresa una descripción para tu caso."); return; }
    
    setAppState({ caseData: { ...state.caseData, isProcessing: true } });

    const aiResult = await callGeminiAPI(caseDesc, state.userProfile?.subscriptionLevel || 'professional');

    if (aiResult.diagnosis !== 'Error de conexión.') {
        setAppState({ 
            caseData: { ...state.caseData, aiResult: aiResult, isProcessing: false },
            professionalSubView: 'ai_result' // Nueva vista para el resultado profesional
        });
    } else {
        setAppState({ caseData: { ...state.caseData, isProcessing: false } });
        alert(aiResult.diagnosis);
    }
};

window.setCurrentCase = (caseId) => {
    localStorage.removeItem('debateText'); 
    setAppState({ currentCaseToReview: caseId });
};

window.submitDebate = () => {
    const debateText = document.getElementById('debate-text').value || '';
    if (!debateText.trim()) return alert("Por favor, ingresa tu análisis o corrección.");

    alert("¡Gracias! Tu debate ha sido enviado. Ganaste 1 punto de experiencia.");

    setAppState({
        userProfile: { ...state.userProfile, score: (state.userProfile.score || 0) + 1 },
        currentCaseToReview: null
    });
};


// --- VISTAS HTML (Renderizado) ---

// (Mantener LandingView, AdminLoginView, VolunteerView, ProfessionalView, CaseReviewPanel como están, 
// excepto por la nueva lógica de 'upload_case' y la nueva vista 'ai_result' dentro de ProfessionalView)

const LandingView = () => `
    <div class="min-h-screen flex items-center justify-center bg-gray-50 p-4">
        <div class="w-full max-w-4xl p-8 bg-white rounded-3xl shadow-2xl">
            <header class="text-center mb-10">
                <h1 class="text-5xl font-extrabold text-blue-800 mb-2">${APP_TITLE}</h1>
                <p class="text-xl text-gray-600">Una plataforma de colaboración experimental.</p>
                <p class="text-sm text-gray-400 mt-2">ID: ${state.userId.substring(0, 10)}...</p>
            </header>
            <h2 class="text-3xl font-bold text-center text-gray-800 mb-8">Elige tu Rol de Participación</h2>
            <div class="grid md:grid-cols-2 gap-8">
                <div class="p-8 bg-green-50 border-4 border-green-200 rounded-2xl shadow-xl transition-transform transform hover:scale-[1.02]">
                    <h3 class="text-3xl font-black text-green-700 mb-4">Soy Voluntario</h3>
                    <p class="text-gray-700 mb-6">Recibe un diagnóstico, tratamiento y orientación generada por IA. **Costo: $50 USD por caso**.</p>
                    ${Button('Quiero Participar', "selectUserRole('volunteer')", true, 'w-full bg-green-600 hover:bg-green-700')}
                </div>
                <div class="p-8 bg-blue-50 border-4 border-blue-200 rounded-2xl shadow-xl transition-transform transform hover:scale-[1.02]">
                    <h3 class="text-3xl font-black text-blue-700 mb-4">Soy Profesional de Salud</h3>
                    <p class="text-gray-700 mb-6">Debate, corrige o valida diagnósticos de IA. Planes de Suscripción.</p>
                    ${Button('Ver Niveles', "selectUserRole('professional')", true, 'w-full')}
                </div>
            </div>
            <footer class="mt-12 text-center text-sm">
                ${Button('Acceso Desarrollador (Admin Bypass)', "goToAdminLogin()", false, 'text-xs text-gray-500 hover:text-blue-500 border-none shadow-none bg-transparent')}
            </footer>
        </div>
    </div>
`;

const AdminLoginView = () => `
    <div class="min-h-screen flex items-center justify-center bg-gray-50 p-4">
        <div class="w-full max-w-md p-8 bg-white rounded-3xl shadow-2xl">
            <h2 class="text-3xl font-bold text-red-700 mb-6 text-center">Acceso Directo (Developer)</h2>
            <p class="text-gray-600 mb-6 text-center">
                Introduce el valor de tu variable secreta **ADMIN_BYPASS_KEY** para saltar pagos y obtener acceso Nivel 3.
            </p>
            <div class="mb-4">
                <label class="block text-gray-700 font-semibold mb-2" for="admin-key">Clave Secreta de Render</label>
                <input
                    type="password"
                    id="admin-key"
                    class="w-full p-3 border border-gray-300 rounded-lg focus:ring-red-500 focus:border-red-500"
                    placeholder="Valor de ADMIN_BYPASS_KEY"
                />
            </div>
            ${state.adminLoginError ? `<p class="text-sm text-red-500 mb-4">${state.adminLoginError}</p>` : ''}
            
            ${Button(
                state.loading ? 'Verificando en Render...' : 'Acceder (Bypass Payment)',
                "submitAdminKey()",
                true,
                'w-full bg-red-600 hover:bg-red-700',
                state.loading
            )}

            ${Button('← Volver', "setAppState({ view: 'landing' })", false, 'mt-4 w-full')}
        </div>
    </div>
`;

const VolunteerView = () => {
    const { volunteerStep, caseData } = state;

    const Waiver = () => `
        <div class="bg-red-100 p-6 rounded-xl border-l-4 border-red-500 shadow-inner">
            <h3 class="text-xl font-bold text-red-700 mb-3">⚠️ Aviso Legal (Waiver Obligatorio)</h3>
            <p class="text-red-800 italic">“Esta plataforma es únicamente para fines **educativos, de simulación y debate clínico.**</p>
            ${Button('Aceptar y Continuar (Paso 2 de 3)', "setAppState({ volunteerStep: 2 })", true, 'mt-6 bg-red-600 hover:bg-red-700')}
        </div>
    `;

    const UploadCase = () => `
        <div class="bg-white p-8 rounded-xl shadow-2xl">
            <h3 class="text-2xl font-bold text-gray-800 mb-6">Paso 2: Describe tu Caso ($50 USD)</h3>
            <div class="mb-4">
                <label class="block text-gray-700 font-semibold mb-2" for="case-description">Descripción de la Situación Clínica</label>
                <textarea
                    id="case-description"
                    class="w-full p-3 border border-gray-300 rounded-lg focus:ring-blue-500 focus:border-blue-500"
                    rows="5"
                    placeholder="Describe tus síntomas, historial o el motivo de la consulta."
                    oninput="updateCaseData('description', this.value)"
                >${caseData.description}</textarea>
            </div>
            <div class="mb-6">
                <label class="block text-gray-700 font-semibold mb-2" for="case-file">Subir Archivos (Imágenes, Texto o Video)</label>
                <input
                    type="file"
                    id="case-file"
                    accept="image/*, .txt, .pdf, video/*"
                    onchange="handleFileChange(this)"
                    class="w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100"
                />
                ${caseData.file ? `<p class="mt-2 text-sm text-green-600">✅ Archivo simulado listo: ${caseData.file.name}</p>` : ''}
            </div>

            ${Button(
                caseData.isProcessing ? 'Redirigiendo a Stripe...' : 'Pagar y Obtener Análisis IA',
                "submitVolunteerCase()",
                true,
                'w-full',
                caseData.isProcessing || !caseData.description.trim() || !caseData.file
            )}
            <p class="mt-4 text-sm text-gray-500 text-center">**Pago real con Stripe:** Se cargaría $50 USD. El análisis se inicia tras el pago (vía Webhook).</p>
        </div>
    `;

    const AIResponse = () => `
        <div class="bg-blue-50 p-8 rounded-xl shadow-2xl border-l-4 border-blue-500">
            <h3 class="text-2xl font-bold text-blue-700 mb-4">Paso 3: Respuesta de la Inteligencia Artificial (Post-Pago)</h3>
            <div class="space-y-4">
                <p class="text-lg text-gray-700">La respuesta de la IA (obtenida del Webhook de Stripe en tu backend) aparecería aquí.
                **CRÍTICO:** Asegúrate de que el backend de Render maneje el Webhook y actualice este estado.</p>
                ${caseData.aiResult ? 
                    `<div class="p-4 bg-white rounded-lg shadow-sm">
                        <h4 class="font-bold text-lg text-gray-800">Diagnóstico IA</h4>
                        <p class="text-gray-700">${caseData.aiResult.diagnosis}</p>
                    </div>` : 
                    `<p class="text-orange-500 font-semibold">Esperando la respuesta del Webhook de Stripe para iniciar el análisis...</p>`
                }
            </div>
            ${Button('Iniciar Nuevo Caso', "resetVolunteerCase()", false, 'mt-8 w-full')}
        </div>
    `;

    let content;
    if (volunteerStep === 1) content = Waiver();
    else if (volunteerStep === 2) content = UploadCase();
    else if (volunteerStep === 3) content = AIResponse();

    return `
        <div class="min-h-screen bg-gray-50 p-4 sm:p-8">
            <div class="max-w-3xl mx-auto space-y-8">
                <header class="text-center">
                    <h1 class="text-4xl font-extrabold text-green-700 mb-2">Área de Voluntarios</h1>
                    ${Button('← Volver a Selección de Rol', "selectUserRole('landing')", false, 'mt-4 text-sm')}
                </header>
                ${content}
            </div>
        </div>
    `;
};


const ProfessionalView = () => {
    const { professionalSubView, userProfile } = state;
    const currentLevel = userProfile?.subscriptionLevel ? PROFESSIONAL_LEVELS[userProfile.subscriptionLevel] : null;

    // ... (ProfessionalLevelCard y CaseCard sin cambios)

    const SubscriptionsView = () => `
        <div class="bg-white p-8 rounded-xl shadow-2xl">
            <h3 class="text-2xl font-bold text-gray-800 mb-6">Selección de Nivel Profesional</h3>
            <div class="grid md:grid-cols-3 gap-6">
                ${Object.values(PROFESSIONAL_LEVELS).map(ProfessionalLevelCard).join('')}
            </div>
            ${Button('← Volver al Panel', "setAppState({ professionalSubView: 'dashboard' })", false, 'mt-6')}
        </div>
    `;

    // 💡 CORRECCIÓN: Implementación real de subida de caso profesional
    const UploadOwnCase = () => `
        <div class="bg-white p-8 rounded-xl shadow-2xl">
            <h3 class="text-2xl font-bold text-yellow-700 mb-6">Subir tu Propio Caso para Análisis IA</h3>
            ${currentLevel && currentLevel.id !== 'LEVEL_1' || userProfile?.isAdmin ? `
                <div class="mb-4">
                    <label class="block text-gray-700 font-semibold mb-2" for="professional-case-description">Descripción del Caso Clínico</label>
                    <textarea
                        id="professional-case-description"
                        class="w-full p-3 border border-gray-300 rounded-lg focus:ring-blue-500 focus:border-blue-500"
                        rows="5"
                        placeholder="Introduce la información clínica relevante para que la IA la analice."
                    ></textarea>
                </div>
                ${Button(state.caseData.isProcessing ? 'Analizando con IA...' : 'Enviar Caso a la IA para Análisis', "submitProfessionalCase()", true, 'w-full bg-yellow-600 hover:bg-yellow-700', state.caseData.isProcessing)}
            ` : `
                <p class="text-lg text-red-500 font-bold p-4 bg-red-50 rounded-lg">
                    ❌ **Acceso Restringido:** Esta función requiere el nivel **Clínico Experto (Nivel 2)** o superior.
                </p>
            `}
            ${Button('← Volver al Panel', "setAppState({ professionalSubView: 'dashboard' })", false, 'mt-6')}
        </div>
    `;

    // 💡 NUEVA VISTA: Muestra el resultado de la IA para el profesional
    const AIResultView = () => `
        <div class="bg-blue-50 p-8 rounded-xl shadow-2xl border-l-4 border-blue-500">
            <h3 class="text-2xl font-bold text-blue-700 mb-4">Resultado de Análisis IA (Uso Profesional)</h3>
            <p class="text-lg text-gray-700">El análisis del modelo Gemini ha concluido:</p>
            <div class="space-y-4 mt-4">
                <div class="p-4 bg-white rounded-lg shadow-sm">
                    <h4 class="font-bold text-lg text-gray-800">Diagnóstico y Recomendaciones IA</h4>
                    <pre class="whitespace-pre-wrap text-gray-700 mt-2">${state.caseData.aiResult.diagnosis}</pre>
                </div>
                <div class="p-4 bg-white rounded-lg shadow-sm">
                    <h4 class="font-bold text-lg text-gray-800">Tratamiento Sugerido</h4>
                    <p class="text-gray-700">${state.caseData.aiResult.treatment}</p>
                </div>
            </div>
            ${Button('Volver al Panel', "setAppState({ professionalSubView: 'dashboard', caseData: { ...state.caseData, aiResult: null } })", false, 'mt-8 w-full')}
        </div>
    `;

    const Dashboard = () => {
        // ... (Dashboard sin cambios)
    };
    
    let content;
    if (professionalSubView === 'dashboard') content = Dashboard();
    else if (professionalSubView === 'subscriptions') content = SubscriptionsView();
    else if (professionalSubView === 'upload_case') content = UploadOwnCase();
    else if (professionalSubView === 'ai_result') content = AIResultView(); // Nueva vista

    return `
        <div class="min-h-screen bg-gray-50 p-4 sm:p-8">
            <div class="max-w-5xl mx-auto space-y-8">
                <header class="flex justify-between items-center pb-4 border-b border-gray-200">
                    <h1 class="text-4xl font-extrabold text-blue-700">Área de Profesionales</h1>
                    ${Button('← Volver a Selección de Rol', "selectUserRole('landing')", false, 'text-sm')}
                </header>
                ${content}
            </div>
            ${state.currentCaseToReview ? CaseReviewPanel() : ''}
        </div>
    `;
};


// (Resto de funciones (CaseReviewPanel, renderApp, inicialización) sin cambios)

const ProfessionalLevelCard = (level) => {
    const isCurrent = state.userProfile?.subscriptionLevel === level.id;
    return `
        <div class="p-6 border-4 rounded-2xl transition-all duration-300 shadow-lg ${isCurrent ? 'border-blue-500 bg-blue-50' : 'border-gray-100 bg-white hover:shadow-xl'}">
            <h3 class="text-2xl font-extrabold mb-2 ${isCurrent ? 'text-blue-700' : 'text-gray-900'}">${level.name}</h3>
            <p class="text-gray-600 mb-4 h-12 line-clamp-2">${level.description}</p>
            <div class="text-4xl font-black text-green-600 mb-2">
                $${level.costMonthly}
                <span class="text-base font-medium text-gray-500">/mes</span>
            </div>
            ${Button(isCurrent ? 'Nivel Actual' : 'Seleccionar Plan', `handleSubscriptionSelect('${level.id}')`, !isCurrent, 'w-full', isCurrent)}
        </div>
    `;
};

const CaseCard = (caseData) => `
        <div class="p-5 border border-gray-200 rounded-xl bg-white shadow-sm hover:shadow-md transition-shadow">
            <h4 class="font-semibold text-lg text-gray-800">Caso #${caseData.id.slice(0, 8)}...</h4>
            <p class="text-sm text-gray-600 mt-2 line-clamp-2">**Motivo:** ${caseData.summary}</p>
            ${Button('Revisar y Debatir', `setCurrentCase('${caseData.id}')`, true, 'mt-4 text-sm px-4 py-2')}
        </div>
    `;

const Dashboard = () => `
        <div class="space-y-8">
            <div class="bg-white p-6 rounded-2xl shadow-xl border-l-4 border-blue-500">
                <h3 class="text-2xl font-bold text-blue-800 mb-2">Tu Nivel: ${state.userProfile?.subscriptionLevel ? PROFESSIONAL_LEVELS[state.userProfile.subscriptionLevel].name : 'No Suscrito'} ${state.userProfile?.isAdmin ? '(ADMIN)' : ''}</h3>
                <p class="text-sm text-gray-500 mt-2">Puntos de Impacto Médico (Correc. IA): **${state.userProfile?.score || 0}**</p>
                ${Button('Gestionar Suscripción', "setAppState({ professionalSubView: 'subscriptions' })", false, 'text-sm')}
            </div>

            <div class="grid md:grid-cols-2 gap-6">
                <div class="p-6 bg-yellow-50 rounded-2xl shadow-lg">
                    <h4 class="text-xl font-bold text-yellow-700 mb-3">Sube tu Caso Clínico</h4>
                    ${Button('Subir Caso Propio', "setAppState({ professionalSubView: 'upload_case' })", true, 'bg-yellow-600 hover:bg-yellow-700')}
                </div>
                <div class="p-6 bg-purple-50 rounded-2xl shadow-lg">
                    <h4 class="text-xl font-bold text-purple-700 mb-3">Ranking de Expertos</h4>
                    ${Button('Ver Ranking', "alert('Simulando vista de Ranking...')", false, 'border-purple-300 text-purple-700')}
                </div>
            </div>

            <h3 class="text-2xl font-bold text-gray-800 mt-8 mb-4">Casos IA Asignados para Debate (${getAssignedCases().length})</h3>
            <div class="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
                ${getAssignedCases().map(CaseCard).join('')}
            </div>
        </div>
    `;

const CaseReviewPanel = () => {
    const currentCase = getAssignedCases().find(c => c.id === state.currentCaseToReview);
    if (!currentCase) return '';

    const debateText = localStorage.getItem('debateTextForModal') || '';

    return `
        <div class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
            <div class="bg-white p-8 rounded-2xl w-full max-w-4xl max-h-[90vh] overflow-y-auto shadow-2xl">
                <h3 class="text-3xl font-bold text-blue-800 mb-4">Debate y Validación de Caso #${currentCase.id.slice(0, 8)}...</h3>

                <div class="border p-4 rounded-xl mb-6 bg-gray-50">
                    <h4 class="font-bold text-xl mb-2">Análisis de la IA</h4>
                    <p class="text-sm text-gray-600">**Diagnóstico IA:** ${currentCase.aiResult.diagnosis}</p>
                    <p class="text-sm text-gray-600">**Tratamiento IA:** ${currentCase.aiResult.treatment}</p>
                </div>

                <div class="mb-6">
                    <label class="block text-gray-700 font-semibold mb-2" for="debate-text">Tu Análisis, Corrección o Debate</label>
                    <textarea
                        id="debate-text"
                        class="w-full p-3 border border-gray-300 rounded-lg focus:ring-blue-500 focus:border-blue-500"
                        rows="8"
                        placeholder="Escribe tu validación o desafío al diagnóstico de la IA."
                        oninput="localStorage.setItem('debateTextForModal', this.value)"
                    >${debateText}</textarea>
                </div>

                <div class="flex justify-end space-x-4">
                    ${Button('Cancelar', "setAppState({ currentCaseToReview: null }); localStorage.removeItem('debateTextForModal');", false)}
                    ${Button('Enviar Debate y Ganar Puntos', "submitDebate()", true, '', !debateText.trim())}
                </div>
            </div>
        </div>
    `;
};


// --- FUNCIÓN DE RENDERIZADO PRINCIPAL ---
const renderApp = () => {
    const container = document.getElementById('app-container');
    let content = '';

    if (state.loading && state.view !== 'adminLogin') {
         content = `<div class="flex items-center justify-center min-h-screen bg-gray-50"><div class="text-xl font-semibold text-gray-700">Cargando Ateneo Clínico IA...</div></div>`;
    } else if (state.view === 'landing') {
        content = LandingView();
    } else if (state.view === 'adminLogin') {
        content = AdminLoginView();
    } else if (state.view === 'volunteer') {
        content = VolunteerView();
    } else if (state.view === 'professional') {
        content = ProfessionalView();
    } else {
         content = `<div class="flex items-center justify-center min-h-screen bg-red-50"><div class="p-6 bg-white rounded-xl shadow-lg text-red-700"><h2 class="text-2xl font-bold mb-3">Error de Vista</h2><p>El estado de la aplicación es inválido.</p></div></div>`;
    }

    container.innerHTML = content;
};

// --- INICIALIZACIÓN DE LA APLICACIÓN ---
document.addEventListener('DOMContentLoaded', () => {
    loadProfile();
    setTimeout(() => {
        setAppState({ loading: false });
    }, 500);
});

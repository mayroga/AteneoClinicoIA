from fastapi import FastAPI, Depends, HTTPException, Header, status, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from config import settings
from database import create_tables, get_db_connection
from models import WaiverAcceptance, CreatePaymentIntent, ProfessionalRegister, TesisClinica
from professional_service import register_professional, get_debate_case, add_credits
from volunteer_service import get_volunteer_report, process_volunteer_case
from stripe_service import create_payment_intent # Asumimos que esta función está lista
import shutil
import os
import psycopg2.extras

# ----------------------------------------------------
# 1. INICIALIZACIÓN DE FASTAPI Y CONFIGURACIÓN BASE
# ----------------------------------------------------

app = FastAPI(
    title="Ateneo Clínico IA - Backend",
    description="Motor de simulación y debate médico con IA.",
    version="1.0.0",
)

# Configuración de CORS: permite la comunicación con tu futuro frontend
origins = [settings.FRONTEND_URL, "http://localhost:3000"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup_event():
    """Ejecutado al iniciar: verifica y crea las tablas de la DB."""
    print("Iniciando aplicación. Verificando DB...")
    create_tables()

# ----------------------------------------------------
# 2. LÓGICA DE SEGURIDAD PARA EL DESARROLLADOR (BYPASS KEY) 🔑
# ----------------------------------------------------

async def get_admin_access(x_admin_key: str = Header(None)):
    """Verifica la clave maestra para acceso ilimitado."""
    if x_admin_key and x_admin_key == settings.ADMIN_BYPASS_KEY:
        return True
    
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Acceso Denegado. Clave de bypass de administrador no válida.",
    )

# ----------------------------------------------------
# 3. ENDPOINTS GENERALES Y LEGALES
# ----------------------------------------------------

@app.get("/")
def read_root():
    """Endpoint de salud."""
    return {"message": "Ateneo Clínico IA operativo."}

@app.post("/waiver/accept")
def accept_waiver(data: WaiverAcceptance):
    """Registra la aceptación legal del Waiver."""
    conn = get_db_connection()
    if conn is None: raise HTTPException(status_code=500, detail="Error de conexión con la base de datos.")
    
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO waivers (user_type, user_email) VALUES (%s, %s) ON CONFLICT (user_email) DO UPDATE SET acceptance_timestamp = CURRENT_TIMESTAMP;",
            (data.user_type, data.email)
        )
        conn.commit()
        return {"message": f"Waiver aceptado con éxito por {data.email}. Tipo: {data.user_type}"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=f"Error al registrar aceptación: {e}")
    finally:
        if conn: conn.close()


# ----------------------------------------------------
# 4. ENDPOINTS DE PAGO (STRIPE) 💳
# ----------------------------------------------------

@app.post("/api/v1/payment/create-intent")
def create_intent(data: CreatePaymentIntent):
    """Crea un Payment Intent para la compra de créditos o el caso de voluntario."""
    intent_data = create_payment_intent(data)
    if intent_data is None:
        raise HTTPException(status_code=500, detail="No se pudo iniciar el proceso de pago con Stripe.")
    return {"clientSecret": intent_data["client_secret"]}

@app.post("/api/v1/payment/webhook")
def stripe_webhook():
    """
    Endpoint crucial para Stripe. Aquí se verificaría el evento de pago exitoso (payment_intent.succeeded)
    y se llamaría a la lógica de add_credits para actualizar la DB.
    """
    # Lógica de verificación de firma y procesamiento del evento de Stripe.
    # Por seguridad, solo se devuelve 200 OK.
    print("DEBUG: Webhook de Stripe recibido. (Procesaríamos la compra de créditos aquí)")
    return {"status": "success"}

# ----------------------------------------------------
# 5. ENDPOINTS DEL VOLUNTARIO (INPUT Y REPORTE) 🔬
# ----------------------------------------------------

@app.post("/api/v1/volunteer/submit-case")
async def submit_volunteer_case(
    email: str = Header(..., description="Email del voluntario que ya pagó."),
    history_text: str = Header(..., description="Historia Clínica del paciente."),
    image_file: UploadFile = File(..., description="Imagen de apoyo para el Proxy Visual.")
):
    """
    Recibe los datos del voluntario, llama a Gemini Vision y crea el Caso Anónimo.
    """
    # Se debe verificar que el email ya haya pagado a través de una tabla de pagos/eventos de Stripe.
    # Aquí asumiremos que el frontend hizo esta verificación.
    
    temp_file_path = f"/tmp/upload_{email}_{image_file.filename}" # Usamos /tmp en Render
    try:
        # 1. Almacenamiento Temporal
        with open(temp_file_path, "wb") as buffer:
            shutil.copyfileobj(image_file.file, buffer)
        
        # 2. PROCESAR, GENERAR TESIS, Y ELIMINAR IMAGEN (Proxy Visual)
        case_data = process_volunteer_case(email=email, history_text=history_text, image_path=temp_file_path)
        
        if case_data is None:
            raise HTTPException(status_code=500, detail="Fallo en la generación de la Tesis Clínica por la IA.")

        return {"message": "Caso recibido y anonimizado. Su Reporte de Participación está listo.", "case_id": case_data.case_id}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error interno al procesar el caso: {e}")
    
    finally:
        # 3. DOBLE SEGURIDAD: Asegurarse de que el archivo temporal se borre
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)


@app.get("/api/v1/volunteer/report/{email}")
def get_report(email: str):
    """Permite al voluntario recuperar su Tesis Clínica (Reporte de Participación)."""
    report = get_volunteer_report(email)
    if report is None:
        raise HTTPException(status_code=404, detail="Reporte no encontrado. Verifique su email.")
        
    return {"report": report.model_dump(), "warning": "SOLO FINES EDUCATIVOS. CONSULTE A SU MÉDICO."}


# ----------------------------------------------------
# 6. ENDPOINTS DEL PROFESIONAL (REGISTRO Y DEBATE) 🏆
# ----------------------------------------------------

@app.post("/api/v1/professional/register")
def professional_register_endpoint(data: ProfessionalRegister):
    """Registra al profesional (asumiendo que ya aceptó el waiver)."""
    profile = register_professional(data.email, data.name, data.specialty)
    if not profile or 'error' in profile:
        raise HTTPException(status_code=400, detail=profile.get('error', "Error al registrar profesional o waiver pendiente."))
    return {"message": "Registro exitoso.", "profile": profile}


@app.post("/api/v1/professional/add-credits")
def add_credits_endpoint(email: str = Header(..., description="Email del profesional")):
    """Simula la adición de créditos después de una compra exitosa."""
    # En un caso real, esta lógica sería llamada por el webhook de Stripe.
    result = add_credits(email)
    if result and 'new_balance' in result:
        return {"message": "Créditos añadidos con éxito.", "new_balance": result['new_balance']}
    raise HTTPException(status_code=400, detail="Fallo al añadir créditos.")


@app.get("/api/v1/professional/get-case")
def get_debate_case_endpoint(email: str = Header(..., description="Email del profesional para verificar créditos")):
    """Permite al profesional gastar un crédito y obtener un Caso Anónimo."""
    case_result = get_debate_case(email) 
    
    if case_result is None or 'error' in case_result:
        raise HTTPException(status_code=402, detail=case_result.get('error', "Créditos insuficientes o no hay casos disponibles."))

    return {"case": case_result.model_dump(), "message": "¡Nuevo caso para debate cargado!"}


# ----------------------------------------------------
# 7. ENDPOINTS DE PRUEBA DE ADMINISTRADOR
# ----------------------------------------------------

@app.get("/admin/test-access", dependencies=[Depends(get_admin_access)])
def admin_test_access():
    """Endpoint de prueba accesible solo con la Clave Maestra."""
    return {"status": "OK", "access": "Maestro", "detail": "Acceso ilimitado concedido."}

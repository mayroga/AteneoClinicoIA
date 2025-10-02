from fastapi import FastAPI, Depends, HTTPException, Header, status, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import shutil
import os
import psycopg2.extras
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from uuid import uuid4 # Necesario para generar IDs

# Importaciones de Servicios y Modelos
from config import settings
from database import create_tables, get_db_connection
from models import WaiverAcceptance, CreatePaymentIntent, ProfessionalRegister, DebateResult
from professional_service import register_professional, get_debate_case, add_credits, register_debate_result
from volunteer_service import get_volunteer_report_and_viral_message, process_volunteer_case
from stripe_service import create_payment_intent 
from email_service import send_waiver_confirmation, send_urgency_alert # SERVICIO DE CORREO INTEGRADO

# ----------------------------------------------------
# 1. INICIALIZACIÓN DE FASTAPI Y CONFIGURACIÓN BASE
# ----------------------------------------------------

# REEMPLAZAR 'your-render-url.onrender.com' con tu URL de Render para la documentación (no es funcionalmente usado aquí)
API_BASE_URL = "http://localhost:8000" 

app = FastAPI(
    title="Ateneo Clínico IA - Backend API",
    description="Motor de simulación y debate médico con IA. Monetización 24/7.",
    version="1.0.0",
)

# Permitir CORS desde tu frontend (URL de Render o local)
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
# 2. SEGURIDAD, ENDPOINTS GENERALES Y LEGALES
# ----------------------------------------------------

async def get_admin_access(x_admin_key: str = Header(None)):
    """Verifica la clave maestra para acceso ilimitado (Desarrollador)."""
    if x_admin_key and x_admin_key == settings.ADMIN_BYPASS_KEY:
        return True
    
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Acceso Denegado. Clave de bypass de administrador no válida.",
    )

@app.get("/")
def read_root():
    """Endpoint de salud."""
    return {"message": "Ateneo Clínico IA operativo."}

@app.post("/waiver/accept")
def accept_waiver(data: WaiverAcceptance):
    """Registra la aceptación legal del Waiver y envía email de confirmación (Seguridad/Legalidad)."""
    conn = get_db_connection()
    if conn is None: raise HTTPException(status_code=500, detail="Error de conexión con la base de datos.")
    
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO waivers (user_type, email) VALUES (%s, %s) ON CONFLICT (email) DO UPDATE SET acceptance_timestamp = CURRENT_TIMESTAMP;",
            (data.user_type, data.email)
        )
        conn.commit()
        
        # ENVÍO DE CORREO DE CONFIRMACIÓN LEGAL
        send_waiver_confirmation(data.email, data.user_type) 
        
        return {"message": f"Waiver aceptado con éxito por {data.email}. Tipo: {data.user_type}"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=f"Error al registrar aceptación: {e}")
    finally:
        if conn: conn.close()

# ----------------------------------------------------
# 3. ENDPOINTS DE PAGO (STRIPE) 💳
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
    """Endpoint crucial para Stripe (Aquí se actualizarían los créditos)."""
    # Lógica de Stripe para verificar el evento y llamar a add_credits(email, amount)
    print("DEBUG: Webhook de Stripe recibido. (Se procesaría la compra de créditos aquí)")
    return {"status": "success"}

# ----------------------------------------------------
# 4. ENDPOINTS DEL VOLUNTARIO (INPUT Y REPORTE) 🔬
# ----------------------------------------------------

@app.post("/api/v1/volunteer/submit-case")
async def submit_volunteer_case(
    email: str = Header(..., description="Email del voluntario que ya pagó."),
    history_text: str = Header(..., description="Historia Clínica del paciente."),
    image_file: UploadFile = File(..., description="Imagen de apoyo para el Proxy Visual.")
):
    """Recibe los datos, llama a Gemini Vision y crea el Caso Anónimo (Monetización Voluntario)."""
    # Crea un directorio temporal si no existe
    temp_dir = "/tmp"
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir)
        
    temp_file_path = os.path.join(temp_dir, f"upload_{uuid4()}_{image_file.filename}")
    
    try:
        # Guardar temporalmente la imagen
        with open(temp_file_path, "wb") as buffer:
            shutil.copyfileobj(image_file.file, buffer)
        
        # Procesar con la IA
        case_data = process_volunteer_case(email=email, history_text=history_text, image_path=temp_file_path)
        
        if case_data is None:
            raise HTTPException(status_code=500, detail="Fallo en la generación de la Tesis Clínica por la IA.")

        return {"message": "Caso recibido, anonimizado y Tesis Clínica generada.", "case_id": case_data.case_id}

    except Exception as e:
        print(f"ERROR: {e}")
        raise HTTPException(status_code=500, detail=f"Error interno al procesar el caso: {e}")
    
    finally:
        # Limpiar el archivo temporal
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)

@app.get("/api/v1/volunteer/report/{email}")
def get_report(email: str):
    """Permite al voluntario recuperar su Tesis Clínica y el mensaje viral."""
    result = get_volunteer_report_and_viral_message(email) 
    if result is None:
        raise HTTPException(status_code=404, detail="Reporte no encontrado. Verifique su email o el caso no existe.")
        
    return {
        "report": result['report'], 
        "warning": "SOLO FINES EDUCATIVOS. CONSULTE A SU MÉDICO.",
        "social_message": result['viral_message'] # Mensaje Viral listo para copiar
    }

# ----------------------------------------------------
# 5. ENDPOINTS DEL PROFESIONAL (REGISTRO Y DEBATE) 🏆
# ----------------------------------------------------

@app.post("/api/v1/professional/register")
def professional_register_endpoint(data: ProfessionalRegister):
    """Registra al profesional (asumiendo que ya aceptó el waiver)."""
    profile = register_professional(data.email, data.name, data.specialty)
    if not profile or 'error' in profile:
        raise HTTPException(status_code=400, detail=profile.get('error', "Error al registrar profesional o waiver pendiente."))
    return {"message": "Registro exitoso.", "profile": profile}

@app.get("/api/v1/professional/get-case")
def get_debate_case_endpoint(email: str = Header(..., description="Email del profesional para verificar créditos")):
    """Permite al profesional gastar un crédito y obtener un Caso Anónimo (Monetización)."""
    case_result = get_debate_case(email) 
    
    if case_result is None or 'error' in case_result:
        raise HTTPException(status_code=402, detail=case_result.get('error', "Créditos insuficientes o no hay casos disponibles."))

    return {"case": case_result, "message": "¡Nuevo caso para debate cargado!"}


@app.post("/api/v1/professional/submit-debate")
def submit_debate_result(
    data: DebateResult, 
    email: str = Header(..., description="Email del profesional")
):
    """Recibe el resultado final del debate (antes de las 72h) y actualiza el ranking (Gamificación)."""
    
    result = register_debate_result(email, data.case_id, data.professional_diagnosis, data.outcome)
    
    if result is None:
        raise HTTPException(status_code=500, detail="Fallo al registrar el resultado del debate.")
    
    return {
        "message": "Resultado registrado. ¡Su puntuación ha sido actualizada!", 
        "new_score": result['new_score'],
        "viral_message": result['viral_message'] # El gancho para las redes sociales
    }

# ----------------------------------------------------
# 6. TAREA PROGRAMADA (CRON JOB) - ¡MONETIZACIÓN 24/7!
# ----------------------------------------------------

@app.get("/system/cron/urgency-alert", dependencies=[Depends(get_admin_access)])
def cron_urgency_alert():
    """
    ENDPOINT LLAMADO POR RENDER CRON: Busca debates activos que caducan pronto y envía la alerta de urgencia.
    Requiere la X-Admin-Key para ejecutarse de forma segura.
    """
    conn = get_db_connection()
    if conn is None: return {"status": "error", "message": "DB connection failed for cron job"}

    try:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        # 1. Definir el umbral de urgencia (ej: debates que empezaron hace > 48 horas pero < 72)
        cursor.execute(
            """
            SELECT professional_email, case_id, start_time
            FROM active_debates
            WHERE is_completed = FALSE
            AND start_time <= NOW() - INTERVAL '48 hours'
            AND start_time > NOW() - INTERVAL '72 hours';
            """
        )
        urgent_debates = cursor.fetchall()
        
        emails_sent = 0
        for debate in urgent_debates:
            # Cálculo de horas restantes
            start_time: datetime = debate['start_time'].replace(tzinfo=None) 
            time_passed = datetime.now() - start_time
            hours_passed = time_passed.total_seconds() / 3600
            hours_remaining = 72 - int(hours_passed)

            # ENVÍO DE ALERTA QUE GENERA VENTA!
            if send_urgency_alert(debate['professional_email'], debate['case_id'], max(1, hours_remaining)):
                emails_sent += 1
        
        return {"status": "success", "message": f"Cron Job ejecutado. {len(urgent_debates)} debates urgentes detectados. {emails_sent} alertas de urgencia enviadas. ¡Monetización 24/7 en acción!"}

    except Exception as e:
        print(f"Error en el Cron Job de urgencia: {e}")
        return {"status": "error", "message": f"Error: {e}"}
    finally:
        if conn: conn.close()

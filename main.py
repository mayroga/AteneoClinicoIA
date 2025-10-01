from fastapi import FastAPI, Depends, HTTPException, Header, status, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from config import settings
from database import create_tables
from models import WaiverAcceptance, TesisClinica
from professional_service import register_professional, add_credits_and_get_case
from volunteer_service import get_volunteer_report, process_volunteer_case
from stripe_service import CreatePaymentIntent, create_payment_intent # Asumimos que create_payment_intent está implementado
import shutil
import os # Necesario para manejar archivos subidos temporalmente

# ----------------------------------------------------
# 1. INICIALIZACIÓN DE FASTAPI Y BASE DE DATOS
# ----------------------------------------------------

app = FastAPI(
    title="Ateneo Clínico IA - Backend",
    description="Motor de simulación y debate médico con IA.",
    version="1.0.0",
)

# Configuración de CORS
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
# 2. LÓGICA DE SEGURIDAD PARA EL DESARROLLADOR (BYPASS KEY)
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
    return {"message": "Ateneo Clínico IA operativo."}

@app.post("/waiver/accept")
def accept_waiver(data: WaiverAcceptance):
    # Lógica ya implementada en main.py anterior (simplicidad: solo llama al servicio)
    # Aquí puedes llamar a una función de database.py para guardar la aceptación.
    return {"message": f"Waiver aceptado con éxito por {data.email}"}

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
    Asume que el pago fue verificado por un webhook de Stripe ANTES de esta llamada.
    """
    # 1. ALMACENAMIENTO TEMPORAL DE LA IMAGEN (EL ÚNICO USO)
    # Se recomienda usar un servicio cloud (S3) para uploads, pero para el MVP:
    temp_file_path = f"temp_upload_{image_file.filename}"
    try:
        with open(temp_file_path, "wb") as buffer:
            shutil.copyfileobj(image_file.file, buffer)
        
        # 2. PROCESAR EL CASO Y GENERAR TESIS (PROXY VISUAL)
        # Esto incluye la ELIMINACIÓN INMEDIATA de temp_file_path dentro del servicio.
        case_data = process_volunteer_case(
            email=email, 
            history_text=history_text, 
            image_path=temp_file_path # Se pasa la ruta temporal
        )
        
        if case_data is None:
            raise HTTPException(status_code=500, detail="Fallo en la generación de la Tesis Clínica por la IA.")

        return {"message": "Caso recibido y anonimizado. Su Reporte de Participación está listo.", "case_id": case_data.case_id}

    except Exception as e:
        print(f"Error en submit_volunteer_case: {e}")
        raise HTTPException(status_code=500, detail=f"Error interno al procesar el caso. {e}")
    
    finally:
        # Asegurarse de limpiar si no se eliminó dentro del servicio (doble seguridad)
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

class ProfessionalRegister(WaiverAcceptance):
    name: str
    specialty: str

@app.post("/api/v1/professional/register")
def professional_register(data: ProfessionalRegister):
    """Registra al profesional (asumiendo que ya aceptó el waiver)."""
    profile = register_professional(data.email, data.name, data.specialty)
    if not profile or 'error' in profile:
        raise HTTPException(status_code=400, detail=profile.get('error', "Error al registrar profesional o waiver pendiente."))
    return {"message": "Registro exitoso.", "profile": profile}


@app.post("/api/v1/professional/get-case")
def get_debate_case(email: str = Header(..., description="Email del profesional para verificar créditos")):
    """
    Permite al profesional gastar un crédito y obtener un Caso Anónimo (la Tesis Clínica).
    Asume que el pago de créditos ya se realizó previamente.
    """
    # add_credits_and_get_case maneja la lógica de restar el crédito y obtener el caso.
    case_result = add_credits_and_get_case(email, is_payment_success=False) 
    
    if case_result is None or 'error' in case_result:
        raise HTTPException(status_code=402, detail=case_result.get('error', "Créditos insuficientes. Por favor, recargue su saldo."))

    return {"case": case_result.model_dump(), "message": "¡Nuevo caso para debate cargado! Tienes 72 horas para validarlo."}

# Nota: Los endpoints de sumisión de debate, ranking y gamificación se añadirían después.

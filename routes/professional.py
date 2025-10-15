from fastapi import APIRouter, Form, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from database import get_db
from models import User
from services.payment_service import create_payment_session
from config import ADMIN_BYPASS_KEY, BASE_URL
import datetime
import stripe

router = APIRouter(prefix="/professional", tags=["professional"])

# --- TAREA DE FONDO DE ACTIVACIÓN ---
def process_professional_tool_activation(user_id: int, tool_name: str, db: Session):
    # Aquí iría la lógica real para registrar el acceso profesional en la DB
    print(f"INFO TAREA: Activando herramienta '{tool_name}' para Profesional {user_id} en DB.")
    db.close()

# ------------------------------------------------------------------
# --- ENDPOINT 1: CREAR SESIÓN DE PAGO / BYPASS ---
# ------------------------------------------------------------------

@router.post("/activate-tool")
async def activate_tool(
    user_id: int = Form(...),
    tool_name: str = Form(...),
    developer_bypass_key: str = Form(None),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == user_id, User.role == "professional").first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado o no es profesional")
        
    tool_price = 100 
    
    # LÓGICA DE BYPASS DE DESARROLLADOR
    if developer_bypass_key and developer_bypass_key == ADMIN_BYPASS_KEY:
        db_session_for_task = get_db().__next__()
        process_professional_tool_activation(user_id, tool_name, db_session_for_task)
        return {"message": f"Herramienta {tool_name} activada por bypass. Lista para usar."}
        
    # FLUJO DE PAGO
    try:
        payment_session_data = create_payment_session(
            case_id=user_id, # Usamos user_id como identificador temporal en metadata
            price=tool_price,
            product_name=f"Herramienta: {tool_name}",
            success_url=f"{BASE_URL}/professional/tool-success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{BASE_URL}/professional/tool-cancel"
        )
        if "error" in payment_session_data: raise Exception(payment_session_data["error"])

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error en sesión de pago: {str(e)}")
    
    return {"message": "Redirigiendo a pago Stripe para herramienta.", "payment_url": payment_session_data["url"]}

# ------------------------------------------------------------------
# --- ENDPOINT 2: ACTIVACIÓN TRAS REDIRECCIÓN DE PAGO EXITOSO ---
# ------------------------------------------------------------------

@router.get("/tool-success")
async def tool_success(
    session_id: str,
    db: Session = Depends(get_db)
):
    try:
        session = stripe.checkout.Session.retrieve(session_id)
        
        if session.payment_status != "paid":
             return {"message": "Pago no completado. Estado: " + session.payment_status}
        
        user_id = session.metadata.get('case_id') 
        # Extraer tool_name del nombre del producto, asumiendo el formato
        tool_name = session.line_items.data[0].price.product.name.replace("Herramienta: ", "")
        
        # Activar el servicio en la DB
        db_session_for_task = get_db().__next__()
        process_professional_tool_activation(int(user_id), tool_name, db_session_for_task)

        return {"message": f"Pago verificado. Herramienta '{tool_name}' activada."}

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error al verificar pago y activar herramienta: {str(e)}")

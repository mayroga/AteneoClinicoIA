import psycopg2.extras
from database import get_db_connection
from models import WaiverAcceptance, TesisClinica
from typing import Optional, List

# --- Constantes ---
CREDITS_PER_PURCHASE = 5 # Créditos que compra en un paquete
INITIAL_PURCHASE_AMOUNT = 1500 # $15.00 USD en céntimos (ejemplo)

# ----------------------------------------------------
# 1. Registro y Verificación de Profesionales
# ----------------------------------------------------

def register_professional(email: str, name: str, specialty: str) -> Optional[dict]:
    """
    Registra un nuevo profesional en la DB. Asume que el Waiver ya fue aceptado.
    """
    conn = get_db_connection()
    if conn is None:
        return None

    try:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        # Primero, verifica si el Waiver fue aceptado.
        cursor.execute("SELECT user_email FROM waivers WHERE user_email = %s AND user_type = 'profesional'", (email,))
        if not cursor.fetchone():
            # Si no ha firmado el waiver, no puede registrarse
            return {"error": "Waiver no aceptado. Debe aceptar los términos legales primero."}

        # Inserta o actualiza el registro del profesional
        cursor.execute(
            """
            INSERT INTO profesionales (email, name, specialty)
            VALUES (%s, %s, %s)
            ON CONFLICT (email) DO UPDATE
            SET name = EXCLUDED.name, specialty = EXCLUDED.specialty
            RETURNING id, credits_balance, refutation_score;
            """,
            (email, name, specialty)
        )
        profile = cursor.fetchone()
        conn.commit()
        return dict(profile)

    except Exception as e:
        conn.rollback()
        print(f"Error al registrar profesional: {e}")
        return None

    finally:
        if conn: conn.close()

# ----------------------------------------------------
# 2. Gestión de Créditos y Casos
# ----------------------------------------------------

def add_credits_and_get_case(email: str, is_payment_success: bool = True) -> Optional[TesisClinica]:
    """
    Añade créditos al saldo (si el pago es exitoso) y retorna un Caso Anónimo.
    """
    conn = get_db_connection()
    if conn is None:
        return None

    try:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        # 1. Añadir Créditos
        if is_payment_success:
            cursor.execute(
                """
                UPDATE profesionales
                SET credits_balance = credits_balance + %s
                WHERE email = %s
                RETURNING credits_balance;
                """,
                (CREDITS_PER_PURCHASE, email)
            )
            if not cursor.fetchone():
                return {"error": "Profesional no encontrado después del pago."}
        
        # 2. Verificar saldo y restar un crédito para el caso
        cursor.execute(
            """
            UPDATE profesionales
            SET credits_balance = credits_balance - 1
            WHERE email = %s AND credits_balance >= 1
            RETURNING credits_balance;
            """,
            (email,)
        )
        
        if not cursor.fetchone():
            return {"error": "Créditos insuficientes. Por favor, compre más créditos para debatir."}

        # 3. Obtener un Caso Anónimo (La lógica de selección compleja iría aquí)
        # Por ahora, seleccionamos un caso no validado (is_validated = FALSE)
        cursor.execute(
            """
            SELECT tesis_clinica FROM casos_anonimos 
            WHERE is_validated = FALSE
            ORDER BY creation_date ASC 
            LIMIT 1;
            """
        )
        case = cursor.fetchone()

        if not case:
            return {"error": "No hay casos nuevos disponibles para debatir. Vuelve pronto."}

        return TesisClinica(**case['tesis_clinica'])

    except Exception as e:
        conn.rollback()
        print(f"Error en la transacción de créditos y caso: {e}")
        return None

    finally:
        if conn: conn.close()

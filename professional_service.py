import psycopg2.extras
from database import get_db_connection # Importación corregida
from models import TesisClinica # Importación corregida
from typing import Optional, List
import json

# --- Constantes de Monetización ---
CREDITS_PER_PURCHASE = 5 # Créditos que compra en un paquete de ejemplo
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
        
        # 1. Verifica si el Waiver fue aceptado (¡CRUCIAL!)
        cursor.execute("SELECT user_email FROM waivers WHERE user_email = %s AND user_type = 'profesional'", (email,))
        if not cursor.fetchone():
            return {"error": "Waiver no aceptado. Debe aceptar los términos legales primero."}

        # 2. Inserta o actualiza el registro del profesional
        cursor.execute(
            """
            INSERT INTO profesionales (email, name, specialty)
            VALUES (%s, %s, %s)
            ON CONFLICT (email) DO UPDATE
            SET name = EXCLUDED.name, specialty = EXCLUDED.specialty
            RETURNING id, credits_balance, refutation_score, specialty;
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
# 2. Gestión de Créditos y Obtención de Casos para Debate
# ----------------------------------------------------

def add_credits(email: str, amount: int = CREDITS_PER_PURCHASE) -> Optional[dict]:
    """Añade créditos al saldo de un profesional tras una compra exitosa."""
    conn = get_db_connection()
    if conn is None: return None
    
    try:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute(
            """
            UPDATE profesionales
            SET credits_balance = credits_balance + %s
            WHERE email = %s
            RETURNING credits_balance;
            """,
            (amount, email)
        )
        balance = cursor.fetchone()
        conn.commit()
        if balance:
            return {"new_balance": balance['credits_balance']}
        return {"error": "Profesional no encontrado para añadir créditos."}
    except Exception as e:
        conn.rollback()
        print(f"Error al añadir créditos: {e}")
        return None
    finally:
        if conn: conn.close()


def get_debate_case(email: str) -> Optional[TesisClinica]:
    """
    Resta un crédito al profesional y le proporciona un Caso Anónimo para debatir.
    """
    conn = get_db_connection()
    if conn is None: return None

    try:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        # 1. Verificar saldo y restar un crédito
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

        # 2. Obtener un Caso Anónimo (Prioridad: No validado o de alta complejidad)
        cursor.execute(
            """
            SELECT tesis_clinica FROM casos_anonimos 
            WHERE is_validated = FALSE
            ORDER BY creation_date ASC -- Prioriza los casos más nuevos (voluntarios recientes)
            LIMIT 1;
            """
        )
        case = cursor.fetchone()

        if not case:
            return {"error": "No hay casos nuevos disponibles. Vuelve pronto o intenta un caso ya debatido."}

        # 3. Retorna la Tesis Clínica
        return TesisClinica(**case['tesis_clinica'])

    except Exception as e:
        conn.rollback()
        print(f"Error en la transacción de créditos y caso: {e}")
        return None

    finally:
        if conn: conn.close()

from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import psycopg2.extras
from uuid import uuid4
from random import choice

from database import get_db_connection
from models import ProfessionalRegister

# ----------------------------------------------------
# LÓGICA DE REGISTRO
# ----------------------------------------------------

def register_professional(email: str, name: str, specialty: str) -> Optional[Dict[str, Any]]:
    """
    Registra al profesional y le otorga un crédito inicial de bienvenida.
    """
    conn = get_db_connection()
    if conn is None: return None
    
    try:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        # 1. Verificar si el waiver está aceptado
        cursor.execute("SELECT user_type FROM waivers WHERE email = %s;", (email,))
        if not cursor.fetchone():
            return {'error': 'Waiver no aceptado. El profesional debe aceptar los términos legales primero.'}
            
        # 2. Insertar o actualizar el profesional (Asigna 1 crédito de bienvenida)
        cursor.execute(
            """
            INSERT INTO professionals (email, name, specialty, credits, score_refutation)
            VALUES (%s, %s, %s, 1, 0)
            ON CONFLICT (email) DO UPDATE SET 
                name = EXCLUDED.name, 
                specialty = EXCLUDED.specialty;
            """,
            (email, name, specialty)
        )
        conn.commit()
        
        # 3. Retornar el perfil
        cursor.execute("SELECT email, name, specialty, credits, score_refutation FROM professionals WHERE email = %s;", (email,))
        profile = cursor.fetchone()
        return dict(profile)
        
    except Exception as e:
        conn.rollback()
        print(f"ERROR DB al registrar profesional: {e}")
        return None
    finally:
        if conn: conn.close()


def add_credits(email: str, amount: int) -> Optional[int]:
    """Añade créditos al profesional después de una compra exitosa."""
    conn = get_db_connection()
    if conn is None: return None
    
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE professionals SET credits = credits + %s WHERE email = %s RETURNING credits;",
            (amount, email)
        )
        new_credits = cursor.fetchone()
        conn.commit()
        return new_credits[0] if new_credits else None
        
    except Exception as e:
        conn.rollback()
        print(f"ERROR DB al añadir créditos: {e}")
        return None
    finally:
        if conn: conn.close()

# ----------------------------------------------------
# LÓGICA DE DEBATE Y MONETIZACIÓN (CRÉDITOS)
# ----------------------------------------------------

def get_debate_case(professional_email: str) -> Optional[Dict[str, Any]]:
    """
    Verifica créditos, descuenta 1, y asigna un caso disponible.
    """
    conn = get_db_connection()
    if conn is None: return None
    
    try:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        # 1. Bloquear y verificar créditos (Simulación de transacción)
        cursor.execute(
            "SELECT credits FROM professionals WHERE email = %s FOR UPDATE;", 
            (professional_email,)
        )
        prof_data = cursor.fetchone()
        
        if not prof_data or prof_data['credits'] <= 0:
            return {'error': 'Créditos insuficientes. Por favor, compra más para acceder a los casos.'}

        # 2. Descontar el crédito
        new_credits = prof_data['credits'] - 1
        cursor.execute(
            "UPDATE professionals SET credits = %s WHERE email = %s;", 
            (new_credits, professional_email)
        )
        
        # 3. Seleccionar un caso DISPONIBLE
        cursor.execute(
            """
            SELECT case_id, ai_report 
            FROM cases 
            WHERE is_available = TRUE 
            AND case_id NOT IN (SELECT case_id FROM active_debates WHERE professional_email = %s)
            ORDER BY creation_timestamp ASC LIMIT 1;
            """,
            (professional_email,)
        )
        case = cursor.fetchone()
        
        if not case:
            conn.rollback() # Revertir el descuento si no hay caso
            return {'error': 'No hay casos disponibles para debate en este momento.'}

        # 4. Iniciar un debate activo (Monetización 24/7 con caducidad)
        cursor.execute(
            "INSERT INTO active_debates (case_id, professional_email) VALUES (%s, %s);",
            (case['case_id'], professional_email)
        )
        
        conn.commit()
        print(f"DEBUG: Crédito descontado y debate iniciado para {professional_email} en caso {case['case_id']}.")
        
        # Extraer el reporte AI y el ID
        case_details = case['ai_report']
        case_details['case_id'] = case['case_id']
        return case_details
        
    except Exception as e:
        conn.rollback()
        print(f"ERROR DB en get_debate_case: {e}")
        return None
    finally:
        if conn: conn.close()


def register_debate_result(email: str, case_id: str, professional_diagnosis: str, outcome: str) -> Optional[Dict[str, Any]]:
    """
    Registra el resultado del debate, finaliza el debate activo y actualiza el Refutation Score.
    """
    conn = get_db_connection()
    if conn is None: return None
    
    try:
        cursor = conn.cursor()
        
        # 1. Finalizar el debate activo
        cursor.execute(
            """
            UPDATE active_debates 
            SET is_completed = TRUE 
            WHERE professional_email = %s AND case_id = %s AND is_completed = FALSE;
            """,
            (email, case_id)
        )

        # 2. Actualizar el Refutation Score (Gamificación)
        score_change = 0
        if outcome == "victory":
            score_change = 10
        elif outcome == "defeat":
            score_change = -5
        
        cursor.execute(
            "UPDATE professionals SET score_refutation = score_refutation + %s WHERE email = %s RETURNING score_refutation;",
            (score_change, email)
        )
        new_score = cursor.fetchone()[0]

        # 3. Generar mensaje viral para el profesional
        viral_message = f"¡Lo hice! Acabo de refutar el diagnóstico de la IA de Ateneo Clínico en el caso {case_id} y subí mi Refutation Score a {new_score}. ¿Quién más se atreve? #RefutationScore #AteneoIA"
        
        conn.commit()
        return {'new_score': new_score, 'viral_message': viral_message}

    except Exception as e:
        conn.rollback()
        print(f"ERROR DB al registrar resultado del debate: {e}")
        return None
    finally:
        if conn: conn.close()

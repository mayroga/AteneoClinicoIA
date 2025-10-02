import psycopg2
from psycopg2 import sql
from psycopg2.extras import Json
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

# CORRECCIÓN: Se importa desde 'config'
from config import settings 

# Configuración y conexión de la base de datos
try:
    conn = psycopg2.connect(settings.DATABASE_URL)
    conn.autocommit = True
    print("INFO: Conexión a PostgreSQL exitosa.")
except Exception as e:
    print(f"ERROR: No se pudo conectar a PostgreSQL usando DATABASE_URL. Error: {e}")
    conn = None

def get_db_connection():
    """Retorna la conexión de DB si está activa."""
    if conn and not conn.closed:
        return conn
    # Intenta reconectar si la conexión se perdió
    try:
        global conn
        conn = psycopg2.connect(settings.DATABASE_URL)
        conn.autocommit = True
        return conn
    except Exception as e:
        print(f"ERROR: Fallo en reconexión a DB. {e}")
        return None

def execute_query(query: sql.Composed, fetchone: bool = False, fetchall: bool = False):
    """Ejecuta una consulta SQL y maneja la conexión."""
    db_conn = get_db_connection()
    if not db_conn:
        return None

    try:
        with db_conn.cursor() as cur:
            cur.execute(query)
            if fetchone:
                return cur.fetchone()
            if fetchall:
                return cur.fetchall()
            return True
    except psycopg2.Error as e:
        print(f"ERROR al ejecutar query: {e}")
        return None
    except Exception as e:
        print(f"ERROR inesperado en DB: {e}")
        return None

# --- Creación de Tablas ---

def create_tables():
    """Crea las tablas de la DB si no existen."""
    queries = [
        # Tabla de Perfiles (Profesional/Voluntario)
        """
        CREATE TABLE IF NOT EXISTS profiles (
            email VARCHAR(255) PRIMARY KEY,
            user_type VARCHAR(20) NOT NULL CHECK (user_type IN ('professional', 'volunteer')),
            is_waiver_signed BOOLEAN NOT NULL DEFAULT FALSE,
            ranking_score INT DEFAULT 0,
            credits INT DEFAULT 0,
            created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """,
        # Tabla de Casos Clínicos (Subidos por Voluntarios)
        """
        CREATE TABLE IF NOT EXISTS cases (
            id SERIAL PRIMARY KEY,
            case_id VARCHAR(50) UNIQUE NOT NULL,
            volunteer_email VARCHAR(255) REFERENCES profiles(email),
            ai_report JSONB NOT NULL,
            is_available BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """,
        # Tabla de Debates Activos (Cuando un Profesional toma un caso)
        """
        CREATE TABLE IF NOT EXISTS active_debates (
            id SERIAL PRIMARY KEY,
            case_id VARCHAR(50) UNIQUE REFERENCES cases(case_id),
            professional_email VARCHAR(255) REFERENCES profiles(email),
            start_time TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            is_completed BOOLEAN NOT NULL DEFAULT FALSE
        );
        """
    ]
    
    for q in queries:
        execute_query(sql.SQL(q))
    
    print("INFO: Tablas de la base de datos verificadas/creadas.")

# --- Funciones de Perfiles ---

def get_profile_by_email(email: str) -> Optional[Dict[str, Any]]:
    """Obtiene un perfil por email."""
    query = sql.SQL("SELECT email, user_type, is_waiver_signed, ranking_score, credits FROM profiles WHERE email = %s;")
    result = execute_query(query, fetchone=True, params=[email])
    if result:
        # Mapear los resultados a un diccionario
        keys = ['email', 'user_type', 'is_waiver_signed', 'ranking_score', 'credits']
        return dict(zip(keys, result))
    return None

def create_profile(email: str, user_type: str) -> bool:
    """Crea un nuevo perfil (volunteer o professional)."""
    query = sql.SQL("INSERT INTO profiles (email, user_type) VALUES (%s, %s) ON CONFLICT (email) DO NOTHING;")
    return execute_query(query, params=[email, user_type])

def sign_waiver(email: str) -> bool:
    """Marca el waiver legal como firmado."""
    query = sql.SQL("UPDATE profiles SET is_waiver_signed = TRUE WHERE email = %s;")
    return execute_query(query, params=[email])

def get_professional_profile(email: str) -> Optional[Dict[str, Any]]:
    """Obtiene el perfil de un profesional con sus créditos."""
    query = sql.SQL("SELECT ranking_score, credits FROM profiles WHERE email = %s AND user_type = 'professional';")
    result = execute_query(query, fetchone=True, params=[email])
    if result:
        keys = ['ranking_score', 'credits']
        return dict(zip(keys, result))
    return None

def update_professional_credits(email: str, amount: int) -> Optional[int]:
    """Suma o resta créditos a un profesional. Retorna el nuevo total."""
    query = sql.SQL("UPDATE profiles SET credits = credits + %s WHERE email = %s AND user_type = 'professional' RETURNING credits;")
    result = execute_query(query, fetchone=True, params=[amount, email])
    if result:
        return result[0]
    return None

def update_refutation_score(email: str, score_increment: int) -> bool:
    """Actualiza el ranking (ranking_score) de un profesional."""
    query = sql.SQL("UPDATE profiles SET ranking_score = ranking_score + %s WHERE email = %s;")
    return execute_query(query, params=[score_increment, email])


# --- Funciones de Casos y Debates ---

def insert_case(case_id: str, volunteer_email: str, ai_report: Dict[str, Any]) -> bool:
    """Inserta un nuevo caso clínico con su reporte de IA."""
    query = sql.SQL("INSERT INTO cases (case_id, volunteer_email, ai_report) VALUES (%s, %s, %s);")
    return execute_query(query, params=[case_id, volunteer_email, Json(ai_report)])

def get_available_cases() -> Optional[List[Dict[str, Any]]]:
    """Obtiene todos los casos que están disponibles para debate."""
    query = sql.SQL("SELECT case_id, ai_report, created_at FROM cases WHERE is_available = TRUE;")
    results = execute_query(query, fetchall=True)
    if results:
        keys = ['case_id', 'ai_report', 'created_at']
        return [dict(zip(keys, row)) for row in results]
    return []

def start_active_debate(case_id: str, professional_email: str) -> Optional[int]:
    """
    Inicia un debate: marca el caso como no disponible e inserta el registro.
    Retorna el ID del nuevo debate o None si el caso no estaba disponible.
    """
    db_conn = get_db_connection()
    if not db_conn:
        return None

    try:
        with db_conn.cursor() as cur:
            # 1. Intentar marcar el caso como no disponible (transacción implícita)
            update_query = sql.SQL("UPDATE cases SET is_available = FALSE WHERE case_id = %s AND is_available = TRUE RETURNING id;")
            cur.execute(update_query, [case_id])
            
            if not cur.fetchone():
                db_conn.rollback()
                return None # El caso ya fue tomado o no existe
            
            # 2. Insertar el registro de debate
            insert_query = sql.SQL("INSERT INTO active_debates (case_id, professional_email) VALUES (%s, %s) RETURNING id;")
            cur.execute(insert_query, [case_id, professional_email])
            debate_id = cur.fetchone()[0]
            
            db_conn.commit()
            return debate_id
    except Exception as e:
        db_conn.rollback()
        print(f"ERROR al iniciar debate: {e}")
        return None

def complete_active_debate(debate_id: int) -> bool:
    """Marca un debate como completado."""
    query = sql.SQL("UPDATE active_debates SET is_completed = TRUE WHERE id = %s;")
    return execute_query(query, params=[debate_id])

# --- Funciones de Monitoreo y CRON Job ---

def get_expiring_debates(hours_threshold: int) -> List[Dict[str, Any]]:
    """
    Obtiene debates activos (no completados) que están próximos a caducar.
    Se usa para enviar alertas.
    """
    delta = timedelta(hours=hours_threshold)
    expiration_time = datetime.now() - delta
    
    query = sql.SQL("""
        SELECT ad.id, ad.professional_email, c.case_id, ad.start_time
        FROM active_debates ad
        JOIN cases c ON ad.case_id = c.case_id
        WHERE ad.is_completed = FALSE 
          AND ad.start_time < %s
          AND ad.start_time > %s; -- Solo debates que caducarán en la próxima hora (ej: 22h y no 24h)
    """)
    
    # Buscamos debates que iniciaron hace más de X horas, pero menos de X+1 horas (ej: entre 22h y 23h)
    start_lookback = datetime.now() - timedelta(hours=hours_threshold + 1)

    results = execute_query(query, fetchall=True, params=[expiration_time, start_lookback])
    
    if results:
        keys = ['debate_id', 'professional_email', 'case_id', 'start_time']
        return [dict(zip(keys, row)) for row in results]
    return []


def release_expired_debates(hours_threshold: int) -> int:
    """
    Libera los casos y cierra los debates que han excedido el tiempo límite.
    Retorna el número de casos liberados.
    """
    delta = timedelta(hours=hours_threshold)
    expiration_time = datetime.now() - delta
    
    db_conn = get_db_connection()
    if not db_conn:
        return 0

    try:
        with db_conn.cursor() as cur:
            # 1. Seleccionar los debates expirados (más de X horas y no completados)
            select_expired_query = sql.SQL("""
                SELECT ad.case_id
                FROM active_debates ad
                WHERE ad.is_completed = FALSE 
                AND ad.start_time < %s;
            """)
            cur.execute(select_expired_query, [expiration_time])
            expired_cases = [row[0] for row in cur.fetchall()]
            
            if not expired_cases:
                return 0
                
            # 2. Liberar los casos en la tabla 'cases'
            release_cases_query = sql.SQL("UPDATE cases SET is_available = TRUE WHERE case_id = ANY(%s);")
            cur.execute(release_cases_query, [expired_cases])
            cases_released_count = cur.rowcount
            
            # 3. Marcar los debates como completados/fallidos en 'active_debates'
            complete_debates_query = sql.SQL("UPDATE active_debates SET is_completed = TRUE WHERE case_id = ANY(%s) AND is_completed = FALSE;")
            cur.execute(complete_debates_query, [expired_cases])

            db_conn.commit()
            return cases_released_count
            
    except Exception as e:
        db_conn.rollback()
        print(f"ERROR al liberar debates expirados: {e}")
        return 0

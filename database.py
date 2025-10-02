import psycopg2
from psycopg2 import OperationalError
from typing import Optional, List, Dict, Any # Agregado para tipado
import json # Necesario para manejar la serialización de JSONB
# CORREGIDO: Usamos 'configuracion' para ser consistentes con main.py
from configuracion import settings

def get_db_connection():
    """
    Establece y retorna una conexión a la base de datos usando la DATABASE_URL completa.
    Retorna la conexión (psycopg2) o None si falla.
    """
    if not settings.database_url:
        print("ADVERTENCIA: DATABASE_URL no está configurada en settings.")
        return None
        
    try:
        # Conexión utilizando la URL completa, estándar para entornos cloud (Render).
        # Esto simplifica la configuración a una sola variable.
        conn = psycopg2.connect(settings.database_url)
        return conn
    except OperationalError as e:
        # Esto captura fallos como credenciales incorrectas o servidor no disponible.
        print(f"ERROR: Fallo de conexión a PostgreSQL: {e}")
        return None
    except Exception as e:
        print(f"ERROR inesperado al conectar a DB: {e}")
        return None

def create_tables():
    """Crea las tablas de la base de datos si no existen."""
    conn = get_db_connection()
    if conn is None: 
        print("ERROR: No se pudo establecer la conexión a la DB para crear tablas.")
        return

    try:
        cursor = conn.cursor()
        
        # 1. Tabla de Aceptación Legal (Waivers)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS waivers (
                email VARCHAR(255) PRIMARY KEY,
                user_type VARCHAR(50) NOT NULL,
                acceptance_timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # 2. Tabla de Profesionales (Ranking y Créditos)
        # score_refutation es el ranking de la aplicación.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS professionals (
                email VARCHAR(255) PRIMARY KEY,
                name VARCHAR(255),
                specialty VARCHAR(100),
                credits INTEGER DEFAULT 0,
                score_refutation INTEGER DEFAULT 0
            );
        """)
        
        # 3. Tabla de Casos Clínicos (Para Voluntarios y Profesionales)
        # El campo ai_report es JSONB para almacenar el output estructurado de Gemini.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cases (
                case_id VARCHAR(50) PRIMARY KEY,
                volunteer_email VARCHAR(255) REFERENCES waivers(email),
                ai_report JSONB NOT NULL,
                creation_timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                is_available BOOLEAN DEFAULT TRUE 
            );
        """)
        
        # 4. Tabla de Debates Activos (Para la Monetización 24/7 y Caducidad)
        # Esto es crucial para el CRON JOB y la alerta de urgencia.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS active_debates (
                debate_id SERIAL PRIMARY KEY,
                case_id VARCHAR(50) REFERENCES cases(case_id),
                professional_email VARCHAR(255) REFERENCES professionals(email),
                start_time TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                is_completed BOOLEAN DEFAULT FALSE,
                UNIQUE (case_id, professional_email)
            );
        """)
        
        conn.commit()
        print("DEBUG: Tablas de la base de datos verificadas/creadas con éxito.")
    except Exception as e:
        conn.rollback()
        print(f"ERROR al crear tablas: {e}")
    finally:
        if conn: conn.close()

# --- Funciones de Inserción y Actualización ---

def insert_waiver(email: str, user_type: str) -> bool:
    """
    Inserta un nuevo registro de aceptación de términos legales (waiver).
    Retorna True si la inserción fue exitosa, False en caso contrario.
    """
    conn = get_db_connection()
    if conn is None:
        return False

    try:
        cursor = conn.cursor()
        # Usamos la cláusula ON CONFLICT DO NOTHING para manejar el caso donde el email ya existe (PK)
        cursor.execute("""
            INSERT INTO waivers (email, user_type)
            VALUES (%s, %s)
            ON CONFLICT (email) DO NOTHING
            RETURNING email;
        """, (email, user_type))
        
        inserted_email = cursor.fetchone()
        
        conn.commit()
        
        # Retorna True si se insertó un nuevo registro (cursor.rowcount > 0) o si ya existía y la operación fue exitosa.
        return True

    except Exception as e:
        conn.rollback()
        print(f"ERROR: Fallo al insertar waiver para {email}: {e}")
        return False
    finally:
        if conn: conn.close()

def insert_professional(email: str, name: str, specialty: str) -> bool:
    """
    Registra un nuevo profesional. El email debe existir previamente en la tabla waivers.
    """
    conn = get_db_connection()
    if conn is None:
        return False

    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO professionals (email, name, specialty)
            VALUES (%s, %s, %s)
            ON CONFLICT (email) DO UPDATE
            SET name = EXCLUDED.name, specialty = EXCLUDED.specialty;
        """, (email, name, specialty))
        
        conn.commit()
        return True

    except Exception as e:
        conn.rollback()
        print(f"ERROR: Fallo al registrar profesional {email}: {e}")
        return False
    finally:
        if conn: conn.close()


def insert_case(case_id: str, volunteer_email: str, ai_report: Dict[str, Any]) -> bool:
    """
    Inserta un nuevo caso clínico.
    ai_report es un diccionario de Python que se insertará como JSONB.
    """
    conn = get_db_connection()
    if conn is None:
        return False

    try:
        cursor = conn.cursor()
        # psycopg2 serializa automáticamente el dict a JSONB
        cursor.execute("""
            INSERT INTO cases (case_id, volunteer_email, ai_report)
            VALUES (%s, %s, %s);
        """, (case_id, volunteer_email, json.dumps(ai_report)))
        
        conn.commit()
        return True

    except Exception as e:
        conn.rollback()
        print(f"ERROR: Fallo al insertar caso {case_id}: {e}")
        return False
    finally:
        if conn: conn.close()

def update_professional_credits(email: str, amount: int) -> Optional[int]:
    """Añade o resta créditos al profesional. Retorna el nuevo total de créditos."""
    conn = get_db_connection()
    if conn is None: 
        return None
    
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
        print(f"ERROR DB al actualizar créditos para {email}: {e}")
        return None
    finally:
        if conn: conn.close()

def start_active_debate(case_id: str, professional_email: str) -> Optional[int]:
    """
    Inicia un debate activo. Marca el caso como no disponible y crea el registro de debate.
    Retorna el ID del nuevo debate (debate_id) o None si falla.
    """
    conn = get_db_connection()
    if conn is None: 
        return None
    
    try:
        cursor = conn.cursor()
        
        # 1. Marcar el caso como no disponible (is_available = FALSE)
        cursor.execute(
            "UPDATE cases SET is_available = FALSE WHERE case_id = %s AND is_available = TRUE;",
            (case_id,)
        )
        
        # Si no se actualizó ninguna fila, significa que el caso ya no estaba disponible o no existe.
        if cursor.rowcount == 0:
            conn.rollback()
            print(f"ADVERTENCIA: No se pudo tomar el caso {case_id}. Puede que ya no esté disponible.")
            return None
            
        # 2. Insertar el nuevo debate activo
        cursor.execute("""
            INSERT INTO active_debates (case_id, professional_email)
            VALUES (%s, %s)
            RETURNING debate_id;
        """, (case_id, professional_email))
        
        debate_id = cursor.fetchone()[0]
        conn.commit()
        return debate_id
        
    except psycopg2.IntegrityError as e:
        # Esto captura la violación de UNIQUE (case_id, professional_email) o FK.
        conn.rollback()
        print(f"ERROR: El debate ya existe o datos inválidos (FK violation): {e}")
        return None
    except Exception as e:
        conn.rollback()
        print(f"ERROR DB al iniciar debate para caso {case_id}: {e}")
        return None
    finally:
        if conn: conn.close()

def complete_active_debate(debate_id: int) -> bool:
    """
    Marca un debate activo como completado (is_completed = TRUE).
    Retorna True si la actualización fue exitosa, False en caso contrario.
    """
    conn = get_db_connection()
    if conn is None: 
        return False
    
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE active_debates SET is_completed = TRUE WHERE debate_id = %s AND is_completed = FALSE;",
            (debate_id,)
        )
        conn.commit()
        return cursor.rowcount > 0
        
    except Exception as e:
        conn.rollback()
        print(f"ERROR DB al completar debate {debate_id}: {e}")
        return False
    finally:
        if conn: conn.close()


# --- Funciones de Lectura (GET) ---

def get_user_type(email: str) -> Optional[str]:
    """
    Verifica si un usuario ha firmado el waiver y retorna su tipo ('volunteer' o 'professional').
    Retorna None si no existe.
    """
    conn = get_db_connection()
    if conn is None:
        return None

    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT user_type FROM waivers WHERE email = %s;",
            (email,)
        )
        result = cursor.fetchone()
        return result[0] if result else None
    
    except Exception as e:
        print(f"ERROR al obtener tipo de usuario {email}: {e}")
        return None
    finally:
        if conn: conn.close()

def get_available_cases() -> Optional[List[Dict[str, Any]]]:
    """
    Obtiene una lista de todos los casos clínicos que están marcados como disponibles (is_available = TRUE).
    """
    conn = get_db_connection()
    if conn is None:
        return None

    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT case_id, volunteer_email, ai_report, creation_timestamp 
            FROM cases 
            WHERE is_available = TRUE 
            ORDER BY creation_timestamp DESC;
        """)
        
        # Obtener los nombres de las columnas para crear un diccionario por fila
        column_names = [desc[0] for desc in cursor.description]
        cases_list = []
        
        for row in cursor.fetchall():
            case_data = dict(zip(column_names, row))
            # El campo ai_report ya es un diccionario gracias a la gestión de JSONB de psycopg2
            cases_list.append(case_data)
            
        return cases_list
    
    except Exception as e:
        print(f"ERROR al obtener casos disponibles: {e}")
        return None
    finally:
        if conn: conn.close()

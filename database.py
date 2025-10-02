import psycopg2
from psycopg2 import OperationalError
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

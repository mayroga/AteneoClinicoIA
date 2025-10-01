import psycopg2
from config import settings

DATABASE_URL = settings.DATABASE_URL

def get_db_connection():
    """Establece y devuelve una conexión activa a PostgreSQL."""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        print(f"Error al conectar a la base de datos: {e}")
        return None

def create_tables():
    """Crea todas las tablas necesarias."""
    conn = get_db_connection()
    if conn is None:
        return

    cursor = conn.cursor()

    try:
        # 1. Tabla para la aceptación del WAIVER (El Escudo Legal)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS waivers (
                id SERIAL PRIMARY KEY,
                user_type VARCHAR(20) NOT NULL,
                user_email VARCHAR(255) UNIQUE NOT NULL,
                acceptance_timestamp TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # 2. Tabla de CASOS ANÓNIMOS (El Contenido)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS casos_anonimos (
                case_id VARCHAR(50) PRIMARY KEY, -- ID Anónimo: CASO-ABC-123
                tesis_clinica JSONB NOT NULL,
                is_validated BOOLEAN DEFAULT FALSE,
                creation_date TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # 3. Tabla de PROFESIONALES (Ránking y Créditos)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS profesionales (
                id SERIAL PRIMARY KEY,
                email VARCHAR(255) UNIQUE NOT NULL,
                name VARCHAR(255),
                specialty VARCHAR(100),
                credits_balance INTEGER DEFAULT 0,
                refutation_score INTEGER DEFAULT 0
            );
        """)
        
        # 4. Tabla de VOLUNTARIOS (Vínculo al caso anónimo y pago)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS voluntarios (
                id SERIAL PRIMARY KEY,
                email VARCHAR(255) UNIQUE NOT NULL,
                case_id_linked VARCHAR(50) REFERENCES casos_anonimos(case_id)
            );
        """)

        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"Error al crear tablas: {e}")
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

import psycopg2
from config import settings

# --- Conexión y Setup ---

def get_db_connection():
    """Establece una conexión con la base de datos PostgreSQL."""
    try:
        conn = psycopg2.connect(settings.DATABASE_URL)
        print("INFO: Conexión a PostgreSQL exitosa.")
        return conn
    except Exception as e:
        print(f"ERROR: Fallo al conectar con PostgreSQL: {e}")
        return None

def create_tables():
    """Crea las tablas 'profiles', 'cases', y 'case_comments' si no existen."""
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cur:
                # Tabla de Perfiles (Usuarios)
                cur.execute("""
                CREATE TABLE IF NOT EXISTS profiles (
                    email VARCHAR(255) PRIMARY KEY,
                    user_type VARCHAR(20) NOT NULL,
                    is_waiver_signed BOOLEAN DEFAULT FALSE,
                    # Campos de Profesional
                    name VARCHAR(255) NULL,
                    specialty VARCHAR(255) NULL,
                    credits INTEGER DEFAULT 0,
                    ranking_score INTEGER DEFAULT 0,
                    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
                );
                """)
                # Tabla de Casos (pendiente de implementación completa)
                cur.execute("""
                CREATE TABLE IF NOT EXISTS cases (
                    case_id SERIAL PRIMARY KEY,
                    professional_email VARCHAR(255) REFERENCES profiles(email),
                    title VARCHAR(255) NOT NULL,
                    description TEXT NOT NULL,
                    status VARCHAR(50) DEFAULT 'open',
                    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
                );
                """)
                # Tabla de Comentarios (pendiente de implementación completa)
                cur.execute("""
                CREATE TABLE IF NOT EXISTS case_comments (
                    comment_id SERIAL PRIMARY KEY,
                    case_id INTEGER REFERENCES cases(case_id),
                    user_email VARCHAR(255) REFERENCES profiles(email),
                    comment_text TEXT NOT NULL,
                    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
                );
                """)
            conn.commit()
            print("INFO: Tablas de la base de datos verificadas/creadas.")
        except Exception as e:
            print(f"ERROR: Fallo al crear tablas: {e}")
        finally:
            conn.close()
            
# --- Funciones de Autenticación y Perfil ---

def create_profile(email: str, user_type: str) -> bool:
    """Inserta un nuevo perfil si no existe."""
    sql = """
    INSERT INTO profiles (email, user_type)
    VALUES (%s, %s)
    ON CONFLICT (email) DO NOTHING;
    """
    conn = None
    try:
        conn = get_db_connection()
        if conn:
            with conn.cursor() as cur:
                cur.execute(sql, (email, user_type))
            conn.commit()
            return True
        return False
    except Exception as e:
        print(f"ERROR: Fallo al crear perfil: {e}")
        return False
    finally:
        if conn:
            conn.close()

def sign_waiver(email: str) -> bool:
    """Actualiza el campo is_waiver_signed a TRUE."""
    sql = """
    UPDATE profiles
    SET is_waiver_signed = TRUE
    WHERE email = %s;
    """
    conn = None
    try:
        conn = get_db_connection()
        if conn:
            with conn.cursor() as cur:
                cur.execute(sql, (email,))
            conn.commit()
            return True
        return False
    except Exception as e:
        print(f"ERROR: Fallo al firmar waiver: {e}")
        return False
    finally:
        if conn:
            conn.close()

def get_profile_by_email(email: str):
    """Obtiene todos los datos básicos de un perfil por email."""
    sql = "SELECT email, user_type, is_waiver_signed, credits, ranking_score, name, specialty FROM profiles WHERE email = %s;"
    conn = None
    try:
        conn = get_db_connection()
        if conn:
            with conn.cursor() as cur:
                cur.execute(sql, (email,))
                row = cur.fetchone()
                if row:
                    # Mapear los resultados a un diccionario (simplificado)
                    columns = ['email', 'user_type', 'is_waiver_signed', 'credits', 'ranking_score', 'name', 'specialty']
                    return dict(zip(columns, row))
                return None
    except Exception as e:
        print(f"ERROR: Fallo al obtener perfil por email: {e}")
        return None
    finally:
        if conn:
            conn.close()

def get_professional_profile(email: str):
    """Obtiene los datos específicos de un profesional (créditos, ranking, etc.)."""
    sql = "SELECT credits, ranking_score, name, specialty FROM profiles WHERE email = %s AND user_type = 'professional';"
    conn = None
    try:
        conn = get_db_connection()
        if conn:
            with conn.cursor() as cur:
                cur.execute(sql, (email,))
                row = cur.fetchone()
                if row:
                    columns = ['credits', 'ranking_score', 'name', 'specialty']
                    return dict(zip(columns, row))
                return None
    except Exception as e:
        print(f"ERROR: Fallo al obtener perfil profesional: {e}")
        return None
    finally:
        if conn:
            conn.close()

# --- ¡FUNCIÓN NUEVA Y CRUCIAL! ---
def update_professional_details(email: str, name: str, specialty: str) -> bool:
    """Actualiza el nombre y la especialidad del perfil de un profesional."""
    sql = """
    UPDATE profiles
    SET name = %s, specialty = %s
    WHERE email = %s AND user_type = 'professional';
    """
    conn = None
    try:
        conn = get_db_connection()
        if conn:
            with conn.cursor() as cur:
                cur.execute(sql, (name, specialty, email))
            conn.commit()
            # Retorna True si al menos una fila fue afectada (el perfil se actualizó)
            return cur.rowcount > 0
        return False
    except Exception as e:
        print(f"ERROR: Fallo al actualizar detalles de profesional: {e}")
        return False
    finally:
        if conn:
            conn.close()

# --- Funciones de Pagos (Créditos) ---
def update_professional_credits(email: str, amount: int) -> bool:
    """Añade o resta la cantidad de créditos especificada al perfil de un profesional."""
    sql = """
    UPDATE profiles
    SET credits = credits + %s
    WHERE email = %s AND user_type = 'professional';
    """
    conn = None
    try:
        conn = get_db_connection()
        if conn:
            with conn.cursor() as cur:
                cur.execute(sql, (amount, email))
            conn.commit()
            return cur.rowcount > 0
        return False
    except Exception as e:
        print(f"ERROR: Fallo al actualizar créditos: {e}")
        return False
    finally:
        if conn:
            conn.close()

# --- Funciones de Mantenimiento (Cron Jobs) ---
def get_expiring_cases(hours: int = 24) -> list:
    """Obtiene los casos abiertos que expiran en las próximas N horas."""
    # Usamos INTERVAL para calcular la fecha de expiración
    sql = """
    SELECT case_id, professional_email, title, description
    FROM cases
    WHERE status = 'open'
    AND created_at < NOW() - INTERVAL '48 hours' + INTERVAL '24 hours'
    AND created_at > NOW() - INTERVAL '48 hours' - INTERVAL '1 second';
    """
    conn = None
    results = []
    try:
        conn = get_db_connection()
        if conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                rows = cur.fetchall()
                columns = ['case_id', 'professional_email', 'title', 'description']
                for row in rows:
                    results.append(dict(zip(columns, row)))
        return results
    except Exception as e:
        print(f"ERROR: Fallo al obtener casos por expirar: {e}")
        return []
    finally:
        if conn:
            conn.close()

def release_expired_cases() -> int:
    """Cierra los casos que superaron su tiempo límite de 48 horas."""
    sql = """
    UPDATE cases
    SET status = 'expired'
    WHERE status = 'open'
    AND created_at < NOW() - INTERVAL '48 hours';
    """
    conn = None
    try:
        conn = get_db_connection()
        if conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                conn.commit()
                return cur.rowcount
        return 0
    except Exception as e:
        print(f"ERROR: Fallo al liberar casos expirados: {e}")
        return 0
    finally:
        if conn:
            conn.close()


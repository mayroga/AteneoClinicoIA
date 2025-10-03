```python
import os
import asyncpg
import asyncio

# Render proporciona DATABASE_URL como variable de entorno
DATABASE_URL = os.getenv("DATABASE_URL")

# ------------------------------------------------------
# Función para obtener conexión a PostgreSQL
# ------------------------------------------------------
async def get_connection():
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL no está definida en las variables de entorno")
    return await asyncpg.connect(DATABASE_URL)

# ------------------------------------------------------
# Crear tablas si no existen
# ------------------------------------------------------
async def create_tables():
    conn = await get_connection()
    try:
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS profiles (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        );
        """)

        await conn.execute("""
        CREATE TABLE IF NOT EXISTS cases (
            id SERIAL PRIMARY KEY,
            profile_id INTEGER REFERENCES profiles(id) ON DELETE CASCADE,
            description TEXT,
            status TEXT DEFAULT 'open',
            created_at TIMESTAMP DEFAULT NOW()
        );
        """)

        await conn.execute("""
        CREATE TABLE IF NOT EXISTS debates (
            id SERIAL PRIMARY KEY,
            case_id INTEGER REFERENCES cases(id) ON DELETE CASCADE,
            content TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        );
        """)

        print("DEBUG: Tablas creadas/verificadas correctamente ✅")
    finally:
        await conn.close()

# ------------------------------------------------------
# Función de ejemplo para ejecutar consultas
# ------------------------------------------------------
async def fetch_profiles():
    conn = await get_connection()
    try:
        rows = await conn.fetch("SELECT * FROM profiles;")
        return rows
    finally:
        await conn.close()

# ------------------------------------------------------
# Permite ejecutar manualmente si corres: python database.py
# ------------------------------------------------------
if __name__ == "__main__":
    asyncio.run(create_tables())
```

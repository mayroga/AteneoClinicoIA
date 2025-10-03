from typing import Dict, Any, List, Optional
import os
import asyncpg
import asyncio
import json

# --- Configuración de la Conexión ---
DATABASE_POOL: Optional[asyncpg.pool.Pool] = None
DATABASE_URL = os.getenv("DATABASE_URL")

# ------------------------------------------------------
# Conexión y Pool
# ------------------------------------------------------
async def init_db_pool():
    global DATABASE_POOL
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL no está definida en las variables de entorno")
    DATABASE_POOL = await asyncpg.create_pool(DATABASE_URL)

async def get_connection():
    if DATABASE_POOL is None:
        await init_db_pool()
    async with DATABASE_POOL.acquire() as conn:
        yield conn

# ------------------------------------------------------
# Crear tablas si no existen
# ------------------------------------------------------
async def create_tables():
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL no está definida")
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS profiles (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            user_type TEXT DEFAULT 'professional',
            credits INTEGER DEFAULT 0,
            ranking_score INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT NOW()
        );
        """)
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS cases (
            id SERIAL PRIMARY KEY,
            profile_id INTEGER REFERENCES profiles(id) ON DELETE CASCADE,
            case_id TEXT UNIQUE,
            volunteer_email TEXT,
            ai_report JSONB,
            status TEXT DEFAULT 'available',
            created_at TIMESTAMP DEFAULT NOW()
        );
        """)
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS debates (
            id SERIAL PRIMARY KEY,
            case_id INTEGER REFERENCES cases(id) ON DELETE CASCADE,
            professional_email TEXT,
            status TEXT DEFAULT 'active',
            content TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        );
        """)
        print("DEBUG: Tablas creadas/verificadas correctamente ✅")
    finally:
        await conn.close()

# ------------------------------------------------------
# Funciones de acceso a datos
# ------------------------------------------------------
async def get_professional_profile(email: str) -> Optional[Dict[str, Any]]:
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        row = await conn.fetchrow(
            "SELECT * FROM profiles WHERE email = $1;", email
        )
        if row:
            return dict(row)
        return None
    finally:
        await conn.close()

async def update_professional_credits(email: str, change: int) -> Optional[int]:
    profile = await get_professional_profile(email)
    if profile:
        new_val = profile.get("credits", 0) + change
        if new_val >= 0:
            conn = await asyncpg.connect(DATABASE_URL)
            try:
                row = await conn.fetchrow(
                    "UPDATE profiles SET credits=$1 WHERE email=$2 RETURNING credits;",
                    new_val, email
                )
                return row["credits"] if row else None
            finally:
                await conn.close()
    return None

async def insert_case(case_id: str, volunteer_email: str, ai_report: Dict[str, Any]) -> bool:
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await conn.execute(
            "INSERT INTO cases (case_id, volunteer_email, ai_report) VALUES ($1, $2, $3::jsonb);",
            case_id, volunteer_email, json.dumps(ai_report)
        )
        return True
    finally:
        await conn.close()

async def get_available_cases() -> List[Dict[str, Any]]:
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        rows = await conn.fetch(
            "SELECT case_id, ai_report ->> 'ai_diagnosis' AS ai_diagnosis_preview FROM cases WHERE status='available';"
        )
        return [dict(r) for r in rows]
    finally:
        await conn.close()

async def start_active_debate(case_id: str, professional_email: str) -> Optional[int]:
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await conn.execute(
            "UPDATE cases SET status='in_debate' WHERE case_id=$1 AND status='available';", case_id
        )
        row = await conn.fetchrow(
            "INSERT INTO debates (case_id, professional_email) VALUES ($1, $2) RETURNING id;", case_id, professional_email
        )
        return row["id"] if row else None
    finally:
        await conn.close()

async def complete_active_debate(debate_id: int) -> bool:
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await conn.execute("UPDATE debates SET status='completed' WHERE id=$1;", debate_id)
        row = await conn.fetchrow("SELECT case_id FROM debates WHERE id=$1;", debate_id)
        if row:
            await conn.execute("UPDATE cases SET status='debated' WHERE id=$1;", row["case_id"])
        return True
    finally:
        await conn.close()

async def get_ai_report_by_debate_id(debate_id: int) -> Optional[Dict[str, Any]]:
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        row = await conn.fetchrow("""
            SELECT c.ai_report FROM debates d
            JOIN cases c ON d.case_id=c.id
            WHERE d.id=$1;
        """, debate_id)
        return dict(row["ai_report"]) if row and row["ai_report"] else None
    finally:
        await conn.close()

# ------------------------------------------------------
# Permite ejecutar manualmente
# ------------------------------------------------------
if __name__ == "__main__":
    asyncio.run(create_tables())

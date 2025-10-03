```python
from fastapi import FastAPI, Depends, HTTPException, status
from database import create_tables
from payment_routes import router as payment_router
from auth_routes import router as auth_router 
from case_routes import router as case_router 
# ----------------------------------------------------------------------
# ¡DESCOMENTADO! Importación de las funciones de notificación
from notification_service import run_expiration_alert_job, run_cleanup_job
import time 

# --- Inicialización de la Aplicación ---
app = FastAPI(
    title="Plataforma de Debate Clínico",
    description="Backend para gestionar casos, profesionales, y monetización (v. Final).",
    version="1.0.0"
)

# --- Eventos de Inicio y Cierre ---
@app.on_event("startup")
async def startup_event():
    """
    Se ejecuta al iniciar el servidor (uvicorn).
    Asegura que las tablas de la DB existan.
    """
    print("INFO: Iniciando la aplicación. Verificando tablas de la base de datos...")
    await create_tables()  # <-- CORREGIDO (async)

# --- Conexión de Routers ---
# 1. Autenticación, Registro y Perfiles
app.include_router(auth_router)

# 2. Gestión de Pagos (Stripe Webhook y Sesión de Checkout)
app.include_router(payment_router)

# 3. Lógica Central del Negocio (Casos, Gemini, Debate)
app.include_router(case_router)


# --- Ruta Principal de Prueba ---
@app.get("/", tags=["Diagnóstico"])
async def root():
    """Ruta de diagnóstico para verificar que el servidor está activo."""
    return {"message": "Servidor activo y funcionando correctamente. Todos los módulos cargados."}

# --- Ruta para Ejecutar CRON Jobs de Prueba (Activa) ---
@app.get("/run-cron-jobs", tags=["Diagnóstico"])
async def run_cron_jobs():
    """
    Ejecuta las funciones de monitoreo de caducidad y limpieza de debates.
    """
    start_time = time.time()
    
    # Ejecutar Alerta
    run_expiration_alert_job(hours_threshold=22)
    
    # Ejecutar Limpieza 
    cases_released = run_cleanup_job(hours_threshold=24)
    
    end_time = time.time()
    return {
        "message": "Tareas de CRON ejecutadas con éxito.",
        "cases_released": cases_released,
        "execution_time_seconds": round(end_time - start_time, 2)
    }

# --- Configuración de CORS, Middlewares, etc. (irían aquí) ---
```

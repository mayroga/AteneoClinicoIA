import os
from fastapi import APIRouter, HTTPException, UploadFile, File, Depends
from typing import Annotated
from services.ai_service import analyze_case # Importamos la función de análisis

router = APIRouter(prefix="/developer", tags=["Developer/Admin"])

# =================================================================
# 1. RUTA DE PRUEBA DE ANÁLISIS DE CASO (SIN RESTRICCIÓN DE PAGO)
# =================================================================
@router.post("/analizar-caso-ilimitado")
async def developer_analyze_case(
    description: Annotated[str, File(description="Descripción del caso clínico.")],
    file: Annotated[UploadFile | None, File(description="Archivo adjunto (imagen, pdf, etc.).")] = None,
    # 💡 Lógica pendiente: Depende de la clave de bypass de administrador si es necesario
):
    """
    Permite a los administradores o desarrolladores analizar un caso clínico
    con la IA sin pasar por el flujo de pago (ruta de prueba).
    """
    file_path = None
    
    try:
        # 1. Guardar archivo temporalmente
        if file:
            # Usamos el nombre del archivo original para el guardado temporal
            temp_dir = "temp_uploads"
            os.makedirs(temp_dir, exist_ok=True)
            file_path = os.path.join(temp_dir, file.filename)
            
            with open(file_path, "wb") as f:
                content = await file.read()
                f.write(content)

        # 2. Llamar al servicio de análisis
        analysis_result = analyze_case(description, file_path)
        
        return {
            "status": "success",
            "case_description": description,
            "analysis_result": analysis_result,
            "file_processed": file.filename if file else "None"
        }

    except Exception as e:
        print(f"Error en la ruta /analizar-caso-ilimitado: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Fallo al procesar el caso con la IA: {str(e)}"
        )
    finally:
        # 3. La lógica de limpieza del archivo temporal está en ai_service.py,
        # pero para mayor seguridad, la repetimos si el servicio no la hizo.
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as e:
                print(f"Advertencia: No se pudo eliminar el archivo local en el router: {e}")

# =================================================================
# 2. RUTA DE PRUEBA DE STATUS
# =================================================================
@router.get("/status")
def developer_status():
    """Ruta de prueba simple para verificar que el router está en línea."""
    return {"message": "Developer/Admin router en línea."}

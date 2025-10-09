import os
import shutil
import random

# Carpeta donde se guardan los archivos de referencia libres
REFERENCE_DIR = os.path.join(os.path.dirname(__file__), "reference_files")

# -----------------------------
# Obtener archivo de referencia aleatorio
# -----------------------------
def get_random_reference_file(file_type: str):
    """
    file_type: 'image', 'video' o 'text'
    Devuelve la ruta de un archivo de referencia aleatorio según tipo.
    """
    type_dir = os.path.join(REFERENCE_DIR, file_type)
    if not os.path.exists(type_dir):
        return None
    
    files = [f for f in os.listdir(type_dir) if os.path.isfile(os.path.join(type_dir, f))]
    if not files:
        return None
    
    return os.path.join(type_dir, random.choice(files))

# -----------------------------
# Anonimizar archivo subido por usuario
# -----------------------------
def anonymize_file(uploaded_file_path: str, file_type: str):
    """
    Reemplaza el archivo subido por el usuario por un equivalente libre
    """
    reference_file = get_random_reference_file(file_type)
    if not reference_file:
        raise FileNotFoundError(f"No hay archivos de referencia para el tipo {file_type}")
    
    try:
        # Sobrescribir archivo del usuario con el archivo de referencia
        shutil.copy(reference_file, uploaded_file_path)
        return True
    except Exception as e:
        return {"error": str(e)}

# -----------------------------
# Función auxiliar para verificar tipo de archivo
# -----------------------------
def detect_file_type(file_name: str):
    """
    Detecta tipo de archivo basado en extensión: image, video o text
    """
    ext = file_name.lower().split('.')[-1]
    if ext in ["jpg", "jpeg", "png", "gif", "bmp"]:
        return "image"
    elif ext in ["mp4", "avi", "mov", "mkv"]:
        return "video"
    elif ext in ["txt", "md", "json", "csv"]:
        return "text"
    else:
        return "unknown"

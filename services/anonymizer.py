# MOCKUP
def detect_file_type(file_name: str) -> str:
    """Detecta el tipo de archivo (ej. pdf, docx, txt)."""
    return file_name.split('.')[-1].lower()

def anonymize_file(upload_file: bytes, file_type: str, case_id: int) -> str:
    """Simula el proceso de anonimización y guarda el archivo."""
    # 1. Crear un nombre de archivo seguro
    safe_name = f"case_{case_id}_anon.pdf"
    
    # 2. Simular guardado
    # with open(f"storage/{safe_name}", "wb") as f:
    #     f.write(upload_file)

    print(f"INFO: Archivo anonimizado y guardado como {safe_name}")
    
    return safe_name

from typing import Dict, Any, List, Optional

# --- Base de datos en memoria (SOLO PARA PRUEBAS INICIALES) ---
# En producción, esto debe ser reemplazado por PostgreSQL (usando asyncpg o SQLAlchemy)
db_cases: Dict[str, Dict[str, Any]] = {}
db_profiles: Dict[str, Dict[str, Any]] = {
    # Perfiles de ejemplo para pruebas
    "pro1@test.com": {"user_type": "professional", "credits": 5, "ranking_score": 10},
    "vol1@test.com": {"user_type": "volunteer", "credits": 0, "ranking_score": 0},
}
db_debates: Dict[int, Dict[str, Any]] = {}
debate_id_counter = 1

# --- Funciones Requeridas por case_routes.py ---

def get_professional_profile(email: str) -> Optional[Dict[str, Any]]:
    """Obtiene el perfil de un usuario por email."""
    # Simulación: buscar en el diccionario de perfiles
    return db_profiles.get(email)

def update_professional_credits(email: str, change: int) -> Optional[int]:
    """Actualiza los créditos de un profesional, asegurando que no sean negativos."""
    profile = db_profiles.get(email)
    if profile and profile['user_type'] == 'professional':
        profile['credits'] += change
        # Lógica para revertir si el débito deja el saldo negativo
        if profile['credits'] < 0:
            profile['credits'] -= change
            return None
        return profile['credits']
    return None

def insert_case(case_id: str, volunteer_email: str, ai_report: Dict[str, Any]) -> bool:
    """Guarda un nuevo caso clínico con el reporte inicial de la IA."""
    # Simulación: guardar en el diccionario de casos
    db_cases[case_id] = {
        "case_id": case_id,
        "volunteer_email": volunteer_email,
        "ai_report": ai_report,
        "status": "available", # Estado inicial listo para ser tomado
        "taken_by": None,
        "history": [],
    }
    return True

def get_available_cases() -> List[Dict[str, Any]]:
    """Devuelve una lista de casos disponibles para que los profesionales debatan."""
    available = []
    for case_id, case_data in db_cases.items():
        if case_data['status'] == 'available':
            available.append({
                "case_id": case_id,
                "ai_diagnosis_preview": case_data['ai_report'].get('ai_diagnosis', 'N/A')
            })
    return available

def start_active_debate(case_id: str, professional_email: str) -> Optional[int]:
    """Marca un caso como 'in_debate' e inicia el registro en la tabla de debates."""
    global debate_id_counter
    if db_cases.get(case_id) and db_cases[case_id]['status'] == 'available':
        
        db_cases[case_id]['status'] = 'in_debate'
        db_cases[case_id]['taken_by'] = professional_email
        
        # Simulación de registro de debate
        new_debate_id = debate_id_counter
        db_debates[new_debate_id] = {
            "debate_id": new_debate_id,
            "case_id": case_id,
            "professional_email": professional_email,
            "status": "active",
            "start_time": "Now (Mock)"
        }
        debate_id_counter += 1
        return new_debate_id
        
    return None

def complete_active_debate(debate_id: int) -> bool:
    """Cierra un debate activo y actualiza el estado del caso a 'debated'."""
    debate = db_debates.get(debate_id)
    if debate and debate['status'] == 'active':
        debate['status'] = 'completed'
        
        case_id = debate['case_id']
        if db_cases.get(case_id):
            db_cases[case_id]['status'] = 'debated'
            
        return True
    return False

def get_ai_report_by_debate_id(debate_id: int) -> Optional[Dict[str, Any]]:
    """Obtiene el reporte de IA asociado al caso que se está debatiendo."""
    debate = db_debates.get(debate_id)
    if debate:
        case_id = debate['case_id']
        case_data = db_cases.get(case_id)
        if case_data:
            return case_data.get('ai_report')
    return None

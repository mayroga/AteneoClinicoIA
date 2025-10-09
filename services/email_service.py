import os
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email, To, Content
from config import EMAIL_API_KEY, SENDER_EMAIL

def send_email(to_email: str, subject: str, html_content: str):
    """
    Envía un correo electrónico usando SendGrid
    """
    message = Mail(
        from_email=Email(SENDER_EMAIL, name="Ateneo Clínico IA"),
        to_emails=To(to_email),
        subject=subject,
        html_content=Content("text/html", html_content)
    )
    try:
        sg = SendGridAPIClient(EMAIL_API_KEY)
        response = sg.send(message)
        return {
            "status_code": response.status_code,
            "body": response.body,
            "headers": response.headers
        }
    except Exception as e:
        return {"error": str(e)}

def send_welcome_email(user_name: str, user_email: str):
    """
    Correo de bienvenida para nuevos usuarios
    """
    subject = "Bienvenido al Ateneo Clínico IA"
    html_content = f"""
    <html>
        <body>
            <h2>Hola {user_name}!</h2>
            <p>Gracias por unirte al <b>Ateneo Clínico IA</b>.</p>
            <p>Recuerda que esta plataforma es únicamente con fines educativos y de simulación clínica.</p>
            <p>Estamos encantados de tenerte con nosotros.</p>
        </body>
    </html>
    """
    return send_email(user_email, subject, html_content)

def send_case_assignment_email(user_name: str, user_email: str, case_id: int, level: str):
    """
    Correo notificando asignación de un caso clínico
    """
    subject = f"Nueva asignación de caso: #{case_id}"
    html_content = f"""
    <html>
        <body>
            <h2>Hola {user_name},</h2>
            <p>Se te ha asignado un caso clínico con nivel <b>{level}</b>.</p>
            <p>Por favor revisa la plataforma y realiza tu análisis dentro del tiempo establecido.</p>
        </body>
    </html>
    """
    return send_email(user_email, subject, html_content)

from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from config import EMAIL_API_KEY, SENDER_EMAIL

def send_email(to_email: str, subject: str, content: str):
    """
    Envía un correo electrónico usando SendGrid.
    """
    message = Mail(
        from_email=SENDER_EMAIL,
        to_emails=to_email,
        subject=subject,
        html_content=content
    )
    try:
        sg = SendGridAPIClient(EMAIL_API_KEY)
        response = sg.send(message)
        print(f"Correo enviado a {to_email}. Status: {response.status_code}")
        return True
    except Exception as e:
        print(f"Error al enviar correo: {str(e)}")
        return False

# Ejemplo de funciones específicas
def send_welcome_email(user_email: str, user_name: str):
    subject = "Bienvenido al Ateneo Clínico IA"
    content = f"""
    <p>Hola {user_name},</p>
    <p>Gracias por unirte al Ateneo Clínico IA. Tu participación contribuirá al aprendizaje y bienestar global.</p>
    <p>Recuerda: esta plataforma es educativa y no sustituye la atención médica profesional.</p>
    """
    send_email(user_email, subject, content)

def send_payment_confirmation(user_email: str, amount: float):
    subject = "Confirmación de Pago - Ateneo Clínico IA"
    content = f"""
    <p>Hola,</p>
    <p>Hemos recibido tu pago de <b>${amount:.2f}</b> USD. Gracias por tu apoyo al Ateneo Clínico IA.</p>
    <p>Puedes continuar subiendo tus casos clínicos y participar en debates con IA y profesionales.</p>
    """
    send_email(user_email, subject, content)

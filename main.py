import os
import uuid
import json
import datetime
from flask import Flask, request, jsonify, url_for, send_from_directory, abort
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
import stripe
import requests

# ---------- Config ----------
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'devkey')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///ateneoclinico.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
UPLOAD_FOLDER = os.path.join(os.getcwd(), 'static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Env secrets
STRIPE_SECRET_KEY = os.environ.get('STRIPE_SECRET_KEY')
STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
FIREBASE_CONFIG = os.environ.get('__firebase_config__')
EMAIL_API_KEY = os.environ.get('EMAIL_API_KEY')
SENDER_EMAIL = os.environ.get('SENDER_EMAIL')
ADMIN_BYPASS_KEY = os.environ.get('ADMIN_BYPASS_KEY')

# Stripe init
if not STRIPE_SECRET_KEY:
    raise RuntimeError("STRIPE_SECRET_KEY is required in environment")
stripe.api_key = STRIPE_SECRET_KEY

# DB
db = SQLAlchemy(app)

# ---------- Models ----------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(250), unique=True, nullable=False)
    password = db.Column(db.String(250), nullable=False)
    role = db.Column(db.String(50), nullable=False)  # volunteer | professional
    waiver_accepted = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_email = db.Column(db.String(250), nullable=False)
    role = db.Column(db.String(50), nullable=False)
    stripe_pi_id = db.Column(db.String(250), nullable=False)
    amount_cents = db.Column(db.Integer, nullable=False)
    currency = db.Column(db.String(10), default='usd')
    status = db.Column(db.String(50), default='pending')  # pending | succeeded | failed
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

class Case(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    owner_email = db.Column(db.String(250), nullable=True)
    title = db.Column(db.String(500))
    description = db.Column(db.Text)
    media_path = db.Column(db.String(500))
    language = db.Column(db.String(20))
    ai_report = db.Column(db.Text)  # json string
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

class Debate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    case_id = db.Column(db.Integer, nullable=False)
    professional_email = db.Column(db.String(250), nullable=False)
    professional_diagnosis = db.Column(db.Text)
    outcome = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

# ---------- Helpers ----------
def allowed_file(filename):
    ALLOWED = {'png','jpg','jpeg','gif','mp4','mov','avi','pdf'}
    return '.' in filename and filename.rsplit('.',1)[1].lower() in ALLOWED

def detect_language(text):
    # minimal detection fallback
    try:
        from langdetect import detect
        return detect(text)
    except:
        return 'es'

def ai_generate_thesis(case_obj):
    """
    Uses GEMINI_API_KEY to generate a clinical thesis.
    Sends a concise prompt and expects a JSON-like structured text back.
    """
    api_key = GEMINI_API_KEY
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not configured")
    # Attempt OpenAI-compatible responses endpoint (works if provider supports it)
    url = "https://api.openai.com/v1/responses"
    prompt = (
        f"Genera un informe clínico educativo en JSON para debate.\n"
        f"Case Title: {case_obj.title}\n"
        f"Description: {case_obj.description}\n"
        f"Requirements:\n"
        f" - diagnosis: string\n"
        f" - treatment: string (medicamentos y dosis, solo educativo)\n"
        f" - differentials: array of strings\n"
        f" - educational_note: string (explicar que no sustituye atención médica)\n"
        f"Responder SOLO en JSON.\n"
    )
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": "gpt-4o-mini",  # best-effort; replace if needed
        "input": prompt,
        "max_output_tokens": 800
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(f"AI generation failed: {resp.status_code} {resp.text}")
    data = resp.json()
    # Try to extract text
    text = None
    if isinstance(data.get('output'), list):
        text = ''.join([str(x) for x in data['output']])
    elif isinstance(data.get('choices'), list) and data['choices']:
        text = data['choices'][0].get('message', {}).get('content', '')
    else:
        text = data.get('output', '') or data.get('text', '')
    # Ensure JSON
    try:
        parsed = json.loads(text)
    except:
        # if not valid JSON, wrap as educational note
        parsed = {
            "diagnosis": "Hipótesis IA (edu.)",
            "treatment": "Plan sugerido (solo educativo).",
            "differentials": [],
            "educational_note": "No sustituye atención médica."
        }
    return parsed

# ---------- Routes ----------
@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status":"ok", "time": datetime.datetime.utcnow().isoformat()})

@app.route('/api/register', methods=['POST'])
def register():
    data = request.json or {}
    email = data.get('email'); password = data.get('password'); role = data.get('role'); waiver = data.get('waiver_accepted')
    if not all([email, password, role, waiver]):
        return jsonify({"detail":"missing_fields"}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({"detail":"user_exists"}), 400
    u = User(email=email, password=password, role=role, waiver_accepted=True)
    db.session.add(u); db.session.commit()
    return jsonify({"message":"registered","user":{"email":u.email,"role":u.role}}), 201

@app.route('/api/create-payment-intent/<string:role>', methods=['POST'])
def create_payment_intent(role):
    body = request.json or {}
    email = body.get('email')
    amount_cents = int(body.get('amount_cents', 0))
    # validate role and amount ranges
    if role not in ('volunteer','professional'):
        return jsonify({"detail":"invalid_role"}), 400
    if role == 'volunteer':
        if amount_cents < 4000 or amount_cents > 5000:
            return jsonify({"detail":"amount_out_of_range_volunteer"}), 400
    else:
        if amount_cents < 12000 or amount_cents > 18000:
            return jsonify({"detail":"amount_out_of_range_professional"}), 400
    try:
        pi = stripe.PaymentIntent.create(
            amount=amount_cents,
            currency='usd',
            payment_method_types=['card'],
            metadata={'email': email or 'anonymous', 'role': role}
        )
    except Exception as e:
        return jsonify({"detail":"stripe_error","error":str(e)}), 500
    # record pending payment
    payment = Payment(user_email=email or 'anonymous', role=role, stripe_pi_id=pi.id, amount_cents=amount_cents, status='pending')
    db.session.add(payment); db.session.commit()
    return jsonify({"client_secret": pi.client_secret, "payment_intent_id": pi.id})

@app.route('/api/webhook/stripe', methods=['POST'])
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get('Stripe-Signature')
    if not STRIPE_WEBHOOK_SECRET:
        return jsonify({"detail":"webhook_secret_not_configured"}), 500
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except Exception as e:
        return jsonify({"detail":"invalid_signature","error":str(e)}), 400
    # handle event types
    if event['type'] == 'payment_intent.succeeded':
        pi = event['data']['object']
        pi_id = pi['id']
        payment = Payment.query.filter_by(stripe_pi_id=pi_id).first()
        if payment:
            payment.status = 'succeeded'
            db.session.commit()
    elif event['type'] in ('payment_intent.payment_failed','payment_intent.canceled'):
        pi = event['data']['object']
        pi_id = pi['id']
        payment = Payment.query.filter_by(stripe_pi_id=pi_id).first()
        if payment:
            payment.status = 'failed'
            db.session.commit()
    return jsonify({"received": True})

@app.route('/api/volunteer/submit-case', methods=['POST'])
def volunteer_submit_case():
    email = request.headers.get('Email') or request.form.get('email')
    if not email:
        return jsonify({"detail":"missing_email"}), 400
    # verify successful payment exists
    pay = Payment.query.filter_by(user_email=email, role='volunteer', status='succeeded').order_by(Payment.created_at.desc()).first()
    if not pay and request.args.get('bypass') != ADMIN_BYPASS_KEY:
        return jsonify({"detail":"payment_required"}), 402
    title = request.form.get('title') or request.headers.get('Title') or "Caso clínico"
    description = request.form.get('description') or request.headers.get('History-Text') or ""
    file = request.files.get('image_file') or request.files.get('media')
    media_path = None
    if file:
        if not allowed_file(file.filename):
            return jsonify({"detail":"file_type_not_allowed"}), 400
        filename = secure_filename(f"{uuid.uuid4().hex}_{file.filename}")
        path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(path)
        media_path = f"/static/uploads/{filename}"
    language = detect_language(description or title)
    c = Case(owner_email=email, title=title, description=description, media_path=media_path, language=language)
    db.session.add(c); db.session.commit()
    # generate AI thesis (synchronously)
    try:
        report = ai_generate_thesis(c)
    except Exception as e:
        report = {"error":"ai_generation_failed","message": str(e)}
    c.ai_report = json.dumps(report)
    db.session.commit()
    return jsonify({"case_id": c.id, "ai_report": report})

@app.route('/api/professional/get-cases', methods=['GET'])
def professional_get_cases():
    email = request.headers.get('Email')
    if not email:
        return jsonify({"detail":"missing_email"}), 400
    # verify professional payment
    pay = Payment.query.filter_by(user_email=email, role='professional', status='succeeded').order_by(Payment.created_at.desc()).first()
    if not pay and request.args.get('bypass') != ADMIN_BYPASS_KEY:
        return jsonify({"detail":"payment_required"}), 402
    cases = Case.query.filter(Case.ai_report != None).order_by(Case.created_at.desc()).limit(50).all()
    out = []
    for c in cases:
        out.append({
            "case_id": c.id,
            "title": c.title,
            "description": c.description,
            "media": c.media_path,
            "language": c.language,
            "ai_report": json.loads(c.ai_report) if c.ai_report else None
        })
    return jsonify({"cases": out})

@app.route('/api/professional/submit-debate', methods=['POST'])
def professional_submit_debate():
    data = request.json or {}
    case_id = data.get('case_id'); prof_email = request.headers.get('Email'); prof_diag = data.get('professional_diagnosis'); outcome = data.get('outcome')
    if not all([case_id, prof_email, prof_diag, outcome]):
        return jsonify({"detail":"missing_fields"}), 400
    d = Debate(case_id=case_id, professional_email=prof_email, professional_diagnosis=prof_diag, outcome=outcome)
    db.session.add(d); db.session.commit()
    return jsonify({"message":"debate_saved","debate_id": d.id})

@app.route('/free-access/<key>', methods=['GET'])
def free_access(key):
    if key == ADMIN_BYPASS_KEY:
        return jsonify({"message":"access_granted"})
    return jsonify({"detail":"denied"}), 403

@app.route('/static/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# ---------- Init ----------
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
```

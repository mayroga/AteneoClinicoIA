from flask import Flask
from config import Config
from database import init_db
from routes import auth, volunteer, professional, admin

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Inicializar base de datos
    init_db(app)

    # Registrar blueprints
    app.register_blueprint(auth.bp, url_prefix='/auth')
    app.register_blueprint(volunteer.bp, url_prefix='/volunteer')
    app.register_blueprint(professional.bp, url_prefix='/professional')
    app.register_blueprint(admin

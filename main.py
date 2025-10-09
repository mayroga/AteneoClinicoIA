from flask import Flask, render_template
from routes import auth, volunteer, professional, admin
from config import Config
from database import init_db

# Inicialización de la app
app = Flask(__name__)
app.config.from_object(Config)

# Inicializar base de datos
init_db(app)

# Registrar blueprints
app.register_blueprint(auth.auth_bp, url_prefix='/auth')
app.register_blueprint(volunteer.volunteer_bp, url_prefix='/volunteer')
app.register_blueprint(professional.professional_bp, url_prefix='/professional')
app.register_blueprint(admin.admin_bp, url_prefix='/admin')

# Página principal
@app.route('/')
def index():
    return render_template('index.html')

# Error 404
@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

# Ejecutar la app
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

import os
import logging
from flask import Flask
from flask_login import LoginManager
from routes.api import api
from routes.web import web
from routes.auth import auth
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
import database

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# create the app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", os.environ.get('SECRET_KEY', 'dev'))

# Configure SQLAlchemy
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}

# Initialize SQLAlchemy
database.init_app(app)

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message = 'Por favor, faça login para acessar esta página.'
login_manager.login_message_category = "warning"
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    from models import User
    return User.query.get(int(user_id))

# Register blueprints
logger.debug("Registrando blueprint web...")
app.register_blueprint(web)  # Web routes sem prefixo

logger.debug("Registrando blueprint api...")
app.register_blueprint(api)  # API routes com prefixo /api/v1

logger.debug("Registrando blueprint auth...")
app.register_blueprint(auth, url_prefix='/auth')

logger.debug("Blueprints registrados com sucesso")

with app.app_context():
    # Import models para criar as tabelas
    import models  # noqa: F401
    from database import db
    db.create_all()

# Log todas as rotas registradas
logger.debug("Rotas registradas:")
for rule in app.url_map.iter_rules():
    logger.debug(f"{rule.endpoint}: {rule.rule}")
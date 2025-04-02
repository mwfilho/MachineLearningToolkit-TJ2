import os
import logging
from flask import Flask
from routes.api import api
from routes.web import web
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class Base(DeclarativeBase):
    pass

# create the app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", os.environ.get('SECRET_KEY', 'dev'))

# Configure SQLAlchemy
# Construct database URL from components if DATABASE_URL is not available
if os.environ.get("DATABASE_URL"):
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
elif all([os.environ.get(key) for key in ["PGUSER", "PGPASSWORD", "PGHOST", "PGPORT", "PGDATABASE"]]):
    pg_user = os.environ.get("PGUSER")
    pg_pass = os.environ.get("PGPASSWORD")
    pg_host = os.environ.get("PGHOST")
    pg_port = os.environ.get("PGPORT")
    pg_db = os.environ.get("PGDATABASE")
    app.config["SQLALCHEMY_DATABASE_URI"] = f"postgresql://{pg_user}:{pg_pass}@{pg_host}:{pg_port}/{pg_db}"
    logger.debug(f"Constructed database URL from components: postgresql://{pg_user}:***@{pg_host}:{pg_port}/{pg_db}")
else:
    # Fallback to SQLite for development
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///app.db"
    logger.warning("Using SQLite as fallback database. Not recommended for production.")

app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}

# Initialize SQLAlchemy
db = SQLAlchemy(model_class=Base)
db.init_app(app)

# Register blueprints
logger.debug("Registrando blueprint web...")
app.register_blueprint(web)  # Web routes sem prefixo

logger.debug("Registrando blueprint api...")
app.register_blueprint(api)  # API routes com prefixo /api/v1

logger.debug("Blueprints registrados com sucesso")

with app.app_context():
    # Import models para criar as tabelas
    import models  # noqa: F401
    db.create_all()

# Log todas as rotas registradas
logger.debug("Rotas registradas:")
for rule in app.url_map.iter_rules():
    logger.debug(f"{rule.endpoint}: {rule.rule}")
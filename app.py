import os
import logging
from flask import Flask, send_file, make_response
from routes.api import api
from routes.web import web
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from funcoes_mni import gerar_pdf_completo
from io import BytesIO

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
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
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

# Endpoint para download do PDF completo
@app.route('/processo/<num_processo>/pdf')
def download_pdf_processo(num_processo):
    try:
        # Gera o PDF completo
        pdf_bytes = gerar_pdf_completo(num_processo)

        # Cria um objeto BytesIO com o conteúdo do PDF
        pdf_io = BytesIO(pdf_bytes)

        # Configura o nome do arquivo para download
        filename = f"processo_{num_processo}.pdf"

        # Retorna o arquivo PDF para download
        response = make_response(send_file(
            pdf_io,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=filename
        ))

        # Adiciona headers para garantir download correto
        response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    except Exception as e:
        logger.error(f"Erro ao gerar PDF do processo {num_processo}: {str(e)}")
        return {"error": str(e)}, 500

with app.app_context():
    # Import models para criar as tabelas
    import models  # noqa: F401
    db.create_all()

# Log todas as rotas registradas
logger.debug("Rotas registradas:")
for rule in app.url_map.iter_rules():
    logger.debug(f"{rule.endpoint}: {rule.rule}")
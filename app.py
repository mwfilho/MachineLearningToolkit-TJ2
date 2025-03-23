import os
import logging
from flask import Flask, send_file
from routes.api import api
from routes.web import web
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from io import BytesIO
from funcoes_mni import retorna_processo
from utils import merge_process_documents

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

# Rota para mesclar documentos em PDF único
@app.route('/processo/<numero>/pdf', methods=['GET'])
def download_processo_pdf(numero):
    """
    Mescla todos os documentos do processo em um único PDF e retorna para download.

    Args:
        numero (str): Número do processo no formato CNJ
    """
    try:
        # Busca todos os documentos do processo
        resposta = retorna_processo(numero)
        if not resposta.sucesso:
            return {'error': resposta.mensagem}, 400

        # Mescla os documentos em um único PDF
        pdf_data = merge_process_documents(resposta.processo.documentos)

        # Cria o arquivo para download
        pdf_buffer = BytesIO(pdf_data)
        pdf_buffer.seek(0)

        # Retorna o arquivo PDF
        return send_file(
            pdf_buffer,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f'processo_{numero}.pdf'
        )

    except Exception as e:
        logger.error(f"Erro ao gerar PDF do processo {numero}: {str(e)}")
        return {'error': 'Erro ao gerar PDF'}, 500

with app.app_context():
    # Import models para criar as tabelas
    import models  # noqa: F401
    db.create_all()

# Log todas as rotas registradas
logger.debug("Rotas registradas:")
for rule in app.url_map.iter_rules():
    logger.debug(f"{rule.endpoint}: {rule.rule}")
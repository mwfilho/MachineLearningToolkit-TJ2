import os
import logging
from flask import Flask, send_file, request
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
    Mescla documentos do processo em um único PDF, aplicando filtros opcionais.

    Args:
        numero (str): Número do processo no formato CNJ

    Query Parameters:
        tipos_documento: Lista de tipos de documento (separados por vírgula)
        data_inicial: Data inicial (YYYYMMDD)
        data_final: Data final (YYYYMMDD)
        descricao: Texto a buscar na descrição
        apenas_principais: Se deve incluir apenas documentos principais
        apenas_pdf: Se deve incluir apenas documentos PDF
    """
    try:
        # Extrai filtros da query string
        filtros = {}

        if request.args.get('tipos_documento'):
            filtros['tipos_documento'] = request.args.get('tipos_documento').split(',')

        if request.args.get('data_inicial'):
            filtros['data_inicial'] = request.args.get('data_inicial')

        if request.args.get('data_final'):
            filtros['data_final'] = request.args.get('data_final')

        if request.args.get('descricao'):
            filtros['descricao'] = request.args.get('descricao')

        if request.args.get('apenas_principais'):
            filtros['apenas_principais'] = request.args.get('apenas_principais').lower() == 'true'

        if request.args.get('apenas_pdf'):
            filtros['apenas_pdf'] = request.args.get('apenas_pdf').lower() == 'true'

        # Busca todos os documentos do processo
        resposta = retorna_processo(numero)
        if not resposta.sucesso:
            return {'error': resposta.mensagem}, 400

        # Mescla os documentos em um único PDF aplicando os filtros
        pdf_data = merge_process_documents(resposta.processo.documentos, filtros)

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

    except ValueError as e:
        # Erro de validação (nenhum documento encontrado)
        logger.warning(f"Validação: {str(e)}")
        return {'error': str(e)}, 400
    except Exception as e:
        # Erro interno
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
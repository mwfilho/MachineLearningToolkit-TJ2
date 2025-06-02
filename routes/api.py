from flask import Blueprint, jsonify, send_file, request, g, current_app, abort
import os
import logging
from functools import wraps
from funcoes_mni import retorna_processo, retorna_documento_processo, retorna_peticao_inicial_e_anexos
from utils import extract_mni_data, extract_capa_processo, extract_all_document_ids
import core
import tempfile

# Configure logging
logger = logging.getLogger(__name__)

# Criar o blueprint da API
api = Blueprint('api', __name__, url_prefix='/api/v1')

def get_mni_credentials():
    """Obtém credenciais do MNI dos headers ou environment"""
    cpf = request.headers.get('X-MNI-CPF') or os.environ.get('MNI_ID_CONSULTANTE')
    senha = request.headers.get('X-MNI-SENHA') or os.environ.get('MNI_SENHA_CONSULTANTE')
    return cpf, senha

# def require_api_key(f):
#     @wraps(f)
#     def decorated_function(*args, **kwargs):
#         api_key = request.headers.get('X-API-KEY') or request.args.get('api_key')
#         if not api_key:
#             return jsonify({
#                 'erro': 'API key não fornecida',
#                 'mensagem': 'Forneça uma API key válida no header X-API-KEY ou no parâmetro api_key'
#             }), 401
#         key_entry = ApiKey.query.filter_by(key=api_key, is_active=True).first()
#         g.api_user = key_entry.user
#         return f(*args, **kwargs)
#     return decorated_function

@api.before_request
def log_request_info():
    """Log detalhes da requisição para debug"""
    logger.debug('Headers: %s', dict(request.headers))
    logger.debug('Body: %s', request.get_data())
    logger.debug('URL: %s', request.url)

@api.route('/processo/<num_processo>', methods=['GET'])
# @require_api_key              # Comentado
def get_processo(num_processo):
    try:
        cpf, senha = get_mni_credentials()
        if not cpf or not senha:
            return jsonify({
                'erro': 'Credenciais MNI não fornecidas',
                'mensagem': 'Forneça as credenciais nos headers X-MNI-CPF e X-MNI-SENHA'
            }), 401

        resposta = retorna_processo(num_processo, cpf=cpf, senha=senha)
        dados = extract_mni_data(resposta)
        return jsonify(dados_formatados)
    except Exception as e:
        logger.exception("Erro ao consultar processo")
        return jsonify({'erro': str(e)}), 500
        
        # Se o processo existe e tem sucesso, atualize a lista de documentos
        # usando a abordagem robusta para garantir todos os documentos
        if dados['sucesso'] and 'processo' in dados:
            # Obter a lista completa e robusta de IDs
            ids_dados = extract_all_document_ids(resposta, num_processo=num_processo, 
                                             cpf=cpf, senha=senha)
            
            if ids_dados['sucesso'] and 'documentos' in ids_dados:
                logger.debug(f"API: Lista robusta de documentos extraída com {len(ids_dados.get('documentos', []))} IDs")
                
                # Criar mapa de documentos existentes para facilitar a busca
                docs_map = {}
                # Processar documentos principais
                for doc in dados['processo'].get('documentos', []):
                    doc_id = doc['idDocumento']
                    docs_map[doc_id] = doc
                
                # Processar documentos vinculados
                for doc in dados['processo'].get('documentos', []):
                    for vinc in doc.get('documentos_vinculados', []):
                        vinc_id = vinc['idDocumento']
                        docs_map[vinc_id] = vinc
                
                # Verificar se existem documentos na lista robusta que não foram encontrados na resposta zeep
                docs_principais = []
                docs_secundarios = {}
                
                ids_xml = set(d['idDocumento'] for d in ids_dados['documentos'])
                ids_zeep = set(docs_map.keys())
                ids_faltando = ids_xml - ids_zeep
                
                if ids_faltando:
                    logger.debug(f"API: Encontrados {len(ids_faltando)} documentos na abordagem XML/lxml que não estavam no zeep")
                    
                    # Adiciona entradas para os documentos faltantes com dados básicos
                    for doc_id in ids_faltando:
                        # Procurar nas informações da lista robusta
                        doc_info = next((d for d in ids_dados['documentos'] if d['idDocumento'] == doc_id), None)
                        
                        if doc_info:
                            docs_map[doc_id] = {
                                'idDocumento': doc_id,
                                'tipoDocumento': doc_info.get('tipoDocumento', ''),
                                'descricao': doc_info.get('descricao', f'Documento {doc_id}'),
                                'dataHora': '',
                                'mimetype': doc_info.get('mimetype', ''),
                                'documentos_vinculados': []
                            }
                
                # Construir/atualizar a lista de documentos completa e ordenada
                # baseada na ordem da lista robusta de IDs
                documentos_completos = []
                for doc_info in ids_dados['documentos']:
                    doc_id = doc_info['idDocumento']
                    if doc_id in docs_map:
                        documentos_completos.append(docs_map[doc_id])
                
                # Atualizar a lista de documentos no resultado
                dados['processo']['documentos'] = documentos_completos
                dados['processo']['total_documentos'] = len(documentos_completos)
                
                # Adicionar a lista bruta de IDs para debug/referência
                dados['processo']['documentos_ids_brutos'] = [d['idDocumento'] for d in ids_dados['documentos']]
        
        return jsonify(dados)

    except Exception as e:
        logger.error(f"API: Erro ao consultar processo: {str(e)}", exc_info=True)
        return jsonify({
            'erro': str(e),
            'mensagem': 'Erro ao consultar processo'
        }), 500

@api.route('/processo/<num_processo>/documento/<num_documento>', methods=['GET'])
# @require_api_key
def download_documento(num_processo, num_documento):
    """
    Faz download de um documento específico do processo
    """
    try:
        logger.debug(f"API: Download do documento {num_documento} do processo {num_processo}")
        cpf, senha = get_mni_credentials()

        if not cpf or not senha:
            return jsonify({
                'erro': 'Credenciais MNI não fornecidas',
                'mensagem': 'Forneça as credenciais nos headers X-MNI-CPF e X-MNI-SENHA'
            }), 401

        resposta = retorna_documento_processo(num_processo, num_documento, cpf=cpf, senha=senha)

        if 'msg_erro' in resposta:
            return jsonify({
                'erro': resposta['msg_erro'],
                'mensagem': 'Erro ao baixar documento'
            }), 404

        # Criar arquivo temporário para download
        extensao = core.mime_to_extension.get(resposta['mimetype'], '.bin')
        temp_dir = tempfile.mkdtemp()
        file_path = os.path.join(temp_dir, f'{num_documento}{extensao}')

        with open(file_path, 'wb') as f:
            f.write(resposta['conteudo'])

        return send_file(
            file_path,
            mimetype=resposta['mimetype'],
            as_attachment=True,
            download_name=f'documento_{num_documento}{extensao}'
        )

    except Exception as e:
        logger.error(f"API: Erro ao baixar documento: {str(e)}", exc_info=True)
        return jsonify({
            'erro': str(e),
            'mensagem': 'Erro ao baixar documento'
        }), 500
        
@api.route('/processo/<num_processo>/peticao-inicial', methods=['GET'])
# @require_api_key
def get_peticao_inicial(num_processo):
    """
    Retorna a petição inicial e seus anexos para o processo informado
    """
    try:
        logger.debug(f"API: Buscando petição inicial do processo {num_processo}")
        cpf, senha = get_mni_credentials()

        if not cpf or not senha:
            return jsonify({
                'erro': 'Credenciais MNI não fornecidas',
                'mensagem': 'Forneça as credenciais nos headers X-MNI-CPF e X-MNI-SENHA'
            }), 401

        resposta = retorna_peticao_inicial_e_anexos(num_processo, cpf=cpf, senha=senha)

        if 'msg_erro' in resposta:
            return jsonify({
                'erro': resposta['msg_erro'],
                'mensagem': 'Erro ao buscar petição inicial'
            }), 404

        return jsonify(resposta)

    except Exception as e:
        logger.error(f"API: Erro ao buscar petição inicial: {str(e)}", exc_info=True)
        return jsonify({
            'erro': str(e),
            'mensagem': 'Erro ao buscar petição inicial'
        }), 500
        
@api.route('/processo/<num_processo>/documentos/ids', methods=['GET'])
# @require_api_key
def get_document_ids(num_processo):
    """
    Retorna uma lista única com todos os IDs de documentos do processo, incluindo vinculados,
    na ordem em que aparecem no processo.
    
    Utiliza uma abordagem robusta que garante a extração de todos os documentos, mesmo
    aqueles que podem ser perdidos pela biblioteca SOAP quando há múltiplos documentos vinculados.
    """
    try:
        logger.debug(f"API: Consultando lista de IDs de documentos do processo {num_processo}")
        cpf, senha = get_mni_credentials()

        if not cpf or not senha:
            return jsonify({
                'erro': 'Credenciais MNI não fornecidas',
                'mensagem': 'Forneça as credenciais nos headers X-MNI-CPF e X-MNI-SENHA'
            }), 401

        # Obtém o processo completo com documentos usando a abordagem tradicional primeiro
        resposta = retorna_processo(num_processo, cpf=cpf, senha=senha)

        # Extrai os IDs dos documentos usando a nova abordagem robusta
        # Passa o número do processo e credenciais para permitir nova consulta se necessário
        dados = extract_all_document_ids(resposta, num_processo=num_processo, cpf=cpf, senha=senha)
        return jsonify(dados)

    except Exception as e:
        logger.error(f"API: Erro ao consultar lista de IDs de documentos: {str(e)}", exc_info=True)
        return jsonify({
            'erro': str(e),
            'mensagem': 'Erro ao consultar lista de IDs de documentos'
        }), 500

@api.route('/processo/<num_processo>/capa', methods=['GET'])
# @require_api_key
def get_capa_processo(num_processo):
    """
    Retorna apenas os dados da capa do processo (sem documentos),
    incluindo dados básicos, assuntos, polos e movimentações
    """
    try:
        logger.debug(f"API: Consultando capa do processo {num_processo}")
        cpf, senha = get_mni_credentials()

        if not cpf or not senha:
            return jsonify({
                'erro': 'Credenciais MNI não fornecidas',
                'mensagem': 'Forneça as credenciais nos headers X-MNI-CPF e X-MNI-SENHA'
            }), 401

        # Usando o parâmetro incluir_documentos=False para melhor performance
        resposta = retorna_processo(num_processo, cpf=cpf, senha=senha, incluir_documentos=False)

        # Extrair apenas os dados da capa do processo
        dados = extract_capa_processo(resposta)
        return jsonify(dados)

    except Exception as e:
        logger.error(f"API: Erro ao consultar capa do processo: {str(e)}", exc_info=True)
        return jsonify({
            'erro': str(e),
            'mensagem': 'Erro ao consultar capa do processo'
        }), 500

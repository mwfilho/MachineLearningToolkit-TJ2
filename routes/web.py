from flask import Blueprint, render_template, request, send_file, flash, redirect, url_for
from flask_login import login_required, current_user
import tempfile
import os
import logging
import functools
from funcoes_mni import retorna_processo, retorna_documento_processo, retorna_peticao_inicial_e_anexos
from utils import extract_mni_data, extract_capa_processo, extract_all_document_ids
import core

# Configure logging
logger = logging.getLogger(__name__)

web = Blueprint('web', __name__)

# Decorator personalizado para proteção de rotas
def debug_required(f):
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            logger.warning(f"Tentativa de acesso não autorizado à rota: {request.path}")
            return redirect(url_for('auth.login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

@web.route('/')
def index():
    return render_template('index.html')

@web.route('/debug')
@debug_required
def debug():
    # Se chegou aqui, o usuário está autenticado
    logger.debug(f"Acesso à tela de debug por: {current_user.username}")
    return render_template('debug.html')

@web.route('/debug/consulta', methods=['POST'])
@debug_required
def debug_consulta():
    num_processo = request.form.get('num_processo')
    cpf = request.form.get('cpf')
    senha = request.form.get('senha')

    try:
        logger.debug(f"Consultando processo: {num_processo}")
        # Obtenha credenciais finais para passar ao extrator de IDs
        cpf_final = cpf or os.environ.get('MNI_ID_CONSULTANTE')
        senha_final = senha or os.environ.get('MNI_SENHA_CONSULTANTE')
        
        resposta = retorna_processo(
            num_processo,
            cpf=cpf_final,
            senha=senha_final
        )

        # Extrair dados relevantes
        dados = extract_mni_data(resposta)
        logger.debug(f"Dados extraídos: {dados}")

        # Se o processo existe e tem sucesso, atualize a lista de documentos
        # usando a abordagem robusta para garantir todos os documentos
        if dados['sucesso'] and dados['processo']:
            # Obter a lista completa e robusta de IDs
            ids_dados = extract_all_document_ids(resposta, num_processo=num_processo, 
                                              cpf=cpf_final, senha=senha_final)
            
            if ids_dados['sucesso'] and ids_dados.get('documentos'):
                logger.debug(f"Lista robusta de documentos extraída com {len(ids_dados.get('documentos', []))} IDs")
                
                # Criar mapa de documentos existentes para facilitar a busca
                docs_map = {}
                for doc in dados['processo'].get('documentos', []):
                    doc_id = doc['idDocumento']
                    docs_map[doc_id] = doc
                
                # Processar documentos vinculados para o mapa
                for doc in dados['processo'].get('documentos', []):
                    for vinc in doc.get('documentos_vinculados', []):
                        vinc_id = vinc['idDocumento']
                        docs_map[vinc_id] = vinc

                # Processar hierarquia de documentos a partir da lista robusta
                docs_principais = {}
                docs_vinculados = {}

                # Primeiro passo: coletar todos os principais e vinculados do resultado original
                if dados['processo'].get('documentos'):
                    for doc in dados['processo']['documentos']:
                        doc_id = doc['idDocumento']
                        docs_principais[doc_id] = doc

                        # Se tem documentos vinculados, adiciona à estrutura
                        if doc.get('documentos_vinculados'):
                            docs_vinculados[doc_id] = doc['documentos_vinculados']
                
                # Segundo passo: adicionar quaisquer documentos que só foram encontrados na lista robusta
                for doc_info in ids_dados.get('documentos', []):
                    doc_id = doc_info['idDocumento']
                    
                    # Verifica se este ID já está nos documentos principais
                    if doc_id not in docs_principais:
                        # Se o documento consta no mapa de docs originais, use esse
                        if doc_id in docs_map:
                            docs_principais[doc_id] = docs_map[doc_id]
                        else:
                            # Caso contrário, use as informações básicas da lista de IDs
                            docs_principais[doc_id] = {
                                'idDocumento': doc_id,
                                'tipoDocumento': doc_info.get('tipoDocumento', ''),
                                'descricao': doc_info.get('descricao', f'Documento {doc_id}'),
                                'documentos_vinculados': []
                            }
                
                # Adicionar documentos vinculados aos principais
                for doc_id, doc_info in docs_principais.items():
                    if doc_id in docs_vinculados:
                        doc_info['documentos_vinculados'] = docs_vinculados[doc_id]
                    else:
                        doc_info['documentos_vinculados'] = []
                
                logger.debug(f"Total de documentos na hierarquia: {len(docs_principais)}")

                return render_template('debug.html', 
                                resposta=dados,
                                documentos_hierarquia=docs_principais,
                                documentos_ids_totais=ids_dados.get('documentos', []),
                                num_processo=num_processo)

        # Fallback para o comportamento padrão se a lógica acima falhar
        docs_principais = {}
        docs_vinculados = {}

        if dados['sucesso'] and dados['processo'].get('documentos'):
            for doc in dados['processo']['documentos']:
                doc_id = doc['idDocumento']
                docs_principais[doc_id] = doc

                # Se tem documentos vinculados, adiciona à estrutura
                if doc['documentos_vinculados']:
                    docs_vinculados[doc_id] = doc['documentos_vinculados']

        # Adicionar documentos vinculados aos principais
        for doc_id, doc_info in docs_principais.items():
            if doc_id in docs_vinculados:
                doc_info['documentos_vinculados'] = docs_vinculados[doc_id]
            else:
                doc_info['documentos_vinculados'] = []

        return render_template('debug.html', 
                           resposta=dados,
                           documentos_hierarquia=docs_principais,
                           num_processo=num_processo)  

    except Exception as e:
        logger.error(f"Erro na consulta de debug: {str(e)}", exc_info=True)
        flash(f'Erro na consulta: {str(e)}', 'error')
        return render_template('debug.html')

@web.route('/debug/documento', methods=['POST'])
@debug_required
def debug_documento():
    num_processo = request.form.get('num_processo')
    id_documento = request.form.get('id_documento')

    try:
        logger.debug(f"Consultando documento específico: Processo={num_processo}, ID={id_documento}")
        resposta = retorna_documento_processo(num_processo, id_documento)

        if 'msg_erro' in resposta:
            flash(resposta['msg_erro'], 'error')
            return render_template('debug.html')

        # Criar uma versão segura para exibição
        doc_info = {
            'num_processo': resposta.get('num_processo', ''),
            'id_documento': resposta.get('id_documento', ''),
            'id_tipo_documento': resposta.get('id_tipo_documento', ''),
            'mimetype': resposta.get('mimetype', ''),
            'conteudo': '[CONTEÚDO BINÁRIO]' if resposta.get('conteudo') else 'Sem conteúdo'
        }

        logger.debug(f"Documento encontrado: {doc_info}")
        return render_template('debug.html', resposta=doc_info)

    except Exception as e:
        logger.error(f"Erro na consulta do documento: {str(e)}", exc_info=True)
        flash(f'Erro na consulta do documento: {str(e)}', 'error')
        return render_template('debug.html')

@web.route('/debug/peticao-inicial', methods=['POST'])
@debug_required
def debug_peticao_inicial():
    num_processo = request.form.get('num_processo')
    cpf = request.form.get('cpf')
    senha = request.form.get('senha')
    
    try:
        logger.debug(f"Consultando petição inicial: Processo={num_processo}")
        resposta = retorna_peticao_inicial_e_anexos(
            num_processo,
            cpf=cpf or os.environ.get('MNI_ID_CONSULTANTE'),
            senha=senha or os.environ.get('MNI_SENHA_CONSULTANTE')
        )
        
        if 'msg_erro' in resposta:
            flash(resposta['msg_erro'], 'error')
            return render_template('debug.html')
            
        logger.debug(f"Petição inicial encontrada: {resposta}")
        return render_template('debug.html', 
                               resposta=resposta,
                               peticao_inicial=resposta.get('peticao_inicial'),
                               anexos=resposta.get('anexos', []),
                               num_processo=num_processo)
                               
    except Exception as e:
        logger.error(f"Erro na consulta da petição inicial: {str(e)}", exc_info=True)
        flash(f'Erro na consulta da petição inicial: {str(e)}', 'error')
        return render_template('debug.html')

@web.route('/download_documento/<num_processo>/<num_documento>')
@debug_required
def download_documento(num_processo, num_documento):
    try:
        logger.debug(f"Attempting to download document {num_documento} from process {num_processo}")
        resposta = retorna_documento_processo(num_processo, num_documento)

        if 'msg_erro' in resposta:
            flash(resposta['msg_erro'], 'error')
            return render_template('index.html')

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
        logger.error(f"Erro ao baixar documento: {str(e)}", exc_info=True)
        flash(f'Erro ao baixar documento: {str(e)}', 'error')
        return render_template('index.html')

@web.route('/debug/documentos-ids', methods=['POST'])
@debug_required
def debug_document_ids():
    num_processo = request.form.get('num_processo')
    cpf = request.form.get('cpf')
    senha = request.form.get('senha')
    
    try:
        logger.debug(f"Consultando lista de IDs de documentos: {num_processo}")
        resposta = retorna_processo(
            num_processo,
            cpf=cpf or os.environ.get('MNI_ID_CONSULTANTE'),
            senha=senha or os.environ.get('MNI_SENHA_CONSULTANTE')
        )
        
        # Extrair a lista ordenada de IDs utilizando a nova abordagem robusta
        # Passamos o número do processo e credenciais para permitir nova consulta via XML/lxml
        cpf_final = cpf or os.environ.get('MNI_ID_CONSULTANTE')
        senha_final = senha or os.environ.get('MNI_SENHA_CONSULTANTE')
        dados = extract_all_document_ids(resposta, num_processo=num_processo, cpf=cpf_final, senha=senha_final)
        
        logger.debug(f"Lista de IDs extraída: {dados}")
        logger.debug(f"Total de documentos encontrados: {len(dados.get('documentos', []))}")
        
        return render_template('debug.html', 
                           resposta=dados,
                           documentos_ids=dados.get('documentos', []),
                           num_processo=num_processo)
                           
    except Exception as e:
        logger.error(f"Erro na consulta de IDs de documentos: {str(e)}", exc_info=True)
        flash(f'Erro na consulta de IDs de documentos: {str(e)}', 'error')
        return render_template('debug.html')

@web.route('/debug/capa', methods=['POST'])
@debug_required
def debug_capa_processo():
    num_processo = request.form.get('num_processo')
    cpf = request.form.get('cpf')
    senha = request.form.get('senha')

    try:
        logger.debug(f"Consultando capa do processo: {num_processo}")
        resposta = retorna_processo(
            num_processo,
            cpf=cpf or os.environ.get('MNI_ID_CONSULTANTE'),
            senha=senha or os.environ.get('MNI_SENHA_CONSULTANTE'),
            incluir_documentos=False  # Não incluir documentos para melhor performance
        )

        # Extrair apenas os dados da capa do processo
        dados = extract_capa_processo(resposta)
        logger.debug(f"Dados da capa extraídos: {dados}")

        return render_template('debug.html', 
                           resposta=dados,
                           capa_processo=True,
                           num_processo=num_processo)  

    except Exception as e:
        logger.error(f"Erro na consulta da capa: {str(e)}", exc_info=True)
        flash(f'Erro na consulta da capa: {str(e)}', 'error')
        return render_template('debug.html')

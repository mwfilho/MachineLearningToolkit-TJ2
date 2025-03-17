import os
from app import app
from flask import render_template, request, send_file, flash
import core
from funcoes_mni import retorna_processo, retorna_documento_processo
from controle.exceptions import ExcecaoConsultaMNI
import tempfile
import os
import logging
from zeep.helpers import serialize_object
import json
from xml.etree import ElementTree

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def xml_to_dict(element):
    """Convert XML element to dictionary"""
    if not isinstance(element, ElementTree.Element):
        return element

    result = {}
    for child in element:
        if child:
            if len(child) == 1:
                result[child.tag] = xml_to_dict(child[0])
            else:
                result[child.tag] = xml_to_dict(child)
        else:
            result[child.tag] = child.text
    return result

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/debug')
def debug():
    return render_template('debug.html')

@app.route('/debug/consulta', methods=['POST'])
def debug_consulta():
    num_processo = request.form.get('num_processo')

    try:
        resposta = retorna_processo(num_processo)
        logger.debug(f"Resposta completa do MNI recebida para o processo {num_processo}")

        # Processar hierarquia de documentos
        docs_principais = {}
        docs_vinculados = {}

        if resposta.sucesso and hasattr(resposta.processo, 'documento'):
            for doc in resposta.processo.documento:
                # Verificar se é um documento vinculado
                id_vinculado = getattr(doc, 'idDocumentoVinculado', None)
                doc_id = getattr(doc, 'idDocumento', '')

                doc_info = {
                    'id': doc_id,
                    'tipo': getattr(doc, 'tipoDocumento', ''),
                    'descricao': getattr(doc, 'descricao', ''),
                    'data': getattr(doc, 'dataHora', '')
                }

                logger.debug(f"Processando documento: {doc_info}")

                if id_vinculado:
                    # É um documento vinculado
                    if id_vinculado not in docs_vinculados:
                        docs_vinculados[id_vinculado] = []
                    docs_vinculados[id_vinculado].append(doc_info)
                else:
                    # É um documento principal
                    docs_principais[doc_id] = doc_info

        # Adicionar documentos vinculados aos principais
        for doc_id in docs_principais:
            if doc_id in docs_vinculados:
                docs_principais[doc_id]['documentos_vinculados'] = docs_vinculados[doc_id]

        # Serializar resposta removendo elementos XML
        try:
            serialized = serialize_object(resposta)
            # Remove conteúdos binários
            if isinstance(serialized, dict) and 'processo' in serialized:
                if 'documento' in serialized['processo']:
                    for doc in serialized['processo']['documento']:
                        if 'conteudo' in doc:
                            doc['conteudo'] = '[CONTEÚDO BINÁRIO]'
        except Exception as e:
            logger.error(f"Erro na serialização: {e}")
            serialized = {
                'erro_serializacao': str(e),
                'processo': {
                    'numero': num_processo,
                    'mensagem': 'Erro ao serializar resposta completa'
                }
            }

        return render_template('debug.html', 
                           resposta=serialized,
                           documentos_hierarquia=docs_principais)

    except Exception as e:
        logger.error(f"Erro na consulta de debug: {str(e)}", exc_info=True)
        flash(f'Erro na consulta: {str(e)}', 'error')
        return render_template('debug.html')

@app.route('/debug/documento', methods=['POST'])
def debug_documento():
    num_processo = request.form.get('num_processo')
    id_documento = request.form.get('id_documento')

    try:
        logger.debug(f"Consultando documento específico: Processo={num_processo}, ID={id_documento}")
        resposta = retorna_documento_processo(num_processo, id_documento)

        if 'msg_erro' in resposta:
            flash(resposta['msg_erro'], 'error')
            return render_template('debug.html')

        # Criar uma cópia da resposta para serialização
        resposta_serializable = {}
        for key, value in resposta.items():
            if key == 'conteudo':
                resposta_serializable[key] = '[CONTEÚDO BINÁRIO]'
            else:
                resposta_serializable[key] = value

        logger.debug(f"Documento encontrado: {resposta_serializable}")
        return render_template('debug.html', resposta=resposta_serializable)

    except Exception as e:
        logger.error(f"Erro na consulta do documento: {str(e)}", exc_info=True)
        flash(f'Erro na consulta do documento: {str(e)}', 'error')
        return render_template('debug.html')

@app.route('/consultar', methods=['POST'])
def consultar():
    num_processo = request.form.get('num_processo')

    if not num_processo:
        flash('Por favor, insira um número de processo válido.', 'error')
        return render_template('index.html')

    try:
        resposta = retorna_processo(num_processo)
        logger.debug(f"MNI Response received. Success: {resposta.sucesso}")

        if resposta and resposta.sucesso:
            processo_info = {
                'numero': getattr(resposta.processo, 'numero', num_processo),
                'classeProcessual': getattr(resposta.processo, 'classeProcessual', 'Não disponível'),
                'dataAjuizamento': getattr(resposta.processo, 'dataAjuizamento', 'Não disponível'),
                'orgaoJulgador': {
                    'descricao': getattr(getattr(resposta.processo, 'orgaoJulgador', {}), 'descricao', 'Não disponível')
                },
                'situacao': getattr(resposta.processo, 'situacao', 'Não disponível')
            }

            documentos = []
            if hasattr(resposta.processo, 'documento'):
                logger.debug(f"Processando {len(resposta.processo.documento)} documentos")

                for doc in resposta.processo.documento:
                    doc_info = {
                        'id': getattr(doc, 'idDocumento', ''),
                        'tipo': getattr(doc, 'tipoDocumento', ''),
                        'nome': getattr(doc, 'nome', ''),
                        'descricao': getattr(doc, 'descricao', ''),
                        'assunto': getattr(doc, 'assunto', ''),
                        'movimento': getattr(doc, 'movimento', ''),
                        'data_protocolo': getattr(doc, 'dataProtocolo', ''),
                        'nivel_sigilo': getattr(doc, 'nivelSigilo', 0)
                    }

                    if doc_info['nivel_sigilo'] < 5:
                        documentos.append(doc_info)
                        logger.debug(f"Documento adicionado: {doc_info}")
                    else:
                        logger.debug(f"Documento sigiloso ignorado: {doc_info['id']}")

            logger.debug(f"Total de documentos processados: {len(documentos)}")
            return render_template('result.html', 
                                   processo=processo_info,
                                   documentos=documentos)
        else:
            msg = getattr(resposta, 'mensagem', 'Processo não encontrado ou erro na consulta.')
            flash(msg, 'error')
            return render_template('index.html')

    except ExcecaoConsultaMNI as e:
        flash(f'Erro na consulta: {str(e)}', 'error')
        return render_template('index.html')
    except Exception as e:
        logger.error(f"Erro inesperado: {str(e)}", exc_info=True)
        flash(f'Erro inesperado: {str(e)}', 'error')
        return render_template('index.html')

@app.route('/download_documento/<num_processo>/<num_documento>')
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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
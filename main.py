import os
from app import app
from flask import render_template, request, send_file, flash
import core
from funcoes_mni import retorna_processo, retorna_documento_processo
from controle.exceptions import ExcecaoConsultaMNI
import tempfile
import os
import logging

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def extract_mni_data(resposta):
    """Extrai dados relevantes da resposta MNI de forma segura"""
    try:
        dados = {
            'sucesso': getattr(resposta, 'sucesso', False),
            'mensagem': getattr(resposta, 'mensagem', ''),
            'processo': {}
        }

        if hasattr(resposta, 'processo'):
            processo = resposta.processo
            dados['processo'] = {
                'numero': getattr(processo, 'numero', ''),
                'classeProcessual': getattr(processo, 'classeProcessual', ''),
                'dataAjuizamento': getattr(processo, 'dataAjuizamento', ''),
                'orgaoJulgador': getattr(getattr(processo, 'orgaoJulgador', {}), 'descricao', ''),
                'documentos': []
            }

            if hasattr(processo, 'documento'):
                for doc in processo.documento:
                    doc_info = {
                        'idDocumento': getattr(doc, 'idDocumento', ''),
                        'idDocumentoVinculado': getattr(doc, 'idDocumentoVinculado', ''),
                        'tipoDocumento': getattr(doc, 'tipoDocumento', ''),
                        'descricao': getattr(doc, 'descricao', ''),
                        'dataHora': getattr(doc, 'dataHora', ''),
                        'mimetype': getattr(doc, 'mimetype', ''),
                        'nivelSigilo': getattr(doc, 'nivelSigilo', 0)
                    }
                    dados['processo']['documentos'].append(doc_info)

        return dados
    except Exception as e:
        logger.error(f"Erro ao extrair dados MNI: {str(e)}")
        return {'sucesso': False, 'mensagem': f'Erro ao processar dados: {str(e)}'}

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
        logger.debug(f"Consultando processo: {num_processo}")
        resposta = retorna_processo(num_processo)

        # Extrair dados relevantes
        dados = extract_mni_data(resposta)
        logger.debug(f"Dados extraídos: {dados}")

        # Processar hierarquia de documentos
        docs_principais = {}
        docs_vinculados = {}

        if dados['sucesso'] and dados['processo'].get('documentos'):
            for doc in dados['processo']['documentos']:
                doc_id = doc['idDocumento']
                id_vinculado = doc['idDocumentoVinculado']

                if id_vinculado:
                    if id_vinculado not in docs_vinculados:
                        docs_vinculados[id_vinculado] = []
                    docs_vinculados[id_vinculado].append(doc)
                else:
                    docs_principais[doc_id] = doc

        # Adicionar documentos vinculados aos principais
        for doc_id, doc_info in docs_principais.items():
            if doc_id in docs_vinculados:
                doc_info['documentos_vinculados'] = docs_vinculados[doc_id]
            else:
                doc_info['documentos_vinculados'] = []

        return render_template('debug.html', 
                           resposta=dados,
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
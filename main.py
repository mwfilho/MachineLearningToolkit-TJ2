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

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/consultar', methods=['POST'])
def consultar():
    num_processo = request.form.get('num_processo')

    if not num_processo:
        flash('Por favor, insira um número de processo válido.', 'error')
        return render_template('index.html')

    try:
        resposta = retorna_processo(num_processo)
        logger.debug(f"MNI Response: {resposta}")  # Debug log

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
                for doc in resposta.processo.documento:
                    documentos.append({
                        'id': getattr(doc, 'idDocumento', ''),
                        'tipo': getattr(doc, 'tipoDocumento', 'Documento'),
                        'nome': f"Documento {getattr(doc, 'idDocumento', '')}"
                    })

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
        logger.error(f"Erro inesperado: {str(e)}", exc_info=True)  # Full error log
        flash(f'Erro inesperado: {str(e)}', 'error')
        return render_template('index.html')

@app.route('/download_documento/<num_processo>/<num_documento>')
def download_documento(num_processo, num_documento):
    try:
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
        logger.error(f"Erro ao baixar documento: {str(e)}", exc_info=True)  # Full error log
        flash(f'Erro ao baixar documento: {str(e)}', 'error')
        return render_template('index.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
from flask import Flask, render_template, request, jsonify, send_file, flash
import os
from datetime import date
import core
from funcoes_mni import retorna_processo, retorna_documento_processo
import controle.exceptions as exceptions
import logging
import tempfile

app = Flask(__name__)
app.config.from_object('config')

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

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
        if resposta and resposta.sucesso:
            documentos = []
            for doc in resposta.processo.documento:
                documentos.append({
                    'id': doc.idDocumento,
                    'tipo': doc.tipoDocumento,
                    'nome': f"Documento {doc.idDocumento}"
                })
            return render_template('result.html', 
                                processo=resposta.processo,
                                documentos=documentos)
        else:
            flash('Processo não encontrado ou erro na consulta.', 'error')
            return render_template('index.html')
            
    except exceptions.ExcecaoConsultaMNI as e:
        flash(f'Erro na consulta: {str(e)}', 'error')
        return render_template('index.html')
    except Exception as e:
        flash(f'Erro inesperado: {str(e)}', 'error')
        return render_template('index.html')

@app.route('/download_documento/<num_processo>/<num_documento>')
def download_documento(num_processo, num_documento):
    try:
        resposta = retorna_documento_processo(num_processo, num_documento)
        
        if 'msg_erro' in resposta:
            flash(resposta['msg_erro'], 'error')
            return render_template('index.html')
            
        # Create temporary file
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
        flash(f'Erro ao baixar documento: {str(e)}', 'error')
        return render_template('index.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

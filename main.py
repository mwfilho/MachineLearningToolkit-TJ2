from app import app, db
from flask import render_template, request, send_file, flash, redirect, url_for
from flask_login import login_required
import core
from funcoes_mni import retorna_processo, retorna_documento_processo
from controle.exceptions import ExcecaoConsultaMNI
import tempfile
import os
from routes.auth import auth

# Register blueprints
app.register_blueprint(auth, url_prefix='/auth')

@app.route('/')
@login_required
def index():
    return render_template('index.html')

@app.route('/consultar', methods=['POST'])
@login_required
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

    except ExcecaoConsultaMNI as e:
        flash(f'Erro na consulta: {str(e)}', 'error')
        return render_template('index.html')
    except Exception as e:
        flash(f'Erro inesperado: {str(e)}', 'error')
        return render_template('index.html')

@app.route('/download_documento/<num_processo>/<num_documento>')
@login_required
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
        flash(f'Erro ao baixar documento: {str(e)}', 'error')
        return render_template('index.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
from flask import Blueprint, render_template, request, send_file, flash, redirect, url_for
import tempfile
import os
import logging
from funcoes_mni import retorna_processo, retorna_documento_processo, retorna_peticao_inicial_e_anexos
from utils import extract_mni_data, extract_capa_processo
import core

# Configure logging
logger = logging.getLogger(__name__)

web = Blueprint('web', __name__)

@web.route('/')
def index():
    return render_template('index.html')

@web.route('/debug')
def debug():
    return render_template('debug.html')

@web.route('/debug/consulta', methods=['POST'])
def debug_consulta():
    num_processo = request.form.get('num_processo')
    cpf = request.form.get('cpf')
    senha = request.form.get('senha')

    try:
        logger.debug(f"Consultando processo: {num_processo}")
        resposta = retorna_processo(
            num_processo,
            cpf=cpf or os.environ.get('MNI_ID_CONSULTANTE'),
            senha=senha or os.environ.get('MNI_SENHA_CONSULTANTE')
        )

        # Extrair dados relevantes
        dados = extract_mni_data(resposta)
        logger.debug(f"Dados extraídos: {dados}")

        # Processar hierarquia de documentos
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

        # Adicionar links para download com diferentes limites
        download_links = []
        total_docs = len(dados.get('documentos', []))
        
        # Criar links com diferentes limites para download parcial
        if total_docs > 0:
            # Modo rápido (10 documentos)
            download_links.append({
                'url': f"/api/v1/processo/{num_processo}/pdf-completo?rapido=true",
                'texto': f"Download Rápido (máx. 10 documentos)"
            })
            
            # Links com limites proporcionais ao total
            if total_docs > 5:
                download_links.append({
                    'url': f"/api/v1/processo/{num_processo}/pdf-completo?limite=5",
                    'texto': f"Download com 5 documentos"
                })
            
            if total_docs > 10:
                download_links.append({
                    'url': f"/api/v1/processo/{num_processo}/pdf-completo?limite=10",
                    'texto': f"Download com 10 documentos"
                })
                
            if total_docs > 20:
                download_links.append({
                    'url': f"/api/v1/processo/{num_processo}/pdf-completo?limite=20",
                    'texto': f"Download com 20 documentos"
                })
            
            # Download completo
            download_links.append({
                'url': f"/api/v1/processo/{num_processo}/pdf-completo",
                'texto': f"Download Completo (todos os {total_docs} documentos)"
            })

        return render_template('debug.html', 
                           resposta=dados,
                           documentos_hierarquia=docs_principais,
                           num_processo=num_processo,
                           download_links=download_links)  

    except Exception as e:
        logger.error(f"Erro na consulta de debug: {str(e)}", exc_info=True)
        flash(f'Erro na consulta: {str(e)}', 'error')
        return render_template('debug.html')

@web.route('/debug/pdf-completo', methods=['POST'])
def debug_pdf_completo():
    num_processo = request.form.get('num_processo')
    cpf = request.form.get('cpf') or os.environ.get('MNI_ID_CONSULTANTE')
    senha = request.form.get('senha') or os.environ.get('MNI_SENHA_CONSULTANTE')
    
    if not num_processo:
        flash('Número do processo é obrigatório', 'error')
        return render_template('debug.html')
    
    try:
        logger.debug(f"Gerando PDF completo para o processo: {num_processo}")
        
        # Verificar se temos credenciais para usar
        if not cpf or not senha:
            flash('Credenciais MNI não fornecidas. Informe CPF/CNPJ e senha ou configure as variáveis de ambiente.', 'error')
            return render_template('debug.html')
            
        # Obter processo 
        resposta = retorna_processo(num_processo, cpf=cpf, senha=senha)
        dados = extract_mni_data(resposta)
        logger.debug(f"Verificando documentos para o processo {num_processo}")
        
        # Verificar sucesso da consulta
        if not dados.get('sucesso'):
            flash(f'Erro na consulta: {dados.get("mensagem", "Erro desconhecido")}', 'error')
            return render_template('debug.html')
            
        # Verificar se há documentos (agora usando o novo formato)
        if not dados.get('documentos') or len(dados.get('documentos', [])) == 0:
            # Mostrar quantos documentos foram encontrados nos logs
            docs_originais = dados.get('processo', {}).get('documentos', [])
            logger.debug(f"Documentos no formato original: {len(docs_originais)}")
            
            flash('O processo não tem documentos disponíveis ou você não tem permissão para acessá-los.', 'error')
            return render_template('debug.html')
            
        # Para permitir download direto, definimos headers customizados para API
        os.environ['MNI_ID_CONSULTANTE'] = cpf
        os.environ['MNI_SENHA_CONSULTANTE'] = senha
            
        # Redirecionar para o endpoint da API com os parâmetros necessários
        logger.debug(f"Redirecionando para API com {len(dados.get('documentos', []))} documentos encontrados")
        return redirect(url_for('api.gerar_pdf_completo', num_processo=num_processo))
        
    except Exception as e:
        logger.error(f"Erro ao gerar PDF completo: {str(e)}", exc_info=True)
        flash(f'Erro ao gerar PDF completo: {str(e)}', 'error')
        return render_template('debug.html')


@web.route('/debug/documento', methods=['POST'])
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

@web.route('/debug/capa', methods=['POST'])
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

from flask import Blueprint, render_template, request, send_file, flash, jsonify
import tempfile
import os
import logging
from datetime import datetime
from funcoes_mni import retorna_processo, retorna_documento_processo, retorna_peticao_inicial_e_anexos
from utils import extract_mni_data
import core
from pdf_utils import create_empty_pdf

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

        return render_template('debug.html', 
                           resposta=dados,
                           documentos_hierarquia=docs_principais,
                           num_processo=num_processo)  

    except Exception as e:
        logger.error(f"Erro na consulta de debug: {str(e)}", exc_info=True)
        flash(f'Erro na consulta: {str(e)}', 'error')
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
        return render_template('debug.html', resposta=doc_info, num_processo=num_processo, documento_consultado=id_documento)

    except Exception as e:
        logger.error(f"Erro na consulta do documento: {str(e)}", exc_info=True)
        flash(f'Erro na consulta do documento: {str(e)}', 'error')
        return render_template('debug.html')

@web.route('/download_documento/<num_processo>/<num_documento>')
def download_documento(num_processo, num_documento):
    try:
        logger.debug(f"Baixando documento {num_documento} do processo {num_processo}")
        
        # Verificar e formatar o número do processo
        try:
            # Tentamos formatar o número do processo
            num_processo_formatado = core.format_process_number(num_processo)
            logger.debug(f"Número do processo formatado: {num_processo_formatado}")
        except ValueError as e:
            # Se falhar na formatação, enviamos um erro amigável
            logger.error(f"Erro na formatação do número do processo: {str(e)}")
            flash(f"Número de processo inválido: {num_processo}. Use o formato CNJ completo: NNNNNNN-DD.AAAA.J.TR.OOOO", "error")
            return render_template('index.html')
            
        # Obter credenciais do formulário, se disponíveis
        cpf = request.args.get('cpf') or os.environ.get('MNI_ID_CONSULTANTE')
        senha = request.args.get('senha') or os.environ.get('MNI_SENHA_CONSULTANTE')
        
        resposta = retorna_documento_processo(num_processo_formatado, num_documento, cpf=cpf, senha=senha)

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

@web.route('/download_peticao_inicial/<num_processo>')
def download_peticao_inicial(num_processo):
    """
    Faz download da petição inicial e seus anexos como um único PDF
    """
    try:
        logger.debug(f"Baixando petição inicial do processo {num_processo}")
        
        # Verificar e formatar o número do processo
        try:
            # Tentamos formatar o número do processo
            num_processo_formatado = core.format_process_number(num_processo)
            logger.debug(f"Número do processo formatado: {num_processo_formatado}")
        except ValueError as e:
            # Se falhar na formatação, enviamos um erro amigável
            logger.error(f"Erro na formatação do número do processo: {str(e)}")
            flash(f"Número de processo inválido: {num_processo}. Use o formato CNJ completo: NNNNNNN-DD.AAAA.J.TR.OOOO", "error")
            return render_template('index.html')
            
        # Obter credenciais do formulário, se disponíveis
        cpf = request.args.get('cpf') or os.environ.get('MNI_ID_CONSULTANTE')
        senha = request.args.get('senha') or os.environ.get('MNI_SENHA_CONSULTANTE')
        
        # Buscar info da petição inicial
        resposta = retorna_peticao_inicial_e_anexos(num_processo_formatado, cpf=cpf, senha=senha)

        if 'msg_erro' in resposta:
            flash(resposta['msg_erro'], 'error')
            return render_template('index.html')

        if not resposta.get('peticao_inicial'):
            flash("Petição inicial não encontrada para este processo", 'warning')
            return render_template('index.html')

        # Obter o ID da petição inicial
        peticao = resposta['peticao_inicial']
        id_documento = peticao['id_documento']
        
        logger.debug(f"ID da Petição Inicial encontrado: {id_documento}")
        
        # Usamos o método de gerar PDF com anexos para a petição inicial
        pdf_resposta = core.generate_document_with_attachments_pdf(
            num_processo_formatado, 
            id_documento, 
            cpf=cpf, 
            senha=senha
        )
        
        # Verificar se houve erro
        if not pdf_resposta.get('sucesso', False):
            flash(pdf_resposta.get('msg_erro', 'Erro ao gerar PDF da petição inicial'), 'error')
            return render_template('index.html')
        
        # Se tiver algum aviso, reportamos ao usuário
        if 'aviso' in pdf_resposta:
            flash(f"Aviso: {pdf_resposta['aviso']}", 'warning')
        
        # Preparar o download
        data_atual = datetime.now().strftime("%Y%m%d_%H%M%S")
        temp_dir = tempfile.mkdtemp()
        file_path = os.path.join(temp_dir, f'peticao_inicial_{num_processo}_{data_atual}.pdf')
        
        # Gravar o PDF em disco
        with open(file_path, 'wb') as f:
            f.write(pdf_resposta['pdf_content'])
        
        # Informar quantos anexos foram incluídos
        total_docs = pdf_resposta.get('total_documentos', 0)
        if total_docs > 1:
            flash(f"Petição inicial mesclada com {total_docs-1} anexo(s)", 'success')
        
        # Retornar o arquivo para download
        return send_file(
            file_path,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f'peticao_inicial_{num_processo}_completa.pdf'
        )

    except Exception as e:
        logger.error(f"Erro ao baixar petição inicial: {str(e)}", exc_info=True)
        
        try:
            # Tentar criar um PDF vazio com a mensagem de erro
            pdf_content = create_empty_pdf(f"Erro ao gerar PDF da petição inicial: {str(e)}")
            
            # Criar arquivo temporário para download
            temp_dir = tempfile.mkdtemp()
            file_path = os.path.join(temp_dir, f'erro_peticao_{num_processo}.pdf')
            
            # Gravar o PDF em disco
            with open(file_path, 'wb') as f:
                f.write(pdf_content)
            
            flash("Ocorreu um erro ao gerar o PDF da petição inicial. Um documento vazio foi gerado.", 'error')
            
            # Retornar o arquivo para download
            return send_file(
                file_path,
                mimetype='application/pdf',
                as_attachment=True,
                download_name=f'erro_peticao_{num_processo}.pdf'
            )
        except:
            flash(f'Erro ao gerar PDF da petição inicial: {str(e)}', 'error')
            return render_template('index.html')
        
@web.route('/download_documento_com_anexos/<num_processo>/<num_documento>')
def download_documento_com_anexos(num_processo, num_documento):
    """
    Gera e faz download de um PDF contendo um documento específico e seus anexos
    """
    try:
        logger.debug(f"Web: Gerando PDF do documento {num_documento} com anexos - Processo {num_processo}")
        
        # Verificar e formatar o número do processo
        try:
            # Tentamos formatar o número do processo
            num_processo_formatado = core.format_process_number(num_processo)
            logger.debug(f"Número do processo formatado: {num_processo_formatado}")
        except ValueError as e:
            # Se falhar na formatação, enviamos um erro amigável
            logger.error(f"Erro na formatação do número do processo: {str(e)}")
            flash(f"Número de processo inválido: {num_processo}. Use o formato CNJ completo: NNNNNNN-DD.AAAA.J.TR.OOOO", "error")
            return render_template('index.html')
        
        # Obter credenciais do formulário, se disponíveis
        cpf = request.args.get('cpf') or os.environ.get('MNI_ID_CONSULTANTE')
        senha = request.args.get('senha') or os.environ.get('MNI_SENHA_CONSULTANTE')
        
        # Gerar o PDF do documento e seus anexos
        resposta = core.generate_document_with_attachments_pdf(num_processo_formatado, num_documento, cpf=cpf, senha=senha)
        
        # Verificar se houve erro
        if not resposta.get('sucesso', False):
            flash(resposta.get('msg_erro', 'Erro desconhecido ao gerar PDF'), 'error')
            return render_template('index.html')
        
        # Se tiver algum aviso, reportamos ao usuário
        if 'aviso' in resposta:
            flash(f"Aviso: {resposta['aviso']}", 'warning')
        
        # Criar arquivo temporário para download
        data_atual = datetime.now().strftime("%Y%m%d_%H%M%S")
        temp_dir = tempfile.mkdtemp()
        file_path = os.path.join(temp_dir, f'documento_{num_documento}_{data_atual}.pdf')
        
        # Gravar o PDF em disco
        with open(file_path, 'wb') as f:
            f.write(resposta['pdf_content'])
        
        # Retornar o arquivo para download
        return send_file(
            file_path,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f'documento_{num_documento}_com_anexos.pdf'
        )
        
    except Exception as e:
        logger.error(f"Erro ao gerar PDF do documento com anexos: {str(e)}", exc_info=True)
        
        try:
            # Criar PDF vazio com mensagem de erro
            pdf_content = create_empty_pdf(f"Erro ao gerar PDF: {str(e)}")
            
            # Criar arquivo temporário para download
            temp_dir = tempfile.mkdtemp()
            file_path = os.path.join(temp_dir, f'erro_documento_{num_documento}.pdf')
            
            # Gravar o PDF em disco
            with open(file_path, 'wb') as f:
                f.write(pdf_content)
            
            flash("Ocorreu um erro ao gerar o PDF do documento com anexos. Um documento vazio foi gerado.", 'error')
            
            # Retornar o arquivo para download
            return send_file(
                file_path,
                mimetype='application/pdf',
                as_attachment=True,
                download_name=f'erro_documento_{num_documento}.pdf'
            )
        except:
            flash(f'Erro ao gerar PDF do documento com anexos: {str(e)}', 'error')
            return render_template('index.html')

@web.route('/download_processo_completo/<num_processo>')
def download_processo_completo(num_processo):
    """
    Gera e faz download de um PDF completo contendo todos os documentos do processo
    """
    try:
        logger.debug(f"Web: Gerando PDF completo do processo {num_processo}")
        
        # Verificar e formatar o número do processo
        try:
            # Tentamos formatar o número do processo
            num_processo_formatado = core.format_process_number(num_processo)
            logger.debug(f"Número do processo formatado: {num_processo_formatado}")
        except ValueError as e:
            # Se falhar na formatação, enviamos um erro amigável
            logger.error(f"Erro na formatação do número do processo: {str(e)}")
            flash(f"Número de processo inválido: {num_processo}. Use o formato CNJ completo: NNNNNNN-DD.AAAA.J.TR.OOOO", "error")
            return render_template('index.html')
        
        # Obter credenciais do formulário, se disponíveis
        cpf = request.args.get('cpf') or os.environ.get('MNI_ID_CONSULTANTE')
        senha = request.args.get('senha') or os.environ.get('MNI_SENHA_CONSULTANTE')
        
        # Gerar o PDF completo com o número de processo formatado
        resposta = core.generate_complete_process_pdf(num_processo_formatado, cpf=cpf, senha=senha)

        # Verificar se houve erro
        if not resposta.get('sucesso', False):
            flash(resposta.get('msg_erro', 'Erro desconhecido ao gerar PDF'), 'error')
            return render_template('index.html')

        # Se tiver algum aviso, reportamos ao usuário
        if 'aviso' in resposta:
            flash(f"Aviso: {resposta['aviso']}", 'warning')

        # Criar arquivo temporário para download
        data_atual = datetime.now().strftime("%Y%m%d_%H%M%S")
        temp_dir = tempfile.mkdtemp()
        file_path = os.path.join(temp_dir, f'processo_{num_processo}_{data_atual}.pdf')

        # Gravar o PDF em disco
        with open(file_path, 'wb') as f:
            f.write(resposta['pdf_content'])

        # Retornar o arquivo para download
        return send_file(
            file_path,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f'processo_{num_processo}_completo.pdf'
        )

    except Exception as e:
        logger.error(f"Erro ao gerar PDF completo: {str(e)}", exc_info=True)
        
        try:
            # Criar PDF vazio com mensagem de erro
            pdf_content = create_empty_pdf(f"Erro ao gerar PDF: {str(e)}")
            
            # Criar arquivo temporário para download
            temp_dir = tempfile.mkdtemp()
            file_path = os.path.join(temp_dir, f'erro_processo_{num_processo}.pdf')
            
            # Gravar o PDF em disco
            with open(file_path, 'wb') as f:
                f.write(pdf_content)
            
            flash("Ocorreu um erro ao gerar o PDF completo. Um documento vazio foi gerado.", 'error')
            
            # Retornar o arquivo para download
            return send_file(
                file_path,
                mimetype='application/pdf',
                as_attachment=True,
                download_name=f'erro_processo_{num_processo}.pdf'
            )
        except:
            flash(f'Erro ao gerar PDF completo: {str(e)}', 'error')
            return render_template('index.html')

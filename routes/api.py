from flask import Blueprint, jsonify, send_file, request
import os
import logging
from funcoes_mni import retorna_processo, retorna_documento_processo, retorna_peticao_inicial_e_anexos
from utils import extract_mni_data
import core
import tempfile
import io
from PyPDF2 import PdfMerger, PdfReader, PdfWriter
import pdfkit
import shutil
from datetime import datetime

# Configure logging
logger = logging.getLogger(__name__)

# Criar o blueprint da API
api = Blueprint('api', __name__, url_prefix='/api/v1')

def get_mni_credentials():
    """Obtém credenciais do MNI dos headers ou environment"""
    cpf = request.headers.get('X-MNI-CPF') or os.environ.get('MNI_ID_CONSULTANTE')
    senha = request.headers.get('X-MNI-SENHA') or os.environ.get('MNI_SENHA_CONSULTANTE')
    return cpf, senha

@api.before_request
def log_request_info():
    """Log detalhes da requisição para debug"""
    logger.debug('Headers: %s', dict(request.headers))
    logger.debug('Body: %s', request.get_data())
    logger.debug('URL: %s', request.url)

@api.route('/processo/<num_processo>', methods=['GET'])
def get_processo(num_processo):
    """
    Retorna os dados do processo incluindo lista de documentos
    """
    try:
        logger.debug(f"API: Consultando processo {num_processo}")
        cpf, senha = get_mni_credentials()

        if not cpf or not senha:
            return jsonify({
                'erro': 'Credenciais MNI não fornecidas',
                'mensagem': 'Forneça as credenciais nos headers X-MNI-CPF e X-MNI-SENHA'
            }), 401

        resposta = retorna_processo(num_processo, cpf=cpf, senha=senha)

        # Extrair dados relevantes
        dados = extract_mni_data(resposta)
        return jsonify(dados)

    except Exception as e:
        logger.error(f"API: Erro ao consultar processo: {str(e)}", exc_info=True)
        return jsonify({
            'erro': str(e),
            'mensagem': 'Erro ao consultar processo'
        }), 500

@api.route('/processo/<num_processo>/documento/<num_documento>', methods=['GET'])
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
        
@api.route('/processo/<num_processo>/peticao-inicial/pdf', methods=['GET'])
def download_peticao_inicial_com_anexos_pdf(num_processo):
    """
    Retorna um único arquivo PDF contendo a petição inicial e seus anexos
    """
    try:
        logger.debug(f"API: Gerando PDF único com petição inicial e anexos do processo {num_processo}")
        cpf, senha = get_mni_credentials()

        if not cpf or not senha:
            return jsonify({
                'erro': 'Credenciais MNI não fornecidas',
                'mensagem': 'Forneça as credenciais nos headers X-MNI-CPF e X-MNI-SENHA'
            }), 401

        # 1. Obter informações da petição inicial e anexos
        resposta = retorna_peticao_inicial_e_anexos(num_processo, cpf=cpf, senha=senha)

        if 'msg_erro' in resposta:
            return jsonify({
                'erro': resposta['msg_erro'],
                'mensagem': 'Erro ao buscar petição inicial e anexos'
            }), 404

        # Verificar se existe petição inicial
        if not resposta.get('peticao_inicial'):
            return jsonify({
                'erro': 'Petição inicial não encontrada',
                'mensagem': 'Não foi possível identificar a petição inicial no processo'
            }), 404

        # 2. Criar diretório temporário para armazenar arquivos
        temp_dir = tempfile.mkdtemp()
        pdf_files = []  # Lista para armazenar caminhos dos arquivos PDFs
        
        try:
            # 3. Baixar e processar a petição inicial
            peticao_id = resposta['peticao_inicial']['id_documento']
            peticao_doc = retorna_documento_processo(num_processo, peticao_id, cpf=cpf, senha=senha)
            
            if 'msg_erro' in peticao_doc:
                raise Exception(f"Erro ao baixar petição inicial: {peticao_doc['msg_erro']}")
            
            peticao_mimetype = peticao_doc['mimetype']
            peticao_conteudo = peticao_doc['conteudo']
            
            # Converter HTML para PDF se for o caso
            if peticao_mimetype == 'text/html':
                peticao_path = os.path.join(temp_dir, 'peticao_inicial.pdf')
                
                # Salvar o HTML em um arquivo temporário
                html_path = os.path.join(temp_dir, 'peticao_inicial.html')
                with open(html_path, 'wb') as f:
                    f.write(peticao_conteudo)
                
                # Converter HTML para PDF
                pdf_options = {
                    'encoding': 'UTF-8',
                    'page-size': 'A4',
                    'margin-top': '10mm',
                    'margin-right': '10mm',
                    'margin-bottom': '10mm',
                    'margin-left': '10mm'
                }
                try:
                    pdfkit.from_file(html_path, peticao_path, options=pdf_options)
                    pdf_files.append(peticao_path)
                except Exception as e:
                    logger.error(f"Erro ao converter HTML para PDF: {str(e)}", exc_info=True)
                    # Alternativa: mostrar mensagem de erro no PDF
                    error_html = f"<html><body><h1>Erro ao converter petição inicial</h1><p>{str(e)}</p></body></html>"
                    with open(html_path, 'w', encoding='utf-8') as f:
                        f.write(error_html)
                    pdfkit.from_string(error_html, peticao_path, options=pdf_options)
                    pdf_files.append(peticao_path)
            else:
                # Se já for PDF, salvar diretamente
                if peticao_mimetype == 'application/pdf':
                    peticao_path = os.path.join(temp_dir, 'peticao_inicial.pdf')
                    with open(peticao_path, 'wb') as f:
                        f.write(peticao_conteudo)
                    pdf_files.append(peticao_path)
                else:
                    # Se for outro tipo, criar um PDF informando isso
                    error_html = f"<html><body><h1>Tipo de documento não suportado</h1><p>A petição inicial está no formato {peticao_mimetype} que não pode ser convertido para PDF.</p></body></html>"
                    peticao_path = os.path.join(temp_dir, 'peticao_inicial.pdf')
                    pdf_options = {
                        'encoding': 'UTF-8',
                        'page-size': 'A4'
                    }
                    pdfkit.from_string(error_html, peticao_path, options=pdf_options)
                    pdf_files.append(peticao_path)
            
            # 4. Baixar e processar anexos
            for i, anexo in enumerate(resposta.get('anexos', [])):
                anexo_id = anexo['id_documento']
                anexo_doc = retorna_documento_processo(num_processo, anexo_id, cpf=cpf, senha=senha)
                
                if 'msg_erro' in anexo_doc:
                    logger.warning(f"Erro ao baixar anexo {anexo_id}: {anexo_doc['msg_erro']}")
                    # Criar um PDF com a mensagem de erro
                    error_html = f"<html><body><h1>Erro ao baixar anexo {i+1}</h1><p>{anexo_doc['msg_erro']}</p></body></html>"
                    anexo_path = os.path.join(temp_dir, f'anexo_{i+1}_error.pdf')
                    pdfkit.from_string(error_html, anexo_path)
                    pdf_files.append(anexo_path)
                    continue
                
                anexo_mimetype = anexo_doc['mimetype']
                anexo_conteudo = anexo_doc['conteudo']
                
                # Processar o anexo dependendo do tipo
                if anexo_mimetype == 'application/pdf':
                    # Se já for PDF, salvar diretamente
                    anexo_path = os.path.join(temp_dir, f'anexo_{i+1}.pdf')
                    with open(anexo_path, 'wb') as f:
                        f.write(anexo_conteudo)
                    pdf_files.append(anexo_path)
                elif anexo_mimetype == 'text/html':
                    # Converter HTML para PDF
                    html_path = os.path.join(temp_dir, f'anexo_{i+1}.html')
                    with open(html_path, 'wb') as f:
                        f.write(anexo_conteudo)
                    
                    anexo_path = os.path.join(temp_dir, f'anexo_{i+1}.pdf')
                    try:
                        # Always use a fresh copy of options for PDF conversion
                        pdf_options = {
                            'encoding': 'UTF-8',
                            'page-size': 'A4',
                            'margin-top': '10mm',
                            'margin-right': '10mm',
                            'margin-bottom': '10mm',
                            'margin-left': '10mm'
                        }
                        pdfkit.from_file(html_path, anexo_path, options=pdf_options)
                        pdf_files.append(anexo_path)
                    except Exception as e:
                        logger.error(f"Erro ao converter anexo HTML para PDF: {str(e)}", exc_info=True)
                        error_html = f"<html><body><h1>Erro ao converter anexo {i+1}</h1><p>{str(e)}</p></body></html>"
                        pdf_options = {
                            'encoding': 'UTF-8',
                            'page-size': 'A4'
                        }
                        pdfkit.from_string(error_html, anexo_path, options=pdf_options)
                        pdf_files.append(anexo_path)
                else:
                    # Para outros tipos, criar PDF informativo
                    error_html = f"<html><body><h1>Anexo {i+1} em formato não suportado</h1><p>O anexo está no formato {anexo_mimetype} que não pode ser convertido para PDF.</p></body></html>"
                    anexo_path = os.path.join(temp_dir, f'anexo_{i+1}_nao_suportado.pdf')
                    pdf_options = {
                        'encoding': 'UTF-8',
                        'page-size': 'A4'
                    }
                    pdfkit.from_string(error_html, anexo_path, options=pdf_options)
                    pdf_files.append(anexo_path)
            
            # 5. Mesclar todos os PDFs em um único arquivo
            merger = PdfMerger()
            
            for pdf_file in pdf_files:
                try:
                    merger.append(pdf_file)
                except Exception as e:
                    logger.error(f"Erro ao mesclar PDF {pdf_file}: {str(e)}", exc_info=True)
                    # Criar um PDF com a mensagem de erro e adicionar
                    error_html = f"<html><body><h1>Erro ao mesclar arquivo</h1><p>{str(e)}</p></body></html>"
                    error_path = os.path.join(temp_dir, 'erro_mesclagem.pdf')
                    pdf_options = {
                        'encoding': 'UTF-8',
                        'page-size': 'A4'
                    }
                    pdfkit.from_string(error_html, error_path, options=pdf_options)
                    try:
                        merger.append(error_path)
                    except Exception:
                        pass
            
            # Salvar o PDF mesclado
            output_path = os.path.join(temp_dir, f'processo_{num_processo}_completo.pdf')
            merger.write(output_path)
            merger.close()
            
            # 6. Retornar o arquivo para download
            return send_file(
                output_path,
                mimetype='application/pdf',
                as_attachment=True,
                download_name=f'processo_{num_processo}_completo.pdf'
            )
            
        finally:
            # Garantir limpeza dos arquivos temporários
            # Os arquivos serão removidos automaticamente quando o request terminar
            pass

    except Exception as e:
        logger.error(f"API: Erro ao gerar PDF único: {str(e)}", exc_info=True)
        return jsonify({
            'erro': str(e),
            'mensagem': 'Erro ao gerar PDF único com petição inicial e anexos'
        }), 500
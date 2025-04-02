from flask import Blueprint, jsonify, send_file, request
import os
import logging
from funcoes_mni import retorna_processo, retorna_documento_processo, retorna_peticao_inicial_e_anexos
from utils import extract_mni_data
import core
import tempfile
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
        
        # Verificar e formatar o número do processo
        try:
            # Tentamos formatar o número do processo
            num_processo_formatado = core.format_process_number(num_processo)
            logger.debug(f"Número do processo formatado: {num_processo_formatado}")
        except ValueError as e:
            # Se falhar na formatação, retornamos um erro
            logger.error(f"Erro na formatação do número do processo: {str(e)}")
            return jsonify({
                'erro': f"Número de processo inválido: {num_processo}",
                'mensagem': f"Formato CNJ requerido: NNNNNNN-DD.AAAA.J.TR.OOOO. Erro: {str(e)}"
            }), 400
            
        cpf, senha = get_mni_credentials()

        if not cpf or not senha:
            return jsonify({
                'erro': 'Credenciais MNI não fornecidas',
                'mensagem': 'Forneça as credenciais nos headers X-MNI-CPF e X-MNI-SENHA'
            }), 401

        resposta = retorna_processo(num_processo_formatado, cpf=cpf, senha=senha)

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
        
        # Verificar e formatar o número do processo
        try:
            # Tentamos formatar o número do processo
            num_processo_formatado = core.format_process_number(num_processo)
            logger.debug(f"Número do processo formatado: {num_processo_formatado}")
        except ValueError as e:
            # Se falhar na formatação, retornamos um erro
            logger.error(f"Erro na formatação do número do processo: {str(e)}")
            return jsonify({
                'erro': f"Número de processo inválido: {num_processo}",
                'mensagem': f"Formato CNJ requerido: NNNNNNN-DD.AAAA.J.TR.OOOO. Erro: {str(e)}"
            }), 400
        
        cpf, senha = get_mni_credentials()

        if not cpf or not senha:
            return jsonify({
                'erro': 'Credenciais MNI não fornecidas',
                'mensagem': 'Forneça as credenciais nos headers X-MNI-CPF e X-MNI-SENHA'
            }), 401

        resposta = retorna_documento_processo(num_processo_formatado, num_documento, cpf=cpf, senha=senha)

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
    Retorna dados da petição inicial e seus anexos ou o PDF completo
    Se parâmetro format=json -> Retorna dados JSON
    Se parâmetro format=pdf -> Retorna PDF da petição com anexos (padrão)
    """
    try:
        # Verificar se quer dados JSON ou PDF (padrão)
        format_param = request.args.get('format', 'pdf').lower()
        
        logger.debug(f"API: Buscando petição inicial do processo {num_processo} (format={format_param})")
        
        # Verificar e formatar o número do processo
        try:
            # Tentamos formatar o número do processo
            num_processo_formatado = core.format_process_number(num_processo)
            logger.debug(f"Número do processo formatado: {num_processo_formatado}")
        except ValueError as e:
            # Se falhar na formatação, retornamos um erro
            logger.error(f"Erro na formatação do número do processo: {str(e)}")
            return jsonify({
                'erro': f"Número de processo inválido: {num_processo}",
                'mensagem': f"Formato CNJ requerido: NNNNNNN-DD.AAAA.J.TR.OOOO. Erro: {str(e)}"
            }), 400
            
        cpf, senha = get_mni_credentials()

        if not cpf or not senha:
            return jsonify({
                'erro': 'Credenciais MNI não fornecidas',
                'mensagem': 'Forneça as credenciais nos headers X-MNI-CPF e X-MNI-SENHA'
            }), 401

        # Buscar informações da petição inicial
        resposta = retorna_peticao_inicial_e_anexos(num_processo_formatado, cpf=cpf, senha=senha)

        if 'msg_erro' in resposta:
            return jsonify({
                'erro': resposta['msg_erro'],
                'mensagem': 'Erro ao buscar petição inicial'
            }), 404
            
        # Se não encontrou petição inicial
        if not resposta.get('peticao_inicial'):
            return jsonify({
                'erro': 'Petição inicial não encontrada',
                'mensagem': 'Este processo não possui petição inicial acessível'
            }), 404
        
        # Se quiser apenas os dados JSON
        if format_param == 'json':
            return jsonify(resposta)
            
        # Caso contrário, gera o PDF (padrão)
        # Obter o ID da petição inicial
        peticao = resposta['peticao_inicial']
        id_documento = peticao['id_documento']
        
        logger.debug(f"API: Gerando PDF da petição inicial {id_documento} e anexos")
        
        # Gerar o PDF da petição inicial com seus anexos
        pdf_resposta = core.generate_document_with_attachments_pdf(
            num_processo_formatado, 
            id_documento, 
            cpf=cpf, 
            senha=senha
        )
        
        # Verificar se houve erro
        if not pdf_resposta.get('sucesso', False):
            return jsonify({
                'erro': pdf_resposta.get('msg_erro', 'Erro desconhecido'),
                'mensagem': 'Erro ao gerar PDF da petição inicial'
            }), 500
        
        # Se tiver algum aviso, adicionamos aos logs
        if 'aviso' in pdf_resposta:
            logger.warning(f"Aviso ao gerar PDF da petição: {pdf_resposta['aviso']}")
        
        # Criar arquivo temporário para download
        data_atual = datetime.now().strftime("%Y%m%d_%H%M%S")
        temp_dir = tempfile.mkdtemp()
        file_path = os.path.join(temp_dir, f'peticao_inicial_{num_processo}_{data_atual}.pdf')
        
        # Gravar o PDF em disco
        with open(file_path, 'wb') as f:
            f.write(pdf_resposta['pdf_content'])
        
        # Retornar o arquivo para download
        return send_file(
            file_path,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f'peticao_inicial_{num_processo}_completa.pdf'
        )

    except Exception as e:
        logger.error(f"API: Erro ao buscar petição inicial: {str(e)}", exc_info=True)
        
        # Se a exceção for durante o processamento do PDF, tentamos retornar um PDF vazio
        if 'pdf' in request.args.get('format', 'pdf').lower():
            try:
                from pdf_utils import create_empty_pdf
                
                # Criar PDF vazio com mensagem de erro
                pdf_content = create_empty_pdf(f"Erro ao gerar PDF da petição inicial: {str(e)}")
                
                # Criar arquivo temporário para download
                data_atual = datetime.now().strftime("%Y%m%d_%H%M%S")
                temp_dir = tempfile.mkdtemp()
                file_path = os.path.join(temp_dir, f'erro_peticao_{num_processo}_{data_atual}.pdf')
                
                # Gravar o PDF em disco
                with open(file_path, 'wb') as f:
                    f.write(pdf_content)
                
                # Retornar o arquivo para download
                return send_file(
                    file_path,
                    mimetype='application/pdf',
                    as_attachment=True,
                    download_name=f'erro_peticao_{num_processo}.pdf'
                )
            except:
                pass
                
        # Se tudo falhar ou estivermos em modo JSON, retorna erro JSON
        return jsonify({
            'erro': str(e),
            'mensagem': 'Erro ao processar petição inicial'
        }), 500
        
@api.route('/processo/<num_processo>/documento/<num_documento>/pdf-completo', methods=['GET'])
def get_documento_com_anexos_pdf(num_processo, num_documento):
    """
    Gera e faz download de um PDF de um documento específico com seus anexos
    """
    try:
        logger.debug(f"API: Gerando PDF do documento {num_documento} com anexos - Processo {num_processo}")
        
        # Verificar e formatar o número do processo
        try:
            # Tentamos formatar o número do processo
            num_processo_formatado = core.format_process_number(num_processo)
            logger.debug(f"Número do processo formatado: {num_processo_formatado}")
        except ValueError as e:
            # Se falhar na formatação, retornamos um erro
            logger.error(f"Erro na formatação do número do processo: {str(e)}")
            return jsonify({
                'erro': f"Número de processo inválido: {num_processo}",
                'mensagem': f"Formato CNJ requerido: NNNNNNN-DD.AAAA.J.TR.OOOO. Erro: {str(e)}"
            }), 400
            
        cpf, senha = get_mni_credentials()
        
        # Gerar o PDF do documento e seus anexos
        resposta = core.generate_document_with_attachments_pdf(num_processo_formatado, num_documento, cpf=cpf, senha=senha)
        
        # Verificar se houve erro
        if not resposta.get('sucesso', False):
            return jsonify({
                'erro': resposta.get('msg_erro', 'Erro desconhecido'),
                'mensagem': 'Erro ao gerar PDF do documento com anexos'
            }), 500
        
        # Se tiver algum aviso, adicionamos aos logs
        if 'aviso' in resposta:
            logger.warning(f"Aviso ao gerar PDF: {resposta['aviso']}")
        
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
        logger.error(f"API: Erro ao gerar PDF do documento com anexos: {str(e)}", exc_info=True)
        
        # Mesmo com erro, tentamos retornar um PDF vazio
        try:
            from pdf_utils import create_empty_pdf
            
            # Criar PDF vazio com mensagem de erro
            pdf_content = create_empty_pdf(f"Erro ao gerar PDF: {str(e)}")
            
            # Criar arquivo temporário para download
            data_atual = datetime.now().strftime("%Y%m%d_%H%M%S")
            temp_dir = tempfile.mkdtemp()
            file_path = os.path.join(temp_dir, f'erro_documento_{num_documento}_{data_atual}.pdf')
            
            # Gravar o PDF em disco
            with open(file_path, 'wb') as f:
                f.write(pdf_content)
            
            # Retornar o arquivo para download
            return send_file(
                file_path,
                mimetype='application/pdf',
                as_attachment=True,
                download_name=f'erro_documento_{num_documento}.pdf'
            )
        except:
            # Se falhar até a criação do PDF vazio, aí sim retornamos erro JSON
            return jsonify({
                'erro': str(e),
                'mensagem': 'Erro ao gerar PDF do documento com anexos'
            }), 500

@api.route('/processo/<num_processo>/pdf-completo', methods=['GET'])
def get_processo_completo_pdf(num_processo):
    """
    Gera e faz download de um PDF completo contendo todos os documentos do processo
    """
    try:
        logger.debug(f"API: Gerando PDF completo do processo {num_processo}")
        
        # Verificar e formatar o número do processo
        try:
            # Tentamos formatar o número do processo
            num_processo_formatado = core.format_process_number(num_processo)
            logger.debug(f"Número do processo formatado: {num_processo_formatado}")
        except ValueError as e:
            # Se falhar na formatação, retornamos um erro
            logger.error(f"Erro na formatação do número do processo: {str(e)}")
            return jsonify({
                'erro': f"Número de processo inválido: {num_processo}",
                'mensagem': f"Formato CNJ requerido: NNNNNNN-DD.AAAA.J.TR.OOOO. Erro: {str(e)}"
            }), 400
            
        cpf, senha = get_mni_credentials()

        # A validação não é necessária aqui, pois a função generate_complete_process_pdf
        # pode usar as credenciais de ambiente como fallback
        
        # Gerar o PDF completo com o número formatado
        resposta = core.generate_complete_process_pdf(num_processo_formatado, cpf=cpf, senha=senha)

        # Verificar se houve erro
        if not resposta.get('sucesso', False):
            return jsonify({
                'erro': resposta.get('msg_erro', 'Erro desconhecido'),
                'mensagem': 'Erro ao gerar PDF completo do processo'
            }), 500

        # Se tiver algum aviso, adicionamos aos logs
        if 'aviso' in resposta:
            logger.warning(f"Aviso ao gerar PDF: {resposta['aviso']}")

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
        logger.error(f"API: Erro ao gerar PDF completo: {str(e)}", exc_info=True)
        
        # Mesmo com erro, tentamos retornar um PDF vazio
        try:
            from pdf_utils import create_empty_pdf
            
            # Criar PDF vazio com mensagem de erro
            pdf_content = create_empty_pdf(f"Erro ao gerar PDF: {str(e)}")
            
            # Criar arquivo temporário para download
            data_atual = datetime.now().strftime("%Y%m%d_%H%M%S")
            temp_dir = tempfile.mkdtemp()
            file_path = os.path.join(temp_dir, f'processo_{num_processo}_{data_atual}_erro.pdf')
            
            # Gravar o PDF em disco
            with open(file_path, 'wb') as f:
                f.write(pdf_content)
            
            # Retornar o arquivo para download
            return send_file(
                file_path,
                mimetype='application/pdf',
                as_attachment=True,
                download_name=f'processo_{num_processo}_erro.pdf'
            )
        except:
            # Se falhar até a criação do PDF vazio, aí sim retornamos erro JSON
            return jsonify({
                'erro': str(e),
                'mensagem': 'Erro ao gerar PDF completo do processo'
            }), 500
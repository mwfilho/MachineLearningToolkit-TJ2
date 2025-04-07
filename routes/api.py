from flask import Blueprint, jsonify, send_file, request
import os
import logging
from funcoes_mni import retorna_processo, retorna_documento_processo, retorna_peticao_inicial_e_anexos
from utils import extract_mni_data, extract_capa_processo
import core
import tempfile
import time
import io
import concurrent.futures

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
        
@api.route('/processo/<num_processo>/capa', methods=['GET'])
def get_capa_processo(num_processo):
    """
    Retorna apenas os dados da capa do processo (sem documentos),
    incluindo dados básicos, assuntos, polos e movimentações
    """
    try:
        logger.debug(f"API: Consultando capa do processo {num_processo}")
        cpf, senha = get_mni_credentials()

        if not cpf or not senha:
            return jsonify({
                'erro': 'Credenciais MNI não fornecidas',
                'mensagem': 'Forneça as credenciais nos headers X-MNI-CPF e X-MNI-SENHA'
            }), 401

        # Usando o parâmetro incluir_documentos=False para melhor performance
        resposta = retorna_processo(num_processo, cpf=cpf, senha=senha, incluir_documentos=False)

        # Extrair apenas os dados da capa do processo
        dados = extract_capa_processo(resposta)
        return jsonify(dados)

    except Exception as e:
        logger.error(f"API: Erro ao consultar capa do processo: {str(e)}", exc_info=True)
        return jsonify({
            'erro': str(e),
            'mensagem': 'Erro ao consultar capa do processo'
        }), 500
        
        
@api.route('/processo/<num_processo>/pdf-completo', methods=['GET'])
def gerar_pdf_completo(num_processo):
    """
    Gera um PDF único contendo todos os documentos do processo.
    Lida com documentos em diferentes formatos (PDF e HTML).
    Versão otimizada com melhor gerenciamento de memória e processamento em blocos.
    
    Args:
        num_processo (str): Número do processo judicial
        
    Returns:
        O arquivo PDF combinado para download ou uma mensagem de erro
    """
    # Importar aqui para evitar problemas com o banco de dados
    try:
        # Usar a versão ultra-simplificada com timeouts agressivos para o Replit
        from fix_pdf_download_ultra_simples import gerar_pdf_ultra_simples as gerar_pdf_completo_otimizado
    except ImportError as e:
        logger.error(f"Erro ao importar módulo ultra-simplificado: {str(e)}")
        try:
            # Tentar a versão mais simples sem threads/processos
            from fix_pdf_download_simples import gerar_pdf_completo_simples as gerar_pdf_completo_otimizado
        except ImportError as e2:
            logger.error(f"Erro ao importar módulo simplificado: {str(e2)}")
            try:
                # Tentar a versão com timeout
                from fix_pdf_download_timeout import gerar_pdf_completo_otimizado
            except ImportError as e3:
                logger.error(f"Erro ao importar módulo timeout: {str(e3)}")
                try:
                    # Fallback para a versão original
                    from fix_pdf_download import gerar_pdf_completo_otimizado
                except ImportError as e4:
                    logger.error(f"Erro ao importar módulos necessários: {str(e4)}")
                    return jsonify({
                        'erro': 'Erro de configuração',
                        'mensagem': f'Não foi possível carregar os módulos necessários: {str(e4)}'
                    }), 500
        
    start_time = time.time()
    temp_dir = None
    try:
        logger.debug(f"API: Iniciando geração do PDF completo para o processo {num_processo}")
        
        # Obter credenciais
        cpf, senha = get_mni_credentials()
        if not cpf or not senha:
            return jsonify({
                'erro': 'Credenciais MNI não fornecidas',
                'mensagem': 'Forneça as credenciais nos headers X-MNI-CPF e X-MNI-SENHA'
            }), 401
        
        # Verificar se há parâmetro de limite
        try:
            limite_docs = int(request.args.get('limite', 0))
        except (ValueError, TypeError):
            limite_docs = 0
            
        # Verificar modo rápido (poucos documentos)
        modo_rapido = request.args.get('rapido', 'false').lower() == 'true'
        if modo_rapido and limite_docs == 0:
            limite_docs = 10  # Em modo rápido, limitar a 10 documentos por padrão
        
        # Logging para depuração
        logger.debug(f"Iniciando download do processo {num_processo} com limite de {limite_docs} documentos")
        
        # Usar a versão otimizada que implementa internamente todo o processo com melhor tratamento de timeouts
        output_path = gerar_pdf_completo_otimizado(num_processo, cpf, senha, limite_docs=limite_docs)
        
        if not output_path:
            return jsonify({
                'erro': 'Falha no processamento',
                'mensagem': 'Não foi possível processar o processo para gerar o PDF completo'
            }), 500
        
        # Nome do arquivo baseado na limitação
        if not os.path.exists(output_path):
            logger.error(f"Arquivo de saída não existe: {output_path}")
            return jsonify({
                'erro': 'Arquivo não encontrado',
                'mensagem': 'O arquivo PDF gerado não pôde ser localizado'
            }), 500
            
        # Log do tamanho do arquivo para debug
        file_size = os.path.getsize(output_path)
        logger.debug(f"Arquivo PDF gerado com sucesso: {output_path} ({file_size} bytes)")
            
        # Nome do arquivo para download
        if 'timeout' in output_path:
            download_filename = f'timeout_{num_processo}.pdf'
        elif 'erro' in output_path:
            download_filename = f'erro_{num_processo}.pdf'
        elif limite_docs > 0:
            download_filename = f'processo_parcial_{num_processo}_{limite_docs}docs.pdf'
        else:
            download_filename = f'processo_completo_{num_processo}.pdf'
            
        # Servir o arquivo para download
        return send_file(
            output_path,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=download_filename
        )
            
    except Exception as e:
        logger.error(f"API: Erro ao gerar PDF completo: {str(e)}", exc_info=True)
        return jsonify({
            'erro': str(e),
            'mensagem': 'Erro ao gerar PDF completo do processo'
        }), 500
    finally:
        # Certificar-se de que o medidor de tempo está disponível, mesmo em caso de erro
        if 'start_time' in locals():
            tempo_total = time.time() - start_time
            logger.debug(f"Tempo total de execução (incluindo erros): {tempo_total:.2f}s")
        
        # Tentar limpar os arquivos temporários, se possível
        if temp_dir and os.path.exists(temp_dir):
            try:
                import shutil
                shutil.rmtree(temp_dir, ignore_errors=True)
                logger.debug(f"Diretório temporário removido: {temp_dir}")
            except Exception as e:
                logger.warning(f"Não foi possível remover diretório temporário: {str(e)}")
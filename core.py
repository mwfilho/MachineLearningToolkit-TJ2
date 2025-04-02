import base64
from concurrent.futures import ThreadPoolExecutor
import concurrent.futures
from configparser import ConfigParser
from datetime import datetime, date
import json
import os
import time
import requests
from zeep import Client
from config import MNI_CONSULTA_URL, MNI_ID_CONSULTANTE, MNI_SENHA_CONSULTANTE, MNI_URL
import logging
from funcoes_mni import retorna_documento_processo, retorna_processo
import pandas as pd
from controle.exceptions import ExcecaoConsultaMNI
import re
from pdf_utils import process_document_content, merge_pdfs

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Dictionary mapping mimetypes to file extensions
mime_to_extension = {
    'application/pdf': '.pdf',
    'image/jpeg': '.jpg',
    'image/png': '.png',
    'application/zip': '.zip',
    'text/plain': '.txt',
    'application/msword': '.doc',
    'application/vnd.ms-excel': '.xls',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': '.docx',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': '.xlsx',
    'text/html': '.html',
}

def process_document(num_processo, doc_id):
    """
    Process a single document from a judicial process.

    Args:
        num_processo (str): Process number
        doc_id (str): Document ID

    Returns:
        dict: Document data including content and metadata
    """
    try:
        resposta = retorna_documento_processo(num_processo, doc_id)

        if 'msg_erro' in resposta:
            logger.error(f"Error processing document {doc_id}: {resposta['msg_erro']}")
            return None

        extensao = mime_to_extension.get(resposta['mimetype'], '.bin')

        return {
            'id': doc_id,
            'content': resposta['conteudo'],
            'mimetype': resposta['mimetype'],
            'extension': extensao
        }

    except ExcecaoConsultaMNI as e:
        logger.error(f"MNI Exception while processing document {doc_id}: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error while processing document {doc_id}: {str(e)}")
        return None

def validate_process_number(num_processo):
    """
    Validate process number format.

    Args:
        num_processo (str): Process number to validate

    Returns:
        bool: True if valid, False otherwise
    """
    pattern = r'^\d{7}-\d{2}\.\d{4}\.\d{1}\.\d{2}\.\d{4}$'
    return bool(re.match(pattern, num_processo))

def format_process_number(num_processo):
    """
    Format process number to CNJ standard.

    Args:
        num_processo (str): Process number to format

    Returns:
        str: Formatted process number
    """
    nums = re.sub(r'\D', '', num_processo)

    if len(nums) != 20:
        raise ValueError("Process number must have 20 digits")

    return f"{nums[:7]}-{nums[7:9]}.{nums[9:13]}.{nums[13]}.{nums[14:16]}.{nums[16:]}"
    
def generate_complete_process_pdf(num_processo, cpf=None, senha=None):
    """
    Gera um PDF completo com todos os documentos PDF do processo.
    
    Args:
        num_processo (str): Número do processo
        cpf (str, optional): CPF/CNPJ do consultante
        senha (str, optional): Senha do consultante
        
    Returns:
        dict: Conteúdo do PDF completo ou mensagem de erro
    """
    try:
        from funcoes_mni import retorna_documentos_processo_completo, retorna_documento_processo
        
        logger.debug(f"\n{'=' * 80}")
        logger.debug(f"Gerando PDF completo do processo {num_processo}")
        logger.debug(f"{'=' * 80}\n")
        
        # 1. Obter lista de todos os documentos do processo
        resposta_docs = retorna_documentos_processo_completo(num_processo, cpf=cpf, senha=senha)
        
        if 'msg_erro' in resposta_docs:
            logger.error(f"Erro ao obter documentos: {resposta_docs['msg_erro']}")
            return {
                'sucesso': False,
                'msg_erro': resposta_docs['msg_erro']
            }
            
        # 2. Verificar se há documentos
        if not resposta_docs.get('documentos'):
            logger.error("Nenhum documento encontrado no processo")
            return {
                'sucesso': False,
                'msg_erro': 'Processo não contém documentos'
            }
            
        logger.debug(f"Encontrados {resposta_docs['total_documentos']} documentos no processo")
        
        # 3. Baixar apenas os documentos PDF
        logger.debug("Baixando e processando documentos PDF")
        pdf_files = []
        
        for doc in resposta_docs['documentos']:
            doc_id = doc['id_documento']
            mimetype = doc['mimetype']
            descricao = doc['descricao']
            
            # Só processamos documentos PDF para evitar problemas de conversão
            if mimetype == 'application/pdf':
                logger.debug(f"Baixando documento PDF {doc_id}: {descricao}")
                try:
                    # Baixar o documento do processo
                    doc_response = retorna_documento_processo(num_processo, doc_id, cpf=cpf, senha=senha)
                    
                    if 'msg_erro' in doc_response:
                        logger.warning(f"Erro ao baixar documento {doc_id}: {doc_response['msg_erro']}")
                        continue
                        
                    # Adicionar à lista de PDFs
                    pdf_files.append((
                        doc_response['conteudo'],
                        descricao,
                        doc_id
                    ))
                    logger.debug(f"Documento {doc_id} baixado com sucesso")
                except Exception as e:
                    logger.error(f"Erro ao processar documento {doc_id}: {str(e)}")
                    continue
            else:
                logger.warning(f"Ignorando documento {doc_id} - não é PDF (mimetype: {mimetype})")
                
        # 4. Verificar se temos documentos PDF para mesclar
        if not pdf_files:
            logger.error("Nenhum documento PDF encontrado para mesclar")
            return {
                'sucesso': False,
                'msg_erro': 'Nenhum documento PDF encontrado no processo'
            }
            
        # 5. Mesclar todos os PDFs em um único arquivo
        logger.debug(f"Mesclando {len(pdf_files)} arquivos PDF")
        try:
            pdf_content = merge_pdfs(pdf_files)
            
            return {
                'sucesso': True,
                'numero_processo': num_processo,
                'total_documentos': len(pdf_files),
                'pdf_content': pdf_content,
                'mimetype': 'application/pdf'
            }
        except Exception as e:
            logger.error(f"Erro ao mesclar PDFs: {str(e)}", exc_info=True)
            return {
                'sucesso': False,
                'msg_erro': f'Erro ao mesclar PDFs: {str(e)}'
            }
    except Exception as e:
        logger.error(f"Erro inesperado ao gerar PDF completo: {str(e)}", exc_info=True)
        return {
            'sucesso': False,
            'msg_erro': f'Erro inesperado: {str(e)}'
        }
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
    Handles various input formats and tries to standardize them.

    Args:
        num_processo (str): Process number to format (can be in various formats)

    Returns:
        str: Formatted process number in CNJ standard format (NNNNNNN-DD.AAAA.J.TR.OOOO)
        
    Raises:
        ValueError: If the process number doesn't have enough digits or is invalid
    """
    if not num_processo:
        raise ValueError("Número de processo não fornecido")
        
    # Remove qualquer caractere que não seja dígito
    nums = re.sub(r'\D', '', num_processo)
    
    # Verificar se temos dígitos suficientes
    if len(nums) < 15:
        raise ValueError(f"Número de processo com poucos dígitos: {len(nums)}. São necessários 20 dígitos")
        
    # Se tiver menos de 20 dígitos mas mais de 15, tenta completar com zeros
    if len(nums) < 20 and len(nums) >= 15:
        logger.warning(f"Número de processo incompleto ({len(nums)} dígitos). Tentando completar com zeros...")
        # Adiciona zeros à direita para completar 20 dígitos
        nums = nums.ljust(20, '0')
        
    # Se tiver mais de 20 dígitos, usa apenas os primeiros 20
    if len(nums) > 20:
        logger.warning(f"Número de processo com muitos dígitos ({len(nums)}). Usando apenas os primeiros 20.")
        nums = nums[:20]
        
    # Agora temos exatamente 20 dígitos, podemos formatar
    return f"{nums[:7]}-{nums[7:9]}.{nums[9:13]}.{nums[13]}.{nums[14:16]}.{nums[16:]}"
    
def generate_document_with_attachments_pdf(num_processo, doc_id, cpf=None, senha=None):
    """
    Gera um PDF com um documento específico e seus anexos.
    
    Args:
        num_processo (str): Número do processo
        doc_id (str): ID do documento principal
        cpf (str, optional): CPF/CNPJ do consultante
        senha (str, optional): Senha do consultante
        
    Returns:
        dict: Conteúdo do PDF mesclado ou mensagem de erro
    """
    try:
        from funcoes_mni import retorna_processo, retorna_documento_processo
        from pdf_utils import merge_pdfs, process_document_content
        
        logger.debug(f"\n{'=' * 80}")
        logger.debug(f"Gerando PDF do documento {doc_id} e seus anexos - Processo {num_processo}")
        logger.debug(f"{'=' * 80}\n")
        
        # 1. Consultar o processo para obter dados do documento e seus anexos
        resposta_processo = retorna_processo(num_processo, cpf=cpf, senha=senha)
        
        if 'msg_erro' in resposta_processo:
            logger.error(f"Erro ao consultar processo: {resposta_processo['msg_erro']}")
            return {
                'sucesso': False,
                'msg_erro': resposta_processo['msg_erro']
            }
        
        # 2. Encontrar o documento principal e seus anexos
        documento_principal = None
        documentos_anexos = []
        
        if 'documentos' in resposta_processo:
            for doc in resposta_processo['documentos']:
                if doc.get('id_documento') == doc_id:
                    documento_principal = doc
                    # Procurar os documentos vinculados
                    if 'documentos_vinculados' in doc:
                        documentos_anexos = doc.get('documentos_vinculados', [])
                    break
        
        if not documento_principal:
            logger.error(f"Documento {doc_id} não encontrado no processo {num_processo}")
            return {
                'sucesso': False,
                'msg_erro': f"Documento {doc_id} não encontrado no processo"
            }
        
        logger.debug(f"Documento principal: {documento_principal.get('descricao')} (ID: {doc_id})")
        logger.debug(f"Encontrados {len(documentos_anexos)} anexos")
        
        # 3. Baixar o documento principal
        resposta_doc = retorna_documento_processo(num_processo, doc_id, cpf=cpf, senha=senha)
        
        if 'msg_erro' in resposta_doc:
            logger.error(f"Erro ao baixar documento principal: {resposta_doc['msg_erro']}")
            return {
                'sucesso': False,
                'msg_erro': resposta_doc['msg_erro']
            }
        
        # 4. Preparar lista de PDFs para mesclar
        pdf_files = []
        
        # 4.1 Processar o documento principal (convertendo para PDF se necessário)
        mime_principal = resposta_doc.get('mimetype', 'application/octet-stream')
        descricao_principal = documento_principal.get('descricao', f'Documento {doc_id}')
        
        # Processar o conteúdo (converte para PDF se for HTML ou outro formato suportado)
        try:
            conteudo_pdf = process_document_content(
                resposta_doc['conteudo'], 
                mime_principal,
                doc_id,
                descricao_principal
            )
            
            # Adicionar à lista de PDFs
            pdf_files.append((
                conteudo_pdf,
                descricao_principal,
                doc_id
            ))
            logger.debug(f"Documento principal processado com sucesso")
        except Exception as e:
            logger.error(f"Erro ao processar documento principal: {str(e)}")
            # Continuamos mesmo com erro no documento principal
        
        # 4.2 Processar os anexos
        for i, anexo in enumerate(documentos_anexos):
            anexo_id = anexo.get('id_documento')
            descricao_anexo = anexo.get('descricao', f'Anexo {i+1}')
            
            if not anexo_id:
                logger.warning(f"Anexo sem ID encontrado: {descricao_anexo}")
                continue
                
            logger.debug(f"Baixando anexo {anexo_id}: {descricao_anexo}")
            
            try:
                # Baixar o anexo
                resposta_anexo = retorna_documento_processo(num_processo, anexo_id, cpf=cpf, senha=senha)
                
                if 'msg_erro' in resposta_anexo:
                    logger.warning(f"Erro ao baixar anexo {anexo_id}: {resposta_anexo['msg_erro']}")
                    continue
                
                mime_anexo = resposta_anexo.get('mimetype', 'application/octet-stream')
                
                # Processar o conteúdo do anexo (converte para PDF se necessário)
                conteudo_pdf_anexo = process_document_content(
                    resposta_anexo['conteudo'], 
                    mime_anexo,
                    anexo_id,
                    descricao_anexo
                )
                
                # Adicionar à lista de PDFs
                pdf_files.append((
                    conteudo_pdf_anexo,
                    descricao_anexo,
                    anexo_id
                ))
                logger.debug(f"Anexo {anexo_id} processado com sucesso")
            except Exception as e:
                logger.error(f"Erro ao processar anexo {anexo_id}: {str(e)}")
                continue
        
        # 5. Verificar se temos algum PDF para mesclar
        if not pdf_files:
            logger.error("Nenhum documento PDF disponível para mesclar")
            return {
                'sucesso': False,
                'msg_erro': 'Não foi possível processar o documento e seus anexos'
            }
        
        # 6. Mesclar todos os PDFs em um único arquivo
        logger.debug(f"Mesclando {len(pdf_files)} arquivos PDF")
        
        try:
            pdf_content = merge_pdfs(pdf_files)
            
            return {
                'sucesso': True,
                'numero_processo': num_processo,
                'id_documento': doc_id,
                'descricao': descricao_principal,
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
        logger.error(f"Erro inesperado ao gerar PDF do documento e anexos: {str(e)}", exc_info=True)
        return {
            'sucesso': False,
            'msg_erro': f'Erro inesperado: {str(e)}'
        }

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
        from pdf_utils import merge_pdfs
        
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
        
        # Contador para limitar o número de documentos em caso de processos muito grandes
        max_docs = 50
        contador = 0
        
        for doc in resposta_docs['documentos']:
            # Limitador para não sobrecarregar o sistema com processos muito grandes
            contador += 1
            if contador > max_docs:
                logger.warning(f"Limite de {max_docs} documentos atingido, os demais serão ignorados")
                break
                
            doc_id = doc.get('id_documento', '')
            mimetype = doc.get('mimetype', '')
            descricao = doc.get('descricao', f'Documento {doc_id}')
            
            if not doc_id:
                logger.warning(f"Documento sem ID encontrado: {descricao}")
                continue
            
            # Só processamos documentos PDF para evitar problemas de conversão
            if mimetype == 'application/pdf':
                logger.debug(f"Baixando documento PDF {doc_id}: {descricao}")
                try:
                    # Baixar o documento do processo
                    doc_response = retorna_documento_processo(num_processo, doc_id, cpf=cpf, senha=senha)
                    
                    if 'msg_erro' in doc_response:
                        logger.warning(f"Erro ao baixar documento {doc_id}: {doc_response['msg_erro']}")
                        continue
                        
                    if not doc_response.get('conteudo'):
                        logger.warning(f"Documento {doc_id} sem conteúdo")
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
        
        # Mesmo que tenhamos erros ao mesclar, tentamos retornar um PDF vazio em vez de falhar
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
            # O merge_pdfs já retorna um PDF em branco em caso de erro
            # Em vez de falhar, retornamos esse PDF vazio
            logger.error(f"Erro ao mesclar PDFs: {str(e)}", exc_info=True)
            
            # Criar PDF vazio
            from PyPDF2 import PdfWriter
            from io import BytesIO
            
            pdf = PdfWriter()
            pdf.add_blank_page(width=595, height=842)  # A4
            temp = BytesIO()
            pdf.write(temp)
            temp.seek(0)
            empty_pdf = temp.getvalue()
            
            return {
                'sucesso': True,  # Retornamos sucesso mesmo com erro para devolver um PDF vazio
                'numero_processo': num_processo,
                'total_documentos': 0,
                'pdf_content': empty_pdf,
                'mimetype': 'application/pdf',
                'aviso': f'Erro ao mesclar PDFs: {str(e)}'
            }
            
    except Exception as e:
        logger.error(f"Erro inesperado ao gerar PDF completo: {str(e)}", exc_info=True)
        
        # Mesmo com erro, retornamos um PDF vazio
        try:
            from PyPDF2 import PdfWriter
            from io import BytesIO
            
            pdf = PdfWriter()
            pdf.add_blank_page(width=595, height=842)  # A4
            temp = BytesIO()
            pdf.write(temp)
            temp.seek(0)
            empty_pdf = temp.getvalue()
            
            return {
                'sucesso': True,  # Retornamos sucesso mesmo com erro para devolver um PDF vazio
                'numero_processo': num_processo,
                'total_documentos': 0,
                'pdf_content': empty_pdf,
                'mimetype': 'application/pdf',
                'aviso': f'Erro inesperado: {str(e)}'
            }
        except:
            # Se até a criação do PDF vazio falhar, aí sim retornamos erro
            return {
                'sucesso': False,
                'msg_erro': f'Erro inesperado: {str(e)}'
            }
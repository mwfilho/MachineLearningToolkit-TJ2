import base64
from concurrent.futures import ThreadPoolExecutor
import concurrent.futures
from configparser import ConfigParser
from datetime import datetime, date
import json
import os
import time
import requests
import io
import tempfile
import subprocess
import logging
from funcoes_mni import retorna_documento_processo, retorna_processo
from controle.exceptions import ExcecaoConsultaMNI
import re
# Try to import PyPDF2, but provide fallback
try:
    from PyPDF2 import PdfMerger
    HAS_PYPDF2 = True
except ImportError:
    HAS_PYPDF2 = False
    import logging
    logging.warning("PyPDF2 not available. PDF merging functionality will be limited.")

from config import MNI_CONSULTA_URL, MNI_ID_CONSULTANTE, MNI_SENHA_CONSULTANTE, MNI_URL

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

def html_to_pdf(html_content, output_path):
    """
    Convert HTML content to PDF using wkhtmltopdf.

    Args:
        html_content (bytes): HTML content as bytes
        output_path (str): Path where to save the PDF

    Returns:
        bool: True if conversion successful, False otherwise
    """
    temp_html_path = None
    try:
        # Save the HTML content to a temporary file
        with tempfile.NamedTemporaryFile(suffix='.html', delete=False) as temp_html:
            temp_html.write(html_content)
            temp_html_path = temp_html.name

        # Check if wkhtmltopdf is available
        try:
            # Try to run wkhtmltopdf with --version to check if it's available
            subprocess.run(['wkhtmltopdf', '--version'], 
                           check=True, 
                           stdout=subprocess.DEVNULL, 
                           stderr=subprocess.DEVNULL)
            
            # If we get here, wkhtmltopdf is available
            result = subprocess.run(
                ['wkhtmltopdf', '--quiet', temp_html_path, output_path],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            
            conversion_success = result.returncode == 0
            
        except (subprocess.SubprocessError, FileNotFoundError):
            logger.error("wkhtmltopdf is not installed. Cannot convert HTML to PDF.")
            # As a fallback, just save the HTML content as is
            with open(output_path, 'wb') as f:
                f.write(html_content)
            logger.warning("Saved HTML content without conversion as fallback.")
            conversion_success = False
        
        # Clean up temp file if it exists
        if temp_html_path and os.path.exists(temp_html_path):
            os.unlink(temp_html_path)
        
        return conversion_success
    
    except Exception as e:
        logger.error(f"Error converting HTML to PDF: {str(e)}")
        # Clean up temp file if it exists
        try:
            if temp_html_path and os.path.exists(temp_html_path):
                os.unlink(temp_html_path)
        except Exception as cleanup_err:
            logger.error(f"Error cleaning up temp file: {str(cleanup_err)}")
        return False

def merge_process_documents(num_processo, cpf=None, senha=None):
    """
    Fetch all documents from a process and merge them into a single PDF.
    
    Args:
        num_processo (str): Process number
        cpf (str, optional): CPF/CNPJ of the requester
        senha (str, optional): Password of the requester
        
    Returns:
        tuple: (bytes or None, dict) - PDF content and processing stats
    """
    # Check if PyPDF2 is available
    if not HAS_PYPDF2:
        logger.error("PyPDF2 is not available. Cannot merge PDF documents.")
        return None, {
            'status': 'error',
            'message': "PyPDF2 is not available. Cannot merge PDF documents. Please install PyPDF2."
        }
        
    try:
        logger.debug(f"Starting document merge for process {num_processo}")
        
        # Get process details
        response = retorna_processo(num_processo, cpf=cpf, senha=senha)
        
        if not response.sucesso:
            logger.error(f"Failed to get process details: {response.mensagem if hasattr(response, 'mensagem') else 'Unknown error'}")
            return None, {
                'status': 'error',
                'message': f"Failed to get process details: {response.mensagem if hasattr(response, 'mensagem') else 'Unknown error'}"
            }
            
        if not hasattr(response.processo, 'documento'):
            logger.error("Process does not contain any documents")
            return None, {
                'status': 'error',
                'message': "Process does not contain any documents"
            }
            
        # Initialize PDF merger
        merger = PdfMerger()
        
        # Temporary directory for HTML to PDF conversions
        temp_dir = tempfile.mkdtemp()
        
        # Stats
        stats = {
            'total_documents': 0,
            'pdf_documents': 0,
            'html_documents': 0,
            'failed_documents': 0,
            'document_ids': []
        }
        
        # Extract all documents including linked ones
        all_documents = []
        
        def extract_document_info(doc, is_linked=False):
            """Extract document info and add to all_documents list"""
            if hasattr(doc, 'mimetype') and hasattr(doc, 'idDocumento'):
                mimetype = getattr(doc, 'mimetype', '')
                if mimetype in ['application/pdf', 'text/html']:
                    all_documents.append({
                        'id': doc.idDocumento,
                        'mimetype': mimetype,
                        'is_linked': is_linked
                    })
                    
            # Check for linked documents
            if hasattr(doc, 'documentoVinculado'):
                vinc_docs = doc.documentoVinculado
                if not isinstance(vinc_docs, list):
                    vinc_docs = [vinc_docs]
                    
                for vinc_doc in vinc_docs:
                    extract_document_info(vinc_doc, is_linked=True)
        
        # Process main documents
        docs = response.processo.documento
        if not isinstance(docs, list):
            docs = [docs]
            
        for doc in docs:
            extract_document_info(doc)
            
        # Process each document
        logger.debug(f"Found {len(all_documents)} documents to process")
        
        for doc_info in all_documents:
            try:
                stats['total_documents'] += 1
                stats['document_ids'].append(doc_info['id'])
                
                # Get document content
                doc_response = retorna_documento_processo(num_processo, doc_info['id'], cpf=cpf, senha=senha)
                
                if 'msg_erro' in doc_response:
                    logger.error(f"Error fetching document {doc_info['id']}: {doc_response['msg_erro']}")
                    stats['failed_documents'] += 1
                    continue
                    
                # Process based on mimetype
                if doc_response['mimetype'] == 'application/pdf':
                    # Process PDF
                    pdf_file = io.BytesIO(doc_response['conteudo'])
                    merger.append(pdf_file)
                    stats['pdf_documents'] += 1
                    logger.debug(f"Added PDF document {doc_info['id']}")
                    
                elif doc_response['mimetype'] == 'text/html':
                    # Process HTML
                    temp_pdf_path = os.path.join(temp_dir, f"doc_{doc_info['id']}.pdf")
                    
                    # Convert HTML to PDF
                    if html_to_pdf(doc_response['conteudo'], temp_pdf_path):
                        merger.append(temp_pdf_path)
                        stats['html_documents'] += 1
                        logger.debug(f"Added HTML document {doc_info['id']} (converted to PDF)")
                    else:
                        logger.error(f"Failed to convert HTML to PDF for document {doc_info['id']}")
                        stats['failed_documents'] += 1
                        
                # Small pause to avoid overloading the server
                time.sleep(0.2)
                
            except Exception as e:
                logger.error(f"Error processing document {doc_info['id']}: {str(e)}")
                stats['failed_documents'] += 1
        
        # Check if any documents were processed successfully
        if stats['pdf_documents'] + stats['html_documents'] == 0:
            logger.error("No documents could be processed")
            # Clean up
            for file in os.listdir(temp_dir):
                os.unlink(os.path.join(temp_dir, file))
            os.rmdir(temp_dir)
            
            return None, {
                'status': 'error',
                'message': "No documents could be processed",
                'stats': stats
            }
            
        # Create the merged PDF
        output_pdf = io.BytesIO()
        merger.write(output_pdf)
        merger.close()
        
        # Clean up temporary files
        for file in os.listdir(temp_dir):
            os.unlink(os.path.join(temp_dir, file))
        os.rmdir(temp_dir)
        
        # Return to the beginning of the BytesIO object
        output_pdf.seek(0)
        
        return output_pdf.read(), {
            'status': 'success',
            'stats': stats
        }
        
    except Exception as e:
        logger.error(f"Error merging documents: {str(e)}", exc_info=True)
        return None, {
            'status': 'error',
            'message': f"Error merging documents: {str(e)}"
        }
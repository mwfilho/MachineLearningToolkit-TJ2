import os
import tempfile
import logging
from io import BytesIO
from typing import List, Dict, Any, Tuple, Optional
from PyPDF2 import PdfMerger, PdfReader, PdfWriter
import base64

# Configure logging
logger = logging.getLogger(__name__)

def merge_pdfs(pdf_files: List[Tuple[bytes, str, str]]) -> bytes:
    """
    Mescla múltiplos arquivos PDF em um único documento.
    
    Args:
        pdf_files: Lista de tuplas (conteúdo_pdf, descrição, id_documento)
        
    Returns:
        bytes: PDF mesclado
    """
    try:
        logger.debug(f"Mesclando {len(pdf_files)} arquivos PDF")
        merger = PdfMerger()
        
        for i, (pdf_content, desc, doc_id) in enumerate(pdf_files):
            logger.debug(f"Processando documento {i+1}/{len(pdf_files)}: {desc} (ID: {doc_id})")
            
            # Cria um objeto BytesIO a partir do conteúdo PDF
            pdf_bytes = BytesIO(pdf_content)
            
            try:
                # Tenta adicionar o PDF ao merger
                merger.append(pdf_bytes, import_bookmarks=False)
                logger.debug(f"Documento {doc_id} adicionado com sucesso")
            except Exception as e:
                logger.error(f"Erro ao adicionar documento {doc_id}: {str(e)}")
                # Em caso de erro, adiciona uma página em branco com mensagem
                pdf = PdfWriter()
                pdf.add_blank_page(width=595, height=842)  # A4
                temp = BytesIO()
                pdf.write(temp)
                temp.seek(0)
                merger.append(temp, import_bookmarks=False)
        
        # Grava o PDF mesclado em um BytesIO
        output = BytesIO()
        merger.write(output)
        merger.close()
        
        # Retorna os bytes do PDF mesclado
        output.seek(0)
        return output.getvalue()
    except Exception as e:
        logger.error(f"Erro ao mesclar PDFs: {str(e)}", exc_info=True)
        # Em caso de erro, retornar PDF vazio
        pdf = PdfWriter()
        pdf.add_blank_page(width=595, height=842)  # A4
        temp = BytesIO()
        pdf.write(temp)
        temp.seek(0)
        return temp.getvalue()

def process_document_content(content: bytes, mimetype: str) -> bytes:
    """
    Processa o conteúdo do documento de acordo com seu tipo MIME.
    
    Args:
        content: Conteúdo do documento
        mimetype: Tipo MIME do documento
        
    Returns:
        bytes: Conteúdo processado (já deve ser PDF ou PDF vazio com mensagem)
    """
    try:
        # Se o documento já for um PDF, retorna como está
        if mimetype == 'application/pdf':
            return content
        
        # Para outros tipos, cria um PDF simples
        else:
            logger.warning(f"Tipo de documento não é PDF: {mimetype}")
            pdf = PdfWriter()
            pdf.add_blank_page(width=595, height=842)  # A4
            temp = BytesIO()
            pdf.write(temp)
            temp.seek(0)
            return temp.getvalue()
    except Exception as e:
        logger.error(f"Erro ao processar conteúdo do documento: {str(e)}", exc_info=True)
        # Em caso de erro, retorna PDF vazio
        pdf = PdfWriter()
        pdf.add_blank_page(width=595, height=842)  # A4
        temp = BytesIO()
        pdf.write(temp)
        temp.seek(0)
        return temp.getvalue()
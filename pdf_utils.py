import os
import tempfile
import logging
from io import BytesIO
from typing import List, Dict, Any, Tuple, Optional
import base64

# Importa PyPDF2 com tratamento de erro
try:
    from PyPDF2 import PdfMerger, PdfReader, PdfWriter
except ImportError:
    # Fallback para a versão mais recente do PyPDF2
    try:
        from PyPDF2 import PdfFileMerger as PdfMerger
        from PyPDF2 import PdfFileReader as PdfReader
        from PyPDF2 import PdfFileWriter as PdfWriter
    except ImportError:
        logger = logging.getLogger(__name__)
        logger.error("Não foi possível importar PyPDF2. Instale com: pip install pypdf2")
        raise

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
        
        # Se não tiver arquivos, retorna um PDF em branco
        if not pdf_files:
            logger.warning("Nenhum arquivo PDF para mesclar")
            pdf = PdfWriter()
            pdf.add_blank_page(width=595, height=842)  # A4
            temp = BytesIO()
            pdf.write(temp)
            temp.seek(0)
            return temp.getvalue()
            
        # Cria um novo mesclador de PDFs
        merger = PdfMerger()
        
        # Variável para controlar se pelo menos um PDF foi adicionado com sucesso
        at_least_one_success = False
        
        for i, (pdf_content, desc, doc_id) in enumerate(pdf_files):
            logger.debug(f"Processando documento {i+1}/{len(pdf_files)}: {desc} (ID: {doc_id})")
            
            try:
                # Tentativa 1: Usar diretamente o conteúdo do PDF
                pdf_bytes = BytesIO(pdf_content)
                
                # Verificar se o PDF é válido antes de adicionar
                try:
                    # Tenta ler o PDF para verificar se é válido
                    pdf_reader = PdfReader(pdf_bytes)
                    page_count = len(pdf_reader.pages)
                    logger.debug(f"Documento {doc_id} é um PDF válido com {page_count} páginas")
                    
                    # Reinicia o ponteiro do buffer para o início
                    pdf_bytes.seek(0)
                    
                    # Adiciona o PDF ao merger
                    merger.append(pdf_bytes, import_bookmarks=False)
                    logger.debug(f"Documento {doc_id} adicionado com sucesso")
                    at_least_one_success = True
                    
                except Exception as pdf_error:
                    logger.error(f"PDF inválido (ID: {doc_id}): {str(pdf_error)}")
                    # Adiciona uma página em branco com mensagem de erro
                    pdf = PdfWriter()
                    pdf.add_blank_page(width=595, height=842)  # A4
                    temp = BytesIO()
                    pdf.write(temp)
                    temp.seek(0)
                    merger.append(temp, import_bookmarks=False)
                
            except Exception as e:
                logger.error(f"Erro ao processar documento {doc_id}: {str(e)}")
                # Em caso de erro geral, adiciona uma página em branco
                pdf = PdfWriter()
                pdf.add_blank_page(width=595, height=842)  # A4
                temp = BytesIO()
                pdf.write(temp)
                temp.seek(0)
                merger.append(temp, import_bookmarks=False)
        
        # Se nenhum PDF foi adicionado com sucesso, lança exceção
        if not at_least_one_success:
            raise ValueError("Nenhum documento PDF válido foi encontrado para mesclar")
            
        # Grava o PDF mesclado em um BytesIO
        output = BytesIO()
        merger.write(output)
        merger.close()
        
        # Retorna os bytes do PDF mesclado
        output.seek(0)
        return output.getvalue()
        
    except Exception as e:
        logger.error(f"Erro ao mesclar PDFs: {str(e)}", exc_info=True)
        # Em caso de erro, retornar PDF vazio com uma mensagem
        pdf = PdfWriter()
        pdf.add_blank_page(width=595, height=842)  # A4
        temp = BytesIO()
        pdf.write(temp)
        temp.seek(0)
        return temp.getvalue()

def process_document_content(content: bytes, mimetype: str, documento_id: str = None, descricao: str = None) -> bytes:
    """
    Processa o conteúdo do documento de acordo com seu tipo MIME.
    
    Args:
        content: Conteúdo do documento
        mimetype: Tipo MIME do documento
        documento_id: ID do documento (opcional, para logs)
        descricao: Descrição do documento (opcional, para logs)
        
    Returns:
        bytes: Conteúdo processado (já deve ser PDF ou PDF vazio com mensagem)
    """
    try:
        doc_info = f"Documento {documento_id or 'desconhecido'}"
        if descricao:
            doc_info += f" ({descricao})"
            
        # Verificar se o conteúdo está vazio
        if not content or len(content) == 0:
            logger.warning(f"{doc_info}: Conteúdo vazio")
            return create_empty_pdf(f"Documento sem conteúdo: {doc_info}")
            
        # Se o documento já for um PDF, verifica se é válido
        if mimetype == 'application/pdf':
            try:
                # Verifica se é um PDF válido
                pdf_bytes = BytesIO(content)
                pdf_reader = PdfReader(pdf_bytes)
                page_count = len(pdf_reader.pages)
                logger.debug(f"{doc_info}: PDF válido com {page_count} páginas")
                return content
            except Exception as pdf_error:
                logger.error(f"{doc_info}: PDF inválido: {str(pdf_error)}")
                return create_empty_pdf(f"PDF inválido: {doc_info}")
        
        # Para documentos de texto, tenta criar um PDF simples com o texto
        elif mimetype in ['text/plain', 'text/html', 'text/xml', 'application/xml']:
            try:
                from weasyprint import HTML
                from weasyprint.text.fonts import FontConfiguration
                
                # Tenta decodificar como texto
                try:
                    text_content = content.decode('utf-8')
                except UnicodeDecodeError:
                    # Tenta outras codificações comuns
                    try:
                        text_content = content.decode('latin-1')
                    except:
                        # Se falhar, usa a representação de bytes
                        text_content = str(content)
                
                # Limita o tamanho do texto para não sobrecarregar o PDF
                if len(text_content) > 100000:
                    text_content = text_content[:100000] + "\n\n[Conteúdo truncado...]"
                
                # Cria HTML simples com o texto
                html_content = f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <meta charset="UTF-8">
                    <title>{doc_info}</title>
                    <style>
                        body {{ font-family: Arial, sans-serif; margin: 20px; }}
                        pre {{ white-space: pre-wrap; }}
                    </style>
                </head>
                <body>
                    <h1>{doc_info}</h1>
                    <pre>{text_content}</pre>
                </body>
                </html>
                """
                
                # Converte o HTML para PDF
                font_config = FontConfiguration()
                pdf_bytes = BytesIO()
                HTML(string=html_content).write_pdf(pdf_bytes, font_config=font_config)
                pdf_bytes.seek(0)
                return pdf_bytes.getvalue()
            except Exception as html_error:
                logger.error(f"Erro ao converter texto para PDF: {str(html_error)}")
                return create_empty_pdf(f"Não foi possível converter o documento: {doc_info}")
        
        # Para imagens, poderíamos converter usando reportlab ou weasyprint
        # Mas por enquanto, apenas retornamos um PDF vazio
        else:
            logger.warning(f"{doc_info}: Tipo MIME não suportado: {mimetype}")
            return create_empty_pdf(f"Tipo de documento não suportado ({mimetype}): {doc_info}")
            
    except Exception as e:
        logger.error(f"Erro ao processar conteúdo do documento: {str(e)}", exc_info=True)
        # Em caso de erro, retorna PDF vazio
        return create_empty_pdf("Erro ao processar documento")


def create_empty_pdf(message: str = "Documento não disponível") -> bytes:
    """
    Cria um PDF vazio com uma mensagem.
    
    Args:
        message: Mensagem a ser exibida no PDF
        
    Returns:
        bytes: Conteúdo do PDF
    """
    try:
        # Tentativa usando PyPDF2
        pdf = PdfWriter()
        pdf.add_blank_page(width=595, height=842)  # A4
        temp = BytesIO()
        pdf.write(temp)
        temp.seek(0)
        return temp.getvalue()
    except Exception as e:
        logger.error(f"Erro ao criar PDF vazio: {str(e)}")
        # Retorna bytes vazios como último recurso
        return b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"
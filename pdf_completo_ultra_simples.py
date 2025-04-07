"""
Versão ultra simplificada para geração de PDF completo de processos,
especialmente otimizada para o ambiente Replit.
"""

import os
import tempfile
import time
import logging
import io
from PyPDF2 import PdfMerger, PdfReader
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from funcoes_mni import retorna_processo, retorna_documento_processo
from utils import extract_mni_data

# Configurar logging
logger = logging.getLogger(__name__)

# Configurações muito restritas para o ambiente Replit
MAX_DOCS = 3  # Limite máximo de documentos
DOCUMENTO_TIMEOUT = 3  # Timeout por documento (segundos)
GLOBAL_TIMEOUT = 20  # Timeout total (segundos)

def gerar_pdf_completo_ultra_simples(num_processo, cpf, senha, limite_docs=None):
    """
    Versão extremamente simplificada para gerar PDF com documentos de um processo.
    Limitada a poucos documentos e com timeouts agressivos.
    
    Args:
        num_processo (str): Número do processo judicial
        cpf (str): CPF/CNPJ do consultante
        senha (str): Senha do consultante
        limite_docs (int, optional): Limite de documentos a processar.
        
    Returns:
        str: Caminho para o PDF gerado ou None em caso de erro
    """
    start_time = time.time()
    temp_dir = None
    
    try:
        # Criar diretório temporário
        temp_dir = tempfile.mkdtemp()
        logger.debug(f"Diretório temporário criado: {temp_dir}")
        
        # Aplicar limite máximo de documentos
        if not limite_docs or limite_docs > MAX_DOCS:
            limite_docs = MAX_DOCS
            logger.warning(f"Limitando a {MAX_DOCS} documentos para garantir desempenho")
        
        # Consultar o processo com timeout
        logger.debug(f"Consultando processo {num_processo}")
        try:
            resposta = retorna_processo(num_processo, cpf=cpf, senha=senha)
        except Exception as e:
            logger.error(f"Erro ao consultar processo: {str(e)}")
            return gerar_pdf_informativo(temp_dir, num_processo, f"Erro na consulta: {str(e)}")
        
        # Extrair dados do processo
        try:
            dados = extract_mni_data(resposta)
        except Exception as e:
            logger.error(f"Erro ao extrair dados da resposta: {str(e)}")
            return gerar_pdf_informativo(temp_dir, num_processo, f"Erro ao processar resposta: {str(e)}")
        
        if not dados.get('sucesso'):
            erro_msg = dados.get('mensagem', 'Erro desconhecido')
            logger.error(f"Erro na consulta: {erro_msg}")
            return gerar_pdf_informativo(temp_dir, num_processo, f"Erro na consulta: {erro_msg}")
        
        # Verificar existência de documentos
        documentos = dados.get('documentos', [])
        if not documentos:
            logger.warning(f"Processo {num_processo} não possui documentos acessíveis")
            return gerar_pdf_informativo(temp_dir, num_processo, 
                                        "O processo não possui documentos acessíveis")
        
        # Limitando aos primeiros documentos
        documentos = documentos[:limite_docs]
        logger.info(f"Buscando {len(documentos)} documentos")
        
        # Gerar o cabeçalho do processo
        output_path = os.path.join(temp_dir, f"processo_{num_processo}.pdf")
        cabecalho_buffer = gerar_cabecalho_processo(dados, documentos)
        
        with open(output_path, 'wb') as f:
            cabecalho_buffer.seek(0)
            f.write(cabecalho_buffer.getvalue())
        
        # Processar documentos individualmente
        processados = 0
        erros = 0
        pdfs_documentos = []
        
        # Para cada documento, tentar processar com timeout
        for i, doc in enumerate(documentos, 1):
            # Verificar timeout global
            if time.time() - start_time > GLOBAL_TIMEOUT:
                logger.warning(f"Timeout global atingido após processar {processados} documentos")
                break
                
            doc_id = doc.get('id')
            doc_tipo = doc.get('tipoDocumento', 'Documento')
            
            logger.debug(f"Processando documento {i}/{len(documentos)}: {doc_id} ({doc_tipo})")
            
            try:
                # Timeout por documento
                doc_start_time = time.time()
                
                # Fazer o download do documento
                resposta_doc = retorna_documento_processo(num_processo, doc_id, cpf=cpf, senha=senha)
                
                # Verificar timeout
                if time.time() - doc_start_time > DOCUMENTO_TIMEOUT:
                    logger.warning(f"Documento {doc_id} atingiu timeout ({DOCUMENTO_TIMEOUT}s)")
                    timeout_pdf = os.path.join(temp_dir, f"doc_{doc_id}_timeout.pdf")
                    create_info_pdf(f"Timeout ao baixar documento {doc_id}", 
                                  timeout_pdf, doc_id, doc_tipo)
                    pdfs_documentos.append(timeout_pdf)
                    erros += 1
                    continue
                
                # Verificar se tem erro na resposta
                if 'msg_erro' in resposta_doc:
                    logger.error(f"Erro ao obter documento {doc_id}: {resposta_doc['msg_erro']}")
                    error_pdf = os.path.join(temp_dir, f"doc_{doc_id}_erro.pdf")
                    create_info_pdf(f"Erro ao baixar documento {doc_id}: {resposta_doc['msg_erro']}", 
                                  error_pdf, doc_id, doc_tipo)
                    pdfs_documentos.append(error_pdf)
                    erros += 1
                    continue
                
                # Verificar se tem conteúdo
                if not resposta_doc.get('conteudo'):
                    logger.warning(f"Documento {doc_id} sem conteúdo")
                    no_content_pdf = os.path.join(temp_dir, f"doc_{doc_id}_sem_conteudo.pdf")
                    create_info_pdf(f"O documento {doc_id} ({doc_tipo}) não possui conteúdo", 
                                  no_content_pdf, doc_id, doc_tipo)
                    pdfs_documentos.append(no_content_pdf)
                    erros += 1
                    continue
                
                # Processar o documento conforme seu tipo
                mimetype = resposta_doc.get('mimetype', '')
                conteudo = resposta_doc.get('conteudo', b'')
                
                # Caminho para o arquivo temporário
                arquivo_temp = os.path.join(temp_dir, f"doc_{doc_id}")
                pdf_path = None
                
                # Converter para PDF conforme o tipo, abordagem simplificada
                if mimetype == 'application/pdf':
                    # Já é PDF, salvar diretamente
                    pdf_path = f"{arquivo_temp}.pdf"
                    with open(pdf_path, 'wb') as f:
                        f.write(conteudo)
                else:
                    # Qualquer outro formato: converter para texto e depois PDF
                    pdf_path = f"{arquivo_temp}.pdf"
                    try:
                        texto = "Conteúdo original não é PDF. "
                        
                        if mimetype.startswith('text/'):
                            # Tentar decodificar o conteúdo como texto
                            try:
                                texto += conteudo.decode('utf-8', errors='ignore')
                                if len(texto) > 50000:  # Limitar a ~50KB
                                    texto = texto[:50000] + "\n\n[...TEXTO TRUNCADO POR SER MUITO LONGO...]"
                            except:
                                texto += f"[Erro ao decodificar conteúdo {mimetype}]"
                        else:
                            texto += f"[Conteúdo binário {mimetype} não pode ser exibido]"
                        
                        # Criar PDF simples
                        create_text_pdf(texto, pdf_path, doc_id, doc_tipo)
                    except Exception as e:
                        logger.error(f"Erro ao processar conteúdo: {str(e)}")
                        error_pdf = os.path.join(temp_dir, f"doc_{doc_id}_erro_conteudo.pdf")
                        create_info_pdf(f"Erro ao processar conteúdo: {str(e)}", 
                                      error_pdf, doc_id, doc_tipo)
                        pdf_path = error_pdf
                        erros += 1
                
                # Adicionar cabeçalho ao PDF
                if pdf_path and os.path.exists(pdf_path):
                    add_document_header(pdf_path, doc_id, doc_tipo)
                    pdfs_documentos.append(pdf_path)
                    processados += 1
                    logger.debug(f"Documento {doc_id} processado com sucesso")
                
                # Verificar timeout global após cada documento
                if time.time() - start_time > GLOBAL_TIMEOUT:
                    logger.warning(f"Timeout global atingido após processar documento {doc_id}")
                    break
                    
            except Exception as e:
                logger.error(f"Erro ao processar documento {doc_id}: {str(e)}")
                erros += 1
                if time.time() - start_time > GLOBAL_TIMEOUT:
                    break
        
        # Mesclar PDFs criados
        try:
            with PdfMerger() as merger:
                merger.append(output_path)  # Cabeçalho
                
                for pdf in pdfs_documentos:
                    if os.path.exists(pdf):
                        try:
                            merger.append(pdf)
                        except Exception as e:
                            logger.error(f"Erro ao adicionar PDF ao merger: {str(e)}")
                
                # Salvar resultado final
                final_path = os.path.join(temp_dir, f"processo_{num_processo}_completo.pdf")
                with open(final_path, 'wb') as f:
                    merger.write(f)
                
                # Substituir arquivo principal e remover temporários
                os.replace(final_path, output_path)
                for pdf in pdfs_documentos:
                    try:
                        if os.path.exists(pdf):
                            os.remove(pdf)
                    except:
                        pass
        except Exception as e:
            logger.error(f"Erro ao mesclar PDFs: {str(e)}")
        
        # Adicionar página final com informações
        try:
            info = {
                'processo': num_processo,
                'documentos_processados': f"{processados}/{len(documentos)}",
                'erros': erros,
                'limite': limite_docs,
                'tempo': f"{time.time() - start_time:.2f}s"
            }
            adicionar_pagina_info(output_path, info)
        except Exception as e:
            logger.warning(f"Erro ao adicionar página de informações: {str(e)}")
        
        logger.info(f"PDF gerado com sucesso em {time.time() - start_time:.2f}s. "
                   f"Processados: {processados}/{len(documentos)} documentos")
        
        return output_path
        
    except Exception as e:
        logger.error(f"Erro ao gerar PDF completo: {str(e)}")
        
        if temp_dir:
            return gerar_pdf_informativo(temp_dir, num_processo, 
                                         f"Erro geral: {str(e)}")
        return None

def create_text_pdf(text, output_path, doc_id, doc_type):
    """
    Cria um PDF simples a partir de texto.
    """
    c = canvas.Canvas(output_path, pagesize=letter)
    width, height = letter
    
    # Título
    c.setFont("Helvetica-Bold", 12)
    c.drawString(72, height - 36, f"Documento {doc_id} - {doc_type}")
    c.line(72, height - 40, width - 72, height - 40)
    
    # Texto
    c.setFont("Helvetica", 10)
    y = height - 72
    
    # Quebrar texto em linhas
    for paragraph in text.split('\n'):
        words = paragraph.split()
        if not words:
            y -= 12
            continue
            
        current_line = words[0]
        for word in words[1:]:
            if c.stringWidth(current_line + ' ' + word, "Helvetica", 10) < width - 144:
                current_line += ' ' + word
            else:
                c.drawString(72, y, current_line)
                y -= 12
                if y < 72:
                    c.showPage()
                    c.setFont("Helvetica", 10)
                    y = height - 36
                current_line = word
                
        c.drawString(72, y, current_line)
        y -= 12
        
        if y < 72:
            c.showPage()
            c.setFont("Helvetica", 10)
            y = height - 36
    
    c.save()

def create_info_pdf(message, output_path, doc_id, doc_type):
    """
    Cria um PDF informativo.
    """
    c = canvas.Canvas(output_path, pagesize=letter)
    width, height = letter
    
    # Título
    c.setFont("Helvetica-Bold", 14)
    c.drawString(72, height - 72, f"Informação - Documento {doc_id}")
    
    # Subtítulo
    c.setFont("Helvetica-Bold", 12)
    c.drawString(72, height - 100, f"Tipo: {doc_type}")
    
    # Mensagem
    c.setFont("Helvetica", 10)
    y = height - 130
    
    # Quebrar mensagem em linhas
    for paragraph in message.split('\n'):
        words = paragraph.split()
        if not words:
            y -= 14
            continue
            
        current_line = words[0]
        for word in words[1:]:
            if c.stringWidth(current_line + ' ' + word, "Helvetica", 10) < width - 144:
                current_line += ' ' + word
            else:
                c.drawString(72, y, current_line)
                y -= 14
                if y < 72:
                    c.showPage()
                    c.setFont("Helvetica", 10)
                    y = height - 36
                current_line = word
                
        c.drawString(72, y, current_line)
        y -= 14
        
        if y < 72:
            c.showPage()
            c.setFont("Helvetica", 10)
            y = height - 36
    
    c.save()

def add_document_header(pdf_path, doc_id, doc_type):
    """
    Adiciona um cabeçalho ao PDF.
    """
    try:
        # Ler o PDF original
        with open(pdf_path, 'rb') as input_file:
            reader = PdfReader(input_file)
            
            # Criar um novo PDF
            output = os.path.join(os.path.dirname(pdf_path), f"temp_{os.path.basename(pdf_path)}")
            c = canvas.Canvas(output, pagesize=letter)
            
            # Obter as dimensões
            page_width, page_height = letter
            
            # Para cada página
            for i in range(len(reader.pages)):
                page = reader.pages[i]
                
                # Copiar conteúdo da página (usando um truque: salvamos como PDF e recarregamos)
                packet = io.BytesIO()
                c = canvas.Canvas(packet, pagesize=letter)
                
                # Adicionar cabeçalho
                c.setFont("Helvetica-Bold", 10)
                c.drawString(72, page_height - 20, f"Documento {doc_id} - {doc_type} - Página {i+1}")
                c.line(72, page_height - 24, page_width - 72, page_height - 24)
                
                c.save()
                
                # Mover para a próxima página
                packet.seek(0)
                overlay = PdfReader(packet)
                page.merge_page(overlay.pages[0])
            
            # Salvar o resultado usando PdfWriter
            from PyPDF2 import PdfWriter
            writer = PdfWriter()
            
            for page in reader.pages:
                writer.add_page(page)
                
            with open(output, 'wb') as f:
                writer.write(f)
                
            # Substituir o arquivo original
            os.replace(output, pdf_path)
            
    except Exception as e:
        logger.error(f"Erro ao adicionar cabeçalho: {str(e)}")

def gerar_cabecalho_processo(dados, documentos_selecionados=None):
    """
    Gera um PDF com dados básicos do processo.
    """
    buffer = io.BytesIO()
    
    # Criar PDF direto
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    
    # Título
    c.setFont("Helvetica-Bold", 16)
    c.drawString(72, height - 72, f"PROCESSO {dados.get('numero', 'N/A')}")
    
    # Informações
    c.setFont("Helvetica-Bold", 12)
    c.drawString(72, height - 100, "INFORMAÇÕES DO PROCESSO")
    
    # Dados
    c.setFont("Helvetica", 10)
    y = height - 120
    infos = [
        f"Data de Distribuição: {dados.get('dataDistribuicao', 'N/A')}",
        f"Classe: {dados.get('classe', 'N/A')}",
        f"Valor da Causa: {dados.get('valorCausa', 'N/A')}",
        f"Órgão Julgador: {dados.get('orgaoJulgador', 'N/A')}",
        f"Comarca: {dados.get('comarca', 'N/A')}"
    ]
    
    for info in infos:
        c.drawString(72, y, info)
        y -= 14
    
    y -= 10
    
    # Partes
    if dados.get('polos'):
        c.setFont("Helvetica-Bold", 12)
        c.drawString(72, y, "PARTES DO PROCESSO")
        y -= 20
        
        for polo in dados.get('polos', []):
            polo_nome = polo.get('polo', 'N/A')
            c.setFont("Helvetica-Bold", 10)
            c.drawString(72, y, f"{polo_nome}:")
            y -= 14
            
            c.setFont("Helvetica", 10)
            for parte in polo.get('partes', []):
                nome_parte = parte.get('nome', 'N/A')
                c.drawString(90, y, f"- {nome_parte}")
                y -= 14
            
            y -= 6
    
    # Documentos
    if documentos_selecionados:
        y = max(y, 200)  # Garantir espaço mínimo
        
        c.setFont("Helvetica-Bold", 12)
        c.drawString(72, y, "DOCUMENTOS INCLUÍDOS NO PDF")
        y -= 20
        
        c.setFont("Helvetica", 10)
        for i, doc in enumerate(documentos_selecionados, 1):
            doc_id = doc.get('id', 'N/A')
            doc_tipo = doc.get('tipoDocumento', 'N/A')
            c.drawString(90, y, f"{i}. {doc_tipo} (ID: {doc_id})")
            y -= 14
            
            if y < 72:
                c.showPage()
                c.setFont("Helvetica", 10)
                y = height - 36
    
    # Observação
    c.setFont("Helvetica", 10)
    c.drawString(72, 36, f"PDF gerado em: {time.strftime('%d/%m/%Y %H:%M:%S')}")
    
    c.save()
    buffer.seek(0)
    
    return buffer

def adicionar_pagina_info(pdf_path, info_dict):
    """
    Adiciona página com informações sobre o processamento.
    """
    try:
        # Abrir o PDF original
        with open(pdf_path, 'rb') as f:
            reader = PdfReader(f)
            
            # Criar página de informações
            info_buffer = io.BytesIO()
            c = canvas.Canvas(info_buffer, pagesize=letter)
            width, height = letter
            
            # Título
            c.setFont("Helvetica-Bold", 14)
            c.drawString(72, height - 72, "Informações de Processamento")
            
            # Dados
            c.setFont("Helvetica", 12)
            y = height - 100
            
            for key, value in info_dict.items():
                c.drawString(72, y, f"{key}: {value}")
                y -= 20
            
            c.drawString(72, 36, f"Gerado em: {time.strftime('%d/%m/%Y %H:%M:%S')}")
            
            c.save()
            info_buffer.seek(0)
            
            # Usar PyPDF2 para adicionar a página
            info_pdf = PdfReader(info_buffer)
            
            writer = PdfMerger()
            writer.append(reader)
            writer.append(info_pdf)
            
            # Salvar resultado
            output = pdf_path + ".tmp"
            with open(output, 'wb') as f:
                writer.write(f)
            
            # Substituir original
            os.replace(output, pdf_path)
            
    except Exception as e:
        logger.error(f"Erro ao adicionar página de informações: {str(e)}")

def gerar_pdf_informativo(temp_dir, num_processo, mensagem):
    """
    Gera um PDF informativo para erros.
    """
    output_path = os.path.join(temp_dir, f"erro_{num_processo}.pdf")
    
    c = canvas.Canvas(output_path, pagesize=letter)
    width, height = letter
    
    # Título
    c.setFont("Helvetica-Bold", 16)
    c.drawString(72, height - 72, f"Erro ao Processar: {num_processo}")
    
    # Linha separadora
    c.line(72, height - 80, width - 72, height - 80)
    
    # Mensagem
    c.setFont("Helvetica", 12)
    y = height - 100
    
    # Quebrar a mensagem em linhas
    for paragraph in mensagem.split('\n'):
        words = paragraph.split()
        if not words:
            y -= 14
            continue
            
        current_line = words[0]
        for word in words[1:]:
            if c.stringWidth(current_line + ' ' + word, "Helvetica", 12) < width - 144:
                current_line += ' ' + word
            else:
                c.drawString(72, y, current_line)
                y -= 16
                if y < 72:
                    c.showPage()
                    c.setFont("Helvetica", 12)
                    y = height - 36
                current_line = word
                
        c.drawString(72, y, current_line)
        y -= 16
        
        if y < 72:
            c.showPage()
            c.setFont("Helvetica", 12)
            y = height - 36
    
    # Data e hora
    c.setFont("Helvetica", 10)
    c.drawString(72, 36, f"Gerado em: {time.strftime('%d/%m/%Y %H:%M:%S')}")
    
    c.save()
    
    return output_path
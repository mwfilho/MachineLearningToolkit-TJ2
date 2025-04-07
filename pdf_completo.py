"""
Módulo para geração de PDFs completos de processos, utilizando uma abordagem mais robusta
e otimizada para o ambiente Replit.
"""

import os
import tempfile
import time
import logging
import io
from PyPDF2 import PdfMerger, PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from funcoes_mni import retorna_processo, retorna_documento_processo
from utils import extract_mni_data

# Configurar logging
logger = logging.getLogger(__name__)

# Configurações
MAX_DOCS = 3  # Limite máximo de documentos por padrão para Replit
DOCUMENTO_TIMEOUT = 5  # Timeout por documento em segundos
GLOBAL_TIMEOUT = 20  # Timeout total do processo em segundos

def gerar_pdf_completo(num_processo, cpf, senha, limite_docs=None):
    """
    Gera um PDF completo contendo todos os documentos de um processo judicial.
    Implementação otimizada para o ambiente Replit.

    Args:
        num_processo (str): Número do processo judicial
        cpf (str): CPF/CNPJ do consultante
        senha (str): Senha do consultante
        limite_docs (int, optional): Limite de documentos a processar. Se None, usa o valor padrão.
        
    Returns:
        str: Caminho para o PDF gerado ou None em caso de erro
    """
    start_time = time.time()
    temp_dir = None
    
    try:
        # Aplicar limite de documentos
        if not limite_docs or limite_docs > MAX_DOCS:
            limite_docs = MAX_DOCS
            logger.warning(f"Limitando a {MAX_DOCS} documentos para melhor desempenho")
        
        # Criar diretório temporário
        temp_dir = tempfile.mkdtemp()
        logger.debug(f"Diretório temporário criado: {temp_dir}")
        
        # Consultar o processo
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
                                        "O processo não possui documentos acessíveis ou você não tem permissão para acessá-los.")
        
        # Limitando aos primeiros documentos conforme solicitado
        documentos = documentos[:limite_docs]
        logger.info(f"Processando {len(documentos)} documentos")
        
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
        
        # Para cada documento
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
                
                # Converter para PDF conforme o tipo
                if mimetype == 'application/pdf':
                    # Já é PDF, salvar diretamente
                    pdf_path = f"{arquivo_temp}.pdf"
                    with open(pdf_path, 'wb') as f:
                        f.write(conteudo)
                    
                    # Verificar se o PDF é válido
                    try:
                        with open(pdf_path, 'rb') as f:
                            reader = PdfReader(f)
                            if len(reader.pages) == 0:
                                logger.warning(f"PDF sem páginas: {pdf_path}")
                                raise ValueError("PDF sem páginas")
                    except Exception as e:
                        logger.warning(f"PDF inválido, convertendo para texto: {str(e)}")
                        # PDF inválido, tentar converter para texto
                        text = None
                        try:
                            text = conteudo.decode('utf-8', errors='ignore')
                        except:
                            text = str(conteudo)
                        
                        create_text_pdf(text, pdf_path, doc_id, doc_tipo)
                        
                elif mimetype == 'text/html':
                    # Converter HTML para PDF
                    html_path = f"{arquivo_temp}.html"
                    pdf_path = f"{arquivo_temp}.pdf"
                    
                    with open(html_path, 'wb') as f:
                        f.write(conteudo)
                    
                    # Tentar 2 abordagens para converter HTML para PDF
                    success = False
                    
                    # Primeira tentativa: usar WeasyPrint
                    try:
                        import weasyprint
                        html = weasyprint.HTML(filename=html_path)
                        html.write_pdf(pdf_path)
                        logger.debug(f"Arquivo HTML convertido para PDF com WeasyPrint: {pdf_path}")
                        success = True
                    except Exception as e:
                        logger.warning(f"Erro ao converter HTML para PDF com WeasyPrint: {str(e)}")
                        
                    # Segunda tentativa: extrair texto e criar PDF simples
                    if not success:
                        try:
                            with open(html_path, 'r', encoding='utf-8', errors='ignore') as f:
                                html_content = f.read()
                            
                            # Criar PDF simples com o texto do HTML
                            create_text_pdf(html_content, pdf_path, doc_id, doc_tipo)
                            logger.debug(f"Arquivo HTML convertido para PDF como texto: {pdf_path}")
                            success = True
                        except Exception as ex:
                            logger.error(f"Erro ao criar PDF a partir do texto HTML: {str(ex)}")
                            error_pdf = os.path.join(temp_dir, f"doc_{doc_id}_erro_html.pdf")
                            create_info_pdf(f"Erro ao converter HTML para PDF: {str(ex)}", 
                                          error_pdf, doc_id, doc_tipo)
                            pdf_path = error_pdf
                            erros += 1
                            
                elif mimetype in ['text/plain', 'text/xml', 'application/xml']:
                    # Converter texto para PDF
                    try:
                        text = conteudo.decode('utf-8', errors='ignore')
                        pdf_path = f"{arquivo_temp}.pdf"
                        create_text_pdf(text, pdf_path, doc_id, doc_tipo)
                    except Exception as e:
                        logger.error(f"Erro ao converter texto para PDF: {str(e)}")
                        error_pdf = os.path.join(temp_dir, f"doc_{doc_id}_erro_texto.pdf")
                        create_info_pdf(f"Erro ao converter texto para PDF: {str(e)}", 
                                      error_pdf, doc_id, doc_tipo)
                        pdf_path = error_pdf
                        erros += 1
                        
                else:
                    # Outros tipos: criar PDF informativo
                    pdf_path = f"{arquivo_temp}.pdf"
                    message = f"Documento {doc_id} do tipo {doc_tipo}\nFormato: {mimetype}\n"
                    message += f"Conteúdo binário não pode ser exibido diretamente."
                    create_info_pdf(message, pdf_path, doc_id, doc_tipo)
                
                # Adicionar cabeçalho ao PDF
                if pdf_path and os.path.exists(pdf_path):
                    add_document_header(pdf_path, doc_id, doc_tipo)
                    pdfs_documentos.append(pdf_path)
                    processados += 1
                    logger.debug(f"Documento {doc_id} processado com sucesso")
                else:
                    raise Exception("Falha ao gerar PDF")
                    
            except Exception as e:
                logger.error(f"Erro geral ao processar documento {doc_id}: {str(e)}")
                error_pdf = os.path.join(temp_dir, f"doc_{doc_id}_erro_geral.pdf")
                create_info_pdf(f"Erro ao processar documento {doc_id}: {str(e)}", 
                              error_pdf, doc_id, doc_tipo)
                pdfs_documentos.append(error_pdf)
                erros += 1
        
        # Mesclar todos os PDFs
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
                temp_pdf = os.path.join(temp_dir, f"final_merged.pdf")
                with open(temp_pdf, 'wb') as f:
                    merger.write(f)
                
                # Substituir arquivo principal
                os.replace(temp_pdf, output_path)
                
                # Limpar PDFs individuais
                for pdf in pdfs_documentos:
                    if os.path.exists(pdf):
                        try:
                            os.remove(pdf)
                        except:
                            pass
        except Exception as e:
            logger.error(f"Erro ao mesclar PDFs: {str(e)}")
            # Se falhou ao mesclar, ainda tenta retornar o cabeçalho
        
        # Adicionar página final com informações
        try:
            adicionar_pagina_info(output_path, {
                'processo': num_processo,
                'documentos_solicitados': len(documentos),
                'documentos_processados': processados,
                'erros': erros,
                'limite_imposto': limite_docs,
                'tempo_total': f"{time.time() - start_time:.2f} segundos"
            })
        except Exception as e:
            logger.warning(f"Erro ao adicionar página de informações: {str(e)}")
        
        logger.info(f"PDF gerado com sucesso em {time.time() - start_time:.2f}s. "
                   f"Processados: {processados}/{len(documentos)} documentos")
        
        return output_path
        
    except Exception as e:
        logger.error(f"Erro ao gerar PDF completo: {str(e)}")
        
        if temp_dir:
            return gerar_pdf_informativo(temp_dir, num_processo, 
                                         f"Erro ao gerar PDF completo: {str(e)}")
        return None

def create_text_pdf(text, output_path, doc_id, doc_type):
    """
    Cria um PDF a partir de texto.
    
    Args:
        text (str): Texto a ser convertido
        output_path (str): Caminho para salvar o PDF
        doc_id (str): ID do documento
        doc_type (str): Tipo do documento
    """
    # Criar um novo PDF
    c = canvas.Canvas(output_path, pagesize=letter)
    width, height = letter
    
    # Configurar metadados
    c.setTitle(f"Documento {doc_id}")
    c.setSubject(f"Tipo: {doc_type}")
    
    # Configurar fonte e tamanho
    c.setFont("Helvetica", 10)
    
    # Posição inicial
    y = height - 72  # Começar 1 polegada do topo
    
    # Limitar o texto para evitar PDFs muito grandes
    if len(text) > 500000:  # ~500KB
        text = text[:500000] + "\n\n[...TEXTO TRUNCADO POR SER MUITO LONGO...]"
    
    # Quebrar o texto em linhas
    lines = []
    for paragraph in text.split('\n'):
        if not paragraph.strip():
            lines.append('')
            continue
            
        words = paragraph.split()
        if not words:
            lines.append('')
            continue
            
        current_line = words[0]
        for word in words[1:]:
            # Verificar se a linha atual + nova palavra excede a largura
            line_width = c.stringWidth(current_line + ' ' + word, "Helvetica", 10)
            if line_width < width - 144:  # 72 pontos por polegada * 2 (margens)
                current_line += ' ' + word
            else:
                lines.append(current_line)
                current_line = word
        
        lines.append(current_line)
    
    # Desenhar linhas de texto
    for line in lines:
        if y < 72:  # Se chegou a 1 polegada do fundo da página
            c.showPage()  # Nova página
            c.setFont("Helvetica", 10)
            y = height - 72  # Resetar para o topo
        
        c.drawString(72, y, line)
        y -= 14  # Espaçamento entre linhas
        
    c.showPage()
    c.save()

def create_info_pdf(message, output_path, doc_id, doc_type):
    """
    Cria um PDF informativo quando o tipo de arquivo não é suportado.
    
    Args:
        message (str): Mensagem a ser incluída no PDF
        output_path (str): Caminho para salvar o PDF
        doc_id (str): ID do documento
        doc_type (str): Tipo do documento
    """
    # Criar um novo PDF
    c = canvas.Canvas(output_path, pagesize=letter)
    width, height = letter
    
    # Configurar metadados
    c.setTitle(f"Informação - Documento {doc_id}")
    c.setSubject(f"Tipo: {doc_type}")
    
    # Título 
    c.setFont("Helvetica-Bold", 14)
    c.drawString(72, height - 72, f"Informação sobre o Documento {doc_id}")
    
    # Tipo de documento
    c.setFont("Helvetica-Bold", 12)
    c.drawString(72, height - 100, f"Tipo: {doc_type}")
    
    # Mensagem
    c.setFont("Helvetica", 10)
    y = height - 130
    
    # Quebrar a mensagem em linhas
    lines = []
    for paragraph in message.split('\n'):
        words = paragraph.split()
        if not words:
            lines.append('')
            continue
            
        current_line = words[0]
        for word in words[1:]:
            line_width = c.stringWidth(current_line + ' ' + word, "Helvetica", 10)
            if line_width < width - 144:
                current_line += ' ' + word
            else:
                lines.append(current_line)
                current_line = word
        
        lines.append(current_line)
    
    # Desenhar linhas de texto
    for line in lines:
        c.drawString(72, y, line)
        y -= 14
        
        if y < 72:  # Se chegou a 1 polegada do fundo da página
            c.showPage()
            c.setFont("Helvetica", 10)
            y = height - 72
    
    c.showPage()
    c.save()

def add_document_header(pdf_path, doc_id, doc_type):
    """
    Adiciona um cabeçalho com informações ao PDF existente.
    
    Args:
        pdf_path (str): Caminho do PDF a ser modificado
        doc_id (str): ID do documento
        doc_type (str): Tipo do documento
    """
    try:
        # Ler o PDF original
        with open(pdf_path, 'rb') as input_file:
            reader = PdfReader(input_file)
            writer = PdfWriter()
            
            # Criar uma página de cabeçalho
            packet = io.BytesIO()
            c = canvas.Canvas(packet, pagesize=letter)
            
            # Adicionar informações do documento
            c.setFont("Helvetica-Bold", 12)
            c.drawString(72, 750, f"Documento: {doc_id}")
            c.drawString(72, 730, f"Tipo: {doc_type}")
            c.drawString(72, 710, "=" * 80)
            
            c.save()
            
            # Adicionar cabeçalho em cada página
            packet.seek(0)
            header = PdfReader(packet)
            header_page = header.pages[0]
            
            # Adicionar todas as páginas
            for i in range(len(reader.pages)):
                page = reader.pages[i]
                page.merge_page(header_page)
                writer.add_page(page)
            
            # Salvar o resultado
            with open(pdf_path + ".tmp", 'wb') as output_file:
                writer.write(output_file)
            
            # Substituir o arquivo original
            os.replace(pdf_path + ".tmp", pdf_path)
            
    except Exception as e:
        logger.error(f"Erro ao adicionar cabeçalho ao PDF: {str(e)}")

def get_extension_for_mimetype(mimetype):
    """Helper para obter a extensão apropriada para um mimetype"""
    extension_map = {
        'application/pdf': '.pdf',
        'text/html': '.html',
        'text/plain': '.txt',
        'text/xml': '.xml',
        'application/xml': '.xml',
        'image/jpeg': '.jpg',
        'image/png': '.png',
        'application/zip': '.zip',
        'application/msword': '.doc',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document': '.docx',
    }
    return extension_map.get(mimetype, '.bin')

def gerar_cabecalho_processo(dados, documentos_selecionados=None):
    """
    Gera um PDF contendo informações básicas do processo como cabeçalho.
    Usa abordagem mais simples para evitar problemas com fontes e formatação.
    
    Args:
        dados (dict): Dados do processo
        documentos_selecionados (list, opcional): Lista de documentos que serão incluídos
        
    Returns:
        io.BytesIO: Buffer com o PDF gerado
    """
    buffer = io.BytesIO()
    
    # Criar PDF usando canvas diretamente - mais estável
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    
    # Posição inicial
    y = height - 60
    
    # Título
    c.setFont("Helvetica-Bold", 16)
    c.drawString(60, y, f"PROCESSO {dados.get('numero', 'N/A')}")
    y -= 30
    
    # Informações gerais
    c.setFont("Helvetica-Bold", 12)
    c.drawString(60, y, "INFORMAÇÕES GERAIS")
    y -= 20
    
    c.setFont("Helvetica", 10)
    informacoes = [
        f"Data de Distribuição: {dados.get('dataDistribuicao', 'N/A')}",
        f"Classe: {dados.get('classe', 'N/A')}",
        f"Valor da Causa: {dados.get('valorCausa', 'N/A')}",
        f"Órgão Julgador: {dados.get('orgaoJulgador', 'N/A')}",
        f"Comarca: {dados.get('comarca', 'N/A')}",
    ]
    
    for info in informacoes:
        c.drawString(60, y, info)
        y -= 15
    
    y -= 15
    
    # Assuntos
    if dados.get('assuntos'):
        c.setFont("Helvetica-Bold", 12)
        c.drawString(60, y, "ASSUNTOS")
        y -= 20
        
        c.setFont("Helvetica", 10)
        for assunto in dados.get('assuntos', []):
            c.drawString(70, y, f"- {assunto}")
            y -= 15
            
            # Verificar se precisamos de nova página
            if y < 60:
                c.showPage()
                y = height - 60
                c.setFont("Helvetica", 10)
        
        y -= 15
    
    # Polos
    if dados.get('polos'):
        c.setFont("Helvetica-Bold", 12)
        c.drawString(60, y, "PARTES DO PROCESSO")
        y -= 20
        
        for polo in dados.get('polos', []):
            polo_nome = polo.get('polo', 'N/A')
            c.setFont("Helvetica-Bold", 10)
            c.drawString(60, y, f"{polo_nome}:")
            y -= 15
            
            c.setFont("Helvetica", 10)
            for parte in polo.get('partes', []):
                nome_parte = parte.get('nome', 'N/A')
                tipo_parte = parte.get('tipo', '')
                texto_parte = f"- {nome_parte}"
                if tipo_parte:
                    texto_parte += f" ({tipo_parte})"
                c.drawString(70, y, texto_parte)
                y -= 15
                
                # Verificar se precisamos de nova página
                if y < 60:
                    c.showPage()
                    y = height - 60
                    c.setFont("Helvetica", 10)
            
            y -= 10
            
            # Verificar se precisamos de nova página
            if y < 60:
                c.showPage()
                y = height - 60
                c.setFont("Helvetica", 10)
    
    # Lista de documentos
    if documentos_selecionados:
        c.setFont("Helvetica-Bold", 12)
        c.drawString(60, y, "DOCUMENTOS INCLUÍDOS")
        y -= 20
        
        c.setFont("Helvetica", 10)
        for i, doc in enumerate(documentos_selecionados, 1):
            doc_id = doc.get('id', 'N/A')
            doc_tipo = doc.get('tipoDocumento', 'N/A')
            doc_data = doc.get('dataHora', 'N/A')
            texto = f"{i}. {doc_tipo} (ID: {doc_id}) - {doc_data}"
            
            c.drawString(70, y, texto)
            y -= 15
            
            # Verificar se precisamos de nova página
            if y < 60:
                c.showPage()
                y = height - 60
                c.setFont("Helvetica", 10)
    
    # Finalizar o PDF
    c.showPage()
    c.save()
    buffer.seek(0)
    
    return buffer

def adicionar_pagina_info(pdf_path, info_dict):
    """
    Adiciona uma página final ao PDF com informações de processamento.
    
    Args:
        pdf_path (str): Caminho do PDF a modificar
        info_dict (dict): Dicionário com informações a adicionar
    """
    try:
        # Criar uma página de informações
        packet = io.BytesIO()
        c = canvas.Canvas(packet, pagesize=letter)
        width, height = letter
        
        # Título
        c.setFont("Helvetica-Bold", 16)
        c.drawString(72, height - 72, "Informações de Processamento")
        
        # Dados
        c.setFont("Helvetica", 12)
        y = height - 100
        
        for key, value in info_dict.items():
            c.drawString(72, y, f"{key}: {value}")
            y -= 20
        
        c.save()
        
        # Adicionar a página ao PDF existente
        packet.seek(0)
        info_pdf = PdfReader(packet)
        
        with open(pdf_path, 'rb') as f:
            existing_pdf = PdfReader(f)
            writer = PdfWriter()
            
            # Adicionar todas as páginas existentes
            for page in existing_pdf.pages:
                writer.add_page(page)
            
            # Adicionar a página de informações
            writer.add_page(info_pdf.pages[0])
            
            # Salvar o resultado
            with open(pdf_path + ".tmp", 'wb') as output_file:
                writer.write(output_file)
            
            # Substituir o arquivo original
            os.replace(pdf_path + ".tmp", pdf_path)
            
    except Exception as e:
        logger.error(f"Erro ao adicionar página de informações: {str(e)}")

def gerar_pdf_informativo(temp_dir, num_processo, mensagem):
    """
    Gera um PDF informativo quando ocorre um erro no processamento.
    
    Args:
        temp_dir (str): Diretório temporário
        num_processo (str): Número do processo
        mensagem (str): Mensagem de erro
        
    Returns:
        str: Caminho para o PDF gerado
    """
    output_path = os.path.join(temp_dir, f"erro_processo_{num_processo}.pdf")
    
    # Criar um novo PDF
    c = canvas.Canvas(output_path, pagesize=letter)
    width, height = letter
    
    # Título
    c.setFont("Helvetica-Bold", 16)
    c.drawString(72, height - 72, f"Erro ao Processar: {num_processo}")
    
    # Linha separadora
    c.line(72, height - 80, width - 72, height - 80)
    
    # Mensagem de erro
    c.setFont("Helvetica", 12)
    y = height - 100
    
    # Quebrar a mensagem em linhas
    lines = []
    for paragraph in mensagem.split('\n'):
        words = paragraph.split()
        if not words:
            lines.append('')
            continue
            
        current_line = words[0]
        for word in words[1:]:
            line_width = c.stringWidth(current_line + ' ' + word, "Helvetica", 12)
            if line_width < width - 144:
                current_line += ' ' + word
            else:
                lines.append(current_line)
                current_line = word
        
        lines.append(current_line)
    
    # Desenhar linhas de texto
    for line in lines:
        c.drawString(72, y, line)
        y -= 16
        
        if y < 72:  # Se chegou a 1 polegada do fundo da página
            c.showPage()
            c.setFont("Helvetica", 12)
            y = height - 72
    
    # Data e hora
    c.setFont("Helvetica", 10)  # Usando fonte padrão em vez de itálico
    c.drawString(72, 36, f"Gerado em: {time.strftime('%d/%m/%Y %H:%M:%S')}")
    
    c.save()
    
    return output_path
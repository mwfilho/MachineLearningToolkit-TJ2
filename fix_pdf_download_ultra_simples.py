"""
Versão ultra simplificada para geração de PDF, otimizada para o ambiente Replit.
Sem threads, sem processos, com timeouts agressivos para cada operação.
"""

import os
import tempfile
import time
import logging
import io
import base64
from PyPDF2 import PdfMerger, PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter

# Configurar logging
logger = logging.getLogger(__name__)

# Configuração
MAX_DOCS = 5  # Limite máximo de documentos (independente do que for solicitado)
DOCUMENTO_TIMEOUT = 5  # Timeout por documento em segundos
GLOBAL_TIMEOUT = 15  # Timeout total do processo em segundos

def gerar_pdf_ultra_simples(num_processo, cpf, senha, limite_docs=None):
    """
    Versão extremamente simplificada para gerar PDF com documentos de um processo.
    Limitada a um número pequeno de documentos e com timeouts agressivos.
    
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
        # Aplicar limite máximo de documentos
        if not limite_docs or limite_docs > MAX_DOCS:
            limite_docs = MAX_DOCS
            logger.warning(f"Limitando a {MAX_DOCS} documentos para garantir desempenho")
        
        # Criar diretório temporário
        temp_dir = tempfile.mkdtemp()
        logger.debug(f"Diretório temporário criado: {temp_dir}")
        
        # Importar aqui para evitar circular imports
        from funcoes_mni import retorna_processo, retorna_documento_processo
        from utils import extract_mni_data
        
        # Consultar o processo com timeout
        logger.debug(f"Consultando processo {num_processo}")
        
        # Verificar se já passou do timeout global
        if time.time() - start_time > GLOBAL_TIMEOUT:
            logger.error("Timeout global atingido antes de consultar o processo")
            return gerar_pdf_informativo(temp_dir, num_processo, "Timeout global atingido")
        
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
        
        # Limitando aos primeiros documentos
        documentos = documentos[:limite_docs]
        logger.info(f"Buscando {len(documentos)} documentos")
        
        # Gerar o cabeçalho do processo
        output_path = os.path.join(temp_dir, f"processo_{num_processo}.pdf")
        cabecalho_buffer = gerar_cabecalho_processo(dados, documentos)
        
        with open(output_path, 'wb') as f:
            cabecalho_buffer.seek(0)
            f.write(cabecalho_buffer.getvalue())
        
        # Processar documentos individualmente com timeout estrito
        processados = 0
        erros = 0
        pdfs_documentos = []
        
        # Para cada documento, tentar processar com timeout
        for i, doc in enumerate(documentos, 1):
            # Verificar se já passou do timeout global
            if time.time() - start_time > GLOBAL_TIMEOUT:
                logger.warning(f"Timeout global atingido após processar {processados} documentos")
                break
                
            doc_id = doc.get('id')
            doc_tipo = doc.get('tipoDocumento', 'Documento')
            
            logger.debug(f"Processando documento {i}/{len(documentos)}: {doc_id} ({doc_tipo})")
            
            try:
                # Timeout por documento
                doc_start_time = time.time()
                doc_timeout = False
                
                # Fazer o download com timeout controlado
                resposta_doc = None
                try:
                    resposta_doc = retorna_documento_processo(num_processo, doc_id, cpf=cpf, senha=senha)
                    if time.time() - doc_start_time > DOCUMENTO_TIMEOUT:
                        doc_timeout = True
                        logger.warning(f"Documento {doc_id} atingiu timeout ({DOCUMENTO_TIMEOUT}s)")
                except Exception as e:
                    logger.error(f"Erro ao obter documento {doc_id}: {str(e)}")
                    error_pdf = os.path.join(temp_dir, f"doc_{doc_id}_erro.pdf")
                    create_info_pdf(f"Erro ao baixar documento {doc_id}: {str(e)}", 
                                  error_pdf, doc_id, doc_tipo)
                    pdfs_documentos.append(error_pdf)
                    erros += 1
                    continue
                    
                # Verificar timeout
                if doc_timeout or not resposta_doc:
                    logger.warning(f"Timeout ou erro ao baixar documento {doc_id}")
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
                
                # Processar o documento conforme seu tipo, com timeout estrito
                mimetype = resposta_doc.get('mimetype', '')
                conteudo = resposta_doc.get('conteudo', b'')
                
                # Caminho para o arquivo temporário
                arquivo_temp = os.path.join(temp_dir, f"doc_{doc_id}")
                pdf_path = None
                
                # Converter para PDF conforme o tipo (com timeout)
                try:
                    if mimetype == 'application/pdf':
                        # Já é PDF, salvar diretamente
                        pdf_path = f"{arquivo_temp}.pdf"
                        with open(pdf_path, 'wb') as f:
                            f.write(conteudo)
                    elif mimetype in ['text/plain', 'text/xml', 'text/html']:
                        # Converter texto para PDF
                        pdf_path = f"{arquivo_temp}.pdf"
                        texto = conteudo.decode('utf-8', errors='ignore')
                        # Limitar tamanho do texto para evitar timeout
                        if len(texto) > 50000:  # Limitar a ~50KB
                            texto = texto[:50000] + "\n\n[...TEXTO TRUNCADO POR SER MUITO LONGO...]"
                        create_text_pdf(texto, pdf_path, doc_id, doc_tipo)
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
                    logger.error(f"Erro ao processar documento {doc_id}: {str(e)}")
                    error_pdf = os.path.join(temp_dir, f"doc_{doc_id}_erro_processamento.pdf")
                    create_info_pdf(f"Erro ao processar documento {doc_id}: {str(e)}", 
                                  error_pdf, doc_id, doc_tipo)
                    pdfs_documentos.append(error_pdf)
                    erros += 1
                
                # Verificar novamente timeout global
                if time.time() - start_time > GLOBAL_TIMEOUT:
                    logger.warning(f"Timeout global atingido durante processamento do documento {doc_id}")
                    break
                    
            except Exception as e:
                logger.error(f"Erro geral ao processar documento {doc_id}: {str(e)}")
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
        
        # Adicionar página final com informações de processamento
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
    Cria um PDF a partir de texto, com limite de tamanho.
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
    
    # Limitar o número de linhas para evitar PDFs muito grandes
    max_lines = 500  # Limite bem conservador
    lines = []
    
    # Quebrar o texto em linhas
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
        
        # Verificar limite de linhas durante o processamento
        if len(lines) > max_lines:
            lines.append("")
            lines.append("..." + " [Texto truncado por ser muito longo]")
            break
    
    # Desenhar linhas de texto
    for line in lines:
        if y < 72:  # Se chegou a 1 polegada do fundo da página
            c.showPage()  # Nova página
            c.setFont("Helvetica", 10)
            y = height - 72  # Resetar para o topo
        
        c.drawString(72, y, line)
        y -= 14  # Espaçamento entre linhas
        
        # Limitar o número de páginas
        if c.getPageNumber() > 10:  # No máximo 10 páginas por documento
            c.showPage()
            c.setFont("Helvetica", 10)
            c.drawString(72, height - 72, "[Documento truncado por ser muito longo]")
            break
    
    c.showPage()
    c.save()

def create_info_pdf(message, output_path, doc_id, doc_type):
    """
    Cria um PDF informativo quando o tipo de arquivo não é suportado.
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
        if not paragraph:
            lines.append('')
            continue
            
        words = paragraph.split()
        if not words:
            lines.append('')
            continue
            
        current_line = words[0]
        for word in words[1:]:
            # Verificar se a linha atual + nova palavra excede a largura
            if c.stringWidth(current_line + ' ' + word, "Helvetica", 10) < width - 144:
                current_line += ' ' + word
            else:
                lines.append(current_line)
                current_line = word
        
        lines.append(current_line)
    
    # Desenhar mensagem
    for line in lines:
        c.drawString(72, y, line)
        y -= 14
        
        if y < 72:  # Se chegou a 1 polegada do fundo da página
            c.showPage()
            c.setFont("Helvetica", 10)
            y = height - 72
    
    # Adicionar nota de rodapé
    c.drawString(72, 40, "PDF gerado automaticamente pelo sistema de consulta processual")
    c.drawString(72, 25, f"Data/Hora: {time.strftime('%d/%m/%Y %H:%M:%S')}")
    
    c.showPage()
    c.save()

def add_document_header(pdf_path, doc_id, doc_type):
    """
    Adiciona um cabeçalho com informações ao PDF existente.
    """
    try:
        # Ler o PDF existente
        reader = PdfReader(pdf_path)
        writer = PdfWriter()
        
        # Preparar cabeçalho
        packet = io.BytesIO()
        c = canvas.Canvas(packet, pagesize=letter)
        width, height = letter
        
        # Desenhar cabeçalho na parte superior
        c.setFont("Helvetica-Bold", 10)
        c.drawString(72, height - 40, f"Documento: {doc_id}")
        c.drawString(72, height - 55, f"Tipo: {doc_type}")
        c.drawString(72, height - 70, f"Data de download: {time.strftime('%d/%m/%Y %H:%M:%S')}")
        
        # Linha separadora
        c.line(72, height - 80, width - 72, height - 80)
        
        c.save()
        
        # Mover para o início do buffer
        packet.seek(0)
        watermark = PdfReader(packet)
        
        # Limitar o número de páginas processadas
        max_pages = 20  # Limitar a 20 páginas por documento
        num_pages = min(len(reader.pages), max_pages)
        
        # Adicionar cabeçalho a cada página
        for i in range(num_pages):
            page = reader.pages[i]
            watermark_page = watermark.pages[0]
            page.merge_page(watermark_page)
            writer.add_page(page)
            
        # Se o documento foi truncado
        if len(reader.pages) > max_pages:
            # Adicionar uma página informando o truncamento
            packet = io.BytesIO()
            c = canvas.Canvas(packet, pagesize=letter)
            c.setFont("Helvetica-Bold", 14)
            c.drawString(72, height - 72, "AVISO: Documento Truncado")
            c.setFont("Helvetica", 10)
            c.drawString(72, height - 100, f"Este documento possui {len(reader.pages)} páginas, mas foi limitado a {max_pages} páginas")
            c.drawString(72, height - 120, "para melhorar o desempenho do sistema.")
            c.save()
            packet.seek(0)
            truncate_page = PdfReader(packet).pages[0]
            writer.add_page(truncate_page)
        
        # Salvar o resultado
        with open(pdf_path, 'wb') as output_file:
            writer.write(output_file)
            
    except Exception as e:
        logger.warning(f"Erro ao adicionar cabeçalho ao PDF: {str(e)}")
        # Se falhar, retornar silenciosamente - o PDF original ainda é utilizável

def gerar_cabecalho_processo(dados_processo, documentos_selecionados=None):
    """
    Gera um PDF contendo informações básicas do processo como cabeçalho.
    
    Args:
        dados_processo (dict): Dados do processo
        documentos_selecionados (list, opcional): Lista de documentos que serão incluídos
        
    Returns:
        io.BytesIO: Buffer com o PDF gerado
    """
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    c.setTitle(f"Informações do Processo {dados_processo.get('processo', {}).get('numero', '')}")
    
    width, height = letter
    
    # Configurar fonte e tamanho
    c.setFont("Helvetica-Bold", 14)
    c.drawString(72, height - 72, "INFORMAÇÕES DO PROCESSO")
    
    c.setFont("Helvetica-Bold", 12)
    c.drawString(72, height - 100, f"Processo: {dados_processo.get('processo', {}).get('numero', 'N/A')}")
    
    c.setFont("Helvetica", 10)
    y = height - 130
    
    # Dados básicos
    if 'processo' in dados_processo:
        proc = dados_processo['processo']
        
        # Classe processual
        classe_desc = ''
        if proc.get('classeProcessual'):
            classe_desc = f"Classe: {proc.get('classeProcessual', 'N/A')}"
        c.drawString(72, y, classe_desc)
        y -= 15
        
        # Órgão julgador
        if proc.get('orgaoJulgador'):
            c.drawString(72, y, f"Órgão Julgador: {proc.get('orgaoJulgador', 'N/A')}")
            y -= 15
            
        # Data de ajuizamento
        if proc.get('dataAjuizamento'):
            data_str = proc.get('dataAjuizamento')
            # Formatar data se estiver no formato YYYYMMDD
            if len(data_str) == 8:
                try:
                    data_str = f"{data_str[6:8]}/{data_str[4:6]}/{data_str[0:4]}"
                except:
                    pass
            c.drawString(72, y, f"Data de Ajuizamento: {data_str}")
            y -= 25
    
    # Adicionar aviso sobre limitação
    c.setFont("Helvetica-Bold", 10)
    c.drawString(72, y, "AVISO DE LIMITAÇÃO:")
    y -= 15
    
    c.setFont("Helvetica", 10)
    c.drawString(72, y, f"Este PDF contém apenas uma seleção dos documentos do processo.")
    y -= 15
    c.drawString(72, y, f"Para visualizar todos os documentos, use o endpoint sem limite ou")
    y -= 15
    c.drawString(72, y, f"consulte os documentos individualmente.")
    y -= 25
    
    # Adicionar lista de documentos
    c.setFont("Helvetica-Bold", 12)
    c.drawString(72, y, "DOCUMENTOS INCLUÍDOS NESTE PDF:")
    y -= 20
    
    c.setFont("Helvetica", 10)
    documentos = documentos_selecionados or dados_processo.get('documentos', [])
    for i, doc in enumerate(documentos, 1):
        c.drawString(72, y, f"{i}. {doc.get('tipoDocumento', 'Documento')} (ID: {doc.get('id', 'N/A')})")
        if doc.get('dataDocumento'):
            c.drawString(350, y, f"Data: {doc.get('dataDocumento', 'N/A')}")
        y -= 15
        
        # Evitar que o texto ultrapasse a página
        if y < 72:
            c.showPage()
            c.setFont("Helvetica", 10)
            y = height - 72
    
    c.showPage()
    c.save()
    
    buffer.seek(0)
    return buffer

def adicionar_pagina_info(pdf_path, info_dict):
    """
    Adiciona uma página final ao PDF com informações de processamento.
    """
    try:
        # Criar página de informações
        packet = io.BytesIO()
        c = canvas.Canvas(packet, pagesize=letter)
        width, height = letter
        
        # Título
        c.setFont("Helvetica-Bold", 14)
        c.drawString(72, height - 72, "INFORMAÇÕES DE PROCESSAMENTO")
        
        # Dados
        c.setFont("Helvetica", 10)
        y = height - 100
        
        for key, value in info_dict.items():
            if key == 'processo':
                c.drawString(72, y, f"Processo: {value}")
            elif key == 'documentos_solicitados':
                c.drawString(72, y, f"Documentos solicitados: {value}")
            elif key == 'documentos_processados':
                c.drawString(72, y, f"Documentos processados com sucesso: {value}")
            elif key == 'erros':
                c.drawString(72, y, f"Documentos com erros: {value}")
            elif key == 'limite_imposto':
                c.drawString(72, y, f"Limite máximo de documentos: {value}")
            elif key == 'tempo_total':
                c.drawString(72, y, f"Tempo de processamento: {value}")
            else:
                c.drawString(72, y, f"{key}: {value}")
            
            y -= 20
        
        # Adicionar nota de rodapé
        c.setFont("Helvetica", 10)
        c.drawString(72, 100, "NOTA IMPORTANTE:")
        c.drawString(72, 85, "Este PDF foi gerado com limites de tempo e quantidade para garantir")
        c.drawString(72, 70, "o bom funcionamento do sistema. Alguns documentos podem estar truncados")
        c.drawString(72, 55, "ou não terem sido incluídos devido a estas limitações.")
        
        c.drawString(72, 30, f"PDF gerado em: {time.strftime('%d/%m/%Y %H:%M:%S')}")
        
        c.save()
        packet.seek(0)
        
        # Ler o PDF existente
        reader = PdfReader(pdf_path)
        writer = PdfWriter()
        
        # Copiar todas as páginas existentes
        for page in reader.pages:
            writer.add_page(page)
        
        # Adicionar a nova página de informações
        info_page = PdfReader(packet).pages[0]
        writer.add_page(info_page)
        
        # Salvar o resultado
        with open(pdf_path, 'wb') as output_file:
            writer.write(output_file)
            
    except Exception as e:
        logger.warning(f"Erro ao adicionar página de informações: {str(e)}")
        # Se falhar, o PDF original ainda está utilizável

def gerar_pdf_informativo(temp_dir, num_processo, mensagem):
    """
    Gera um PDF informativo quando ocorre um erro no processamento.
    """
    output_path = os.path.join(temp_dir, f"info_{num_processo}.pdf")
    
    c = canvas.Canvas(output_path, pagesize=letter)
    width, height = letter
    
    # Configurar metadados
    c.setTitle(f"Informação - Processo {num_processo}")
    
    # Título 
    c.setFont("Helvetica-Bold", 14)
    c.drawString(72, height - 72, f"Informação sobre o Processo {num_processo}")
    
    # Data e hora
    c.setFont("Helvetica", 10)
    c.drawString(72, height - 100, f"Data/Hora: {time.strftime('%d/%m/%Y %H:%M:%S')}")
    
    # Mensagem
    c.setFont("Helvetica-Bold", 12)
    c.drawString(72, height - 130, "Mensagem:")
    
    # Quebrar a mensagem em linhas
    c.setFont("Helvetica", 10)
    lines = mensagem.split('\n')
    y = height - 150
    
    for line in lines:
        words = line.split()
        if not words:
            y -= 14
            continue
            
        current_line = words[0]
        for word in words[1:]:
            # Verificar se a linha atual + nova palavra excede a largura
            if c.stringWidth(current_line + ' ' + word, "Helvetica", 10) < width - 144:
                current_line += ' ' + word
            else:
                c.drawString(72, y, current_line)
                y -= 14
                current_line = word
                
                # Verificar se precisa de nova página
                if y < 72:
                    c.showPage()
                    c.setFont("Helvetica", 10)
                    y = height - 72
        
        c.drawString(72, y, current_line)
        y -= 14
    
    # Adicionar instruções adicionais
    y -= 20
    c.setFont("Helvetica-Bold", 11)
    c.drawString(72, y, "Alternativas para visualizar os documentos:")
    y -= 20
    
    c.setFont("Helvetica", 10)
    c.drawString(72, y, "1. Tente baixar documentos individualmente usando o endpoint:")
    y -= 15
    c.drawString(90, y, f"/api/v1/processo/{num_processo}/documento/<id_documento>")
    y -= 15
    
    c.drawString(72, y, "2. Utilize a consulta da capa do processo para ver informações básicas:")
    y -= 15
    c.drawString(90, y, f"/api/v1/processo/{num_processo}/capa")
    y -= 15
    
    c.drawString(72, y, "3. Use o endpoint de PDF completo com um limite menor de documentos:")
    y -= 15
    c.drawString(90, y, f"/api/v1/processo/{num_processo}/pdf-completo?limite=3")
    
    # Adicionar nota de rodapé
    c.drawString(72, 40, "PDF gerado automaticamente pelo sistema de consulta processual")
    
    c.showPage()
    c.save()
    
    return output_path
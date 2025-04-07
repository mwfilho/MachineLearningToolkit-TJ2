"""
Versão simplificada para geração de PDF de processo completo.
Evita usar threads e processos para compatibilidade com Replit.
"""

import os
import tempfile
import time
import logging
import io
from PyPDF2 import PdfMerger, PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter

# Configurar logging
logger = logging.getLogger(__name__)

def gerar_pdf_completo_simples(num_processo, cpf, senha, limite_docs=None):
    """
    Versão simplificada da função para gerar PDF completo de um processo.
    Evita uso de threads e processos.
    
    Args:
        num_processo (str): Número do processo judicial
        cpf (str): CPF/CNPJ do consultante
        senha (str): Senha do consultante
        limite_docs (int, optional): Limite de documentos a processar. Se None, processa todos.
        
    Returns:
        str: Caminho para o PDF gerado ou None em caso de erro
    """
    start_time = time.time()
    temp_dir = None
    
    try:
        # Criar diretório temporário
        temp_dir = tempfile.mkdtemp()
        logger.debug(f"Diretório temporário criado: {temp_dir}")
        
        # Importar aqui para evitar circular imports
        from funcoes_mni import retorna_processo, retorna_documento_processo
        from utils import extract_mni_data
        
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
        
        total_docs = len(documentos)
        logger.info(f"Encontrados {total_docs} documentos no processo {num_processo}")
        
        # Aplicar limite se especificado
        if limite_docs and limite_docs > 0:
            documentos = documentos[:limite_docs]
            logger.info(f"Limitando a {limite_docs} documentos dos {total_docs} disponíveis")
        
        # Gerar o cabeçalho do processo
        output_path = os.path.join(temp_dir, f"processo_{num_processo}.pdf")
        cabecalho_buffer = gerar_cabecalho_processo(dados)
        
        with open(output_path, 'wb') as f:
            cabecalho_buffer.seek(0)
            f.write(cabecalho_buffer.getvalue())
        
        # Processar documentos individualmente
        processados = 0
        erros = 0
        pdfs_documentos = []
        
        # Processar cada documento do processo
        for i, doc in enumerate(documentos, 1):
            doc_id = doc.get('id')
            doc_tipo = doc.get('tipoDocumento', 'Documento')
            
            logger.debug(f"Processando documento {i}/{len(documentos)}: {doc_id} ({doc_tipo})")
            
            try:
                # Obter documento com timeout manual
                start_doc_time = time.time()
                max_doc_time = 20  # 20 segundos máximo por documento
                
                # Tentar obter o documento
                try:
                    resposta_doc = retorna_documento_processo(num_processo, doc_id, cpf=cpf, senha=senha)
                    
                    # Verificar timeout
                    doc_time = time.time() - start_doc_time
                    if doc_time > max_doc_time:
                        logger.warning(f"Documento {doc_id} demorou muito tempo: {doc_time:.2f}s")
                        # Continuar processando mesmo assim
                
                except Exception as e:
                    logger.error(f"Erro ao obter documento {doc_id}: {str(e)}")
                    # Criar um PDF de erro para esse documento
                    error_pdf = os.path.join(temp_dir, f"doc_{doc_id}_erro.pdf")
                    create_info_pdf(f"Erro ao baixar documento {doc_id}: {str(e)}", 
                                   error_pdf, doc_id, doc_tipo)
                    pdfs_documentos.append(error_pdf)
                    erros += 1
                    continue
                
                # Verificar se há erro na resposta
                if 'msg_erro' in resposta_doc:
                    logger.error(f"Erro ao obter documento {doc_id}: {resposta_doc['msg_erro']}")
                    # Criar um PDF de erro para esse documento
                    error_pdf = os.path.join(temp_dir, f"doc_{doc_id}_erro.pdf")
                    create_info_pdf(f"Erro ao baixar documento {doc_id}: {resposta_doc['msg_erro']}", 
                                  error_pdf, doc_id, doc_tipo)
                    pdfs_documentos.append(error_pdf)
                    erros += 1
                    continue
                
                # Verificar se há conteúdo
                if not resposta_doc.get('conteudo'):
                    logger.warning(f"Documento {doc_id} sem conteúdo")
                    # Criar um PDF informando sobre a falta de conteúdo
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
                        
                elif mimetype in ['text/plain', 'text/xml', 'text/html']:
                    # Converter texto para PDF
                    pdf_path = f"{arquivo_temp}.pdf"
                    try:
                        texto = conteudo.decode('utf-8', errors='ignore')
                        create_text_pdf(texto, pdf_path, doc_id, doc_tipo)
                    except Exception as e:
                        logger.error(f"Erro ao converter texto para PDF: {str(e)}")
                        # Criar PDF informativo sobre o erro
                        pdf_path = f"{arquivo_temp}_erro.pdf"
                        create_info_pdf(f"Erro ao converter documento {doc_id} para PDF: {str(e)}",
                                      pdf_path, doc_id, doc_tipo)
                
                else:
                    # Outros tipos: salvar e criar PDF informativo
                    extension = get_extension_for_mimetype(mimetype)
                    original_path = f"{arquivo_temp}{extension}"
                    
                    # Salvar o arquivo original
                    with open(original_path, 'wb') as f:
                        f.write(conteudo)
                    
                    # Criar PDF informativo
                    pdf_path = f"{arquivo_temp}.pdf"
                    message = f"Documento {doc_id} do tipo {doc_tipo}\nFormato: {mimetype}\n"
                    message += f"O arquivo original foi salvo separadamente."
                    
                    create_info_pdf(message, pdf_path, doc_id, doc_tipo)
                
                # Adicionar cabeçalho ao PDF
                if pdf_path and os.path.exists(pdf_path):
                    try:
                        add_document_header(pdf_path, doc_id, doc_tipo)
                    except Exception as e:
                        logger.warning(f"Erro ao adicionar cabeçalho ao PDF: {str(e)}")
                    
                    pdfs_documentos.append(pdf_path)
                    processados += 1
                    logger.debug(f"Documento {doc_id} processado com sucesso")
                else:
                    logger.error(f"Falha ao gerar PDF para documento {doc_id}")
                    erros += 1
                
                # A cada 5 documentos, mesclar com o principal para economizar memória
                if len(pdfs_documentos) >= 5:
                    try:
                        # Mesclar os PDFs processados até agora
                        with PdfMerger() as merger:
                            merger.append(output_path)  # Arquivo principal
                            
                            for pdf in pdfs_documentos:
                                if os.path.exists(pdf):
                                    try:
                                        merger.append(pdf)
                                    except Exception as e:
                                        logger.error(f"Erro ao adicionar PDF ao merger: {str(e)}")
                            
                            # Salvar resultado intermediário
                            temp_pdf = os.path.join(temp_dir, f"temp_merged_{i}.pdf")
                            with open(temp_pdf, 'wb') as f:
                                merger.write(f)
                            
                            # Substituir arquivo principal
                            os.replace(temp_pdf, output_path)
                            
                            # Limpar PDFs individuais para liberar espaço
                            for pdf in pdfs_documentos:
                                if os.path.exists(pdf):
                                    try:
                                        os.remove(pdf)
                                    except:
                                        pass
                            
                            # Resetar lista
                            pdfs_documentos = []
                    except Exception as e:
                        logger.error(f"Erro ao mesclar PDFs: {str(e)}")
                
            except Exception as e:
                logger.error(f"Erro ao processar documento {doc_id}: {str(e)}")
                erros += 1
        
        # Mesclar documentos restantes
        if pdfs_documentos:
            try:
                with PdfMerger() as merger:
                    merger.append(output_path)
                    
                    for pdf in pdfs_documentos:
                        if os.path.exists(pdf):
                            try:
                                merger.append(pdf)
                            except Exception as e:
                                logger.error(f"Erro ao adicionar PDF ao merger final: {str(e)}")
                    
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
                logger.error(f"Erro ao mesclar PDFs finais: {str(e)}")
        
        # Verificar se algum documento foi processado
        if processados == 0:
            logger.error("Nenhum documento foi processado com sucesso")
            return gerar_pdf_informativo(temp_dir, num_processo,
                                        "Não foi possível processar nenhum documento deste processo.")
        
        # Adicionar página final com informações de processamento
        try:
            adicionar_pagina_info(output_path, {
                'processo': num_processo,
                'total_documentos': len(documentos),
                'processados': processados,
                'erros': erros,
                'taxa_sucesso': f"{(processados / len(documentos)) * 100:.1f}%",
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
    
    # Verificar se o texto é muito grande
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
    
    # Limitar o número de linhas para evitar PDFs muito grandes
    max_lines = 1000
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines.append("")
        lines.append("..." + " [Texto truncado por ser muito longo]")
    
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
    
    Args:
        pdf_path (str): Caminho do PDF a ser modificado
        doc_id (str): ID do documento
        doc_type (str): Tipo do documento
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
        
        # Adicionar cabeçalho a cada página
        for i in range(len(reader.pages)):
            page = reader.pages[i]
            watermark_page = watermark.pages[0]
            page.merge_page(watermark_page)
            writer.add_page(page)
        
        # Salvar o resultado
        with open(pdf_path, 'wb') as output_file:
            writer.write(output_file)
            
    except Exception as e:
        logger.warning(f"Erro ao adicionar cabeçalho ao PDF: {str(e)}")
        # Se falhar, retornar silenciosamente - o PDF original ainda é utilizável

def get_extension_for_mimetype(mimetype):
    """Helper para obter a extensão apropriada para um mimetype"""
    extensions = {
        'application/pdf': '.pdf',
        'text/html': '.html',
        'text/plain': '.txt',
        'text/xml': '.xml',
        'application/xml': '.xml',
        'application/json': '.json',
        'application/zip': '.zip',
        'image/jpeg': '.jpg',
        'image/png': '.png',
        'image/gif': '.gif',
        'application/msword': '.doc',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document': '.docx',
        'application/vnd.ms-excel': '.xls',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': '.xlsx'
    }
    
    return extensions.get(mimetype, '.bin')

def gerar_cabecalho_processo(dados_processo):
    """
    Gera um PDF contendo informações básicas do processo como cabeçalho.
    
    Args:
        dados_processo (dict): Dados do processo
        
    Returns:
        io.BytesIO: Buffer com o PDF gerado
    """
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    c.setTitle(f"Informações do Processo {dados_processo.get('processo', {}).get('numero', '')}")
    
    # Configurar fonte e tamanho
    c.setFont("Helvetica-Bold", 14)
    c.drawString(72, 750, "INFORMAÇÕES DO PROCESSO")
    
    c.setFont("Helvetica-Bold", 12)
    c.drawString(72, 720, f"Processo: {dados_processo.get('processo', {}).get('numero', 'N/A')}")
    
    c.setFont("Helvetica", 12)
    y = 690
    
    # Dados básicos
    if 'processo' in dados_processo:
        proc = dados_processo['processo']
        
        # Classe processual
        classe_desc = ''
        if proc.get('classeProcessual'):
            classe_desc = f"Classe: {proc.get('classeProcessual', 'N/A')}"
        c.drawString(72, y, classe_desc)
        y -= 20
        
        # Órgão julgador
        if proc.get('orgaoJulgador'):
            c.drawString(72, y, f"Órgão Julgador: {proc.get('orgaoJulgador', 'N/A')}")
            y -= 20
            
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
            y -= 30
    
    # Adicionar lista de documentos
    c.setFont("Helvetica-Bold", 12)
    c.drawString(72, y, "DOCUMENTOS DO PROCESSO")
    y -= 20
    
    c.setFont("Helvetica", 10)
    for i, doc in enumerate(dados_processo.get('documentos', []), 1):
        c.drawString(72, y, f"{i}. {doc.get('tipoDocumento', 'Documento')} (ID: {doc.get('id', 'N/A')})")
        if doc.get('dataDocumento'):
            c.drawString(350, y, f"Data: {doc.get('dataDocumento', 'N/A')}")
        y -= 15
        
        # Evitar que o texto ultrapasse a página
        if y < 72:
            c.showPage()
            c.setFont("Helvetica", 10)
            y = 750
    
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
        # Criar página de informações
        packet = io.BytesIO()
        c = canvas.Canvas(packet, pagesize=letter)
        width, height = letter
        
        # Título
        c.setFont("Helvetica-Bold", 14)
        c.drawString(72, height - 72, "INFORMAÇÕES DE PROCESSAMENTO")
        
        # Dados
        c.setFont("Helvetica", 12)
        y = height - 100
        
        for key, value in info_dict.items():
            if key == 'processo':
                c.drawString(72, y, f"Processo: {value}")
            elif key == 'total_documentos':
                c.drawString(72, y, f"Total de documentos: {value}")
            elif key == 'processados':
                c.drawString(72, y, f"Documentos processados: {value}")
            elif key == 'erros':
                c.drawString(72, y, f"Documentos com erros: {value}")
            elif key == 'taxa_sucesso':
                c.drawString(72, y, f"Taxa de sucesso: {value}")
            elif key == 'tempo_total':
                c.drawString(72, y, f"Tempo de processamento: {value}")
            else:
                c.drawString(72, y, f"{key}: {value}")
            
            y -= 20
        
        # Adicionar nota de rodapé
        c.setFont("Helvetica-Italic", 10)
        c.drawString(72, 72, "PDF gerado automaticamente pelo sistema de consulta processual")
        c.drawString(72, 60, f"Data/Hora: {time.strftime('%d/%m/%Y %H:%M:%S')}")
        
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
    
    Args:
        temp_dir (str): Diretório temporário
        num_processo (str): Número do processo
        mensagem (str): Mensagem de erro
        
    Returns:
        str: Caminho para o PDF gerado
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
    
    # Adicionar nota de rodapé
    c.drawString(72, 40, "PDF gerado automaticamente pelo sistema de consulta processual")
    
    c.showPage()
    c.save()
    
    return output_path
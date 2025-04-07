"""
Módulo para otimizar o download e processamento de PDFs de processos judiciais.
Inclui mecanismos melhorados de timeout e tratamento de erros.
"""

import os
import tempfile
import time
import logging
import io
import signal
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, TimeoutError
from functools import partial
import traceback

# Configurar logging
logger = logging.getLogger(__name__)

# Imports para manipulação de PDFs
try:
    from PyPDF2 import PdfMerger, PdfReader, PdfWriter
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter
except ImportError as e:
    logger.error(f"Erro ao importar bibliotecas de PDF: {str(e)}")

# Timeouts configuráveis
CONSULTA_TIMEOUT = 40  # Timeout para consulta inicial do processo
DOCUMENTO_TIMEOUT = 20  # Timeout para cada documento individual

class ProcessoTimeoutError(Exception):
    """Exceção para timeout durante o processamento"""
    pass

def timeout_handler(signum, frame):
    """Handler para sinal de timeout"""
    raise ProcessoTimeoutError("Operação excedeu o tempo limite")

def gerar_pdf_completo_otimizado(num_processo, cpf, senha, limite_docs=None):
    """
    Versão otimizada para gerar PDF completo de um processo com melhor tratamento de timeouts.
    
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
        
        # Importar funções necessárias
        try:
            from funcoes_mni import retorna_processo, retorna_documento_processo
            from utils import extract_mni_data
        except ImportError as e:
            logger.error(f"Erro ao importar módulos necessários: {str(e)}")
            return gerar_pdf_informativo(temp_dir, num_processo, 
                                         f"Erro ao carregar módulos necessários: {str(e)}")
        
        # Consultar o processo com timeout
        logger.debug(f"Consultando processo {num_processo} (timeout: {CONSULTA_TIMEOUT}s)")
        
        try:
            # Definir timeout para a consulta inicial
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(retorna_processo, num_processo, cpf=cpf, senha=senha)
                resposta = future.result(timeout=CONSULTA_TIMEOUT)
        except TimeoutError:
            logger.error(f"Timeout ao consultar processo {num_processo} (limite: {CONSULTA_TIMEOUT}s)")
            return gerar_pdf_informativo(temp_dir, num_processo, 
                                         f"Timeout ao consultar processo. A operação excedeu {CONSULTA_TIMEOUT} segundos.")
        except Exception as e:
            logger.error(f"Erro ao consultar processo: {str(e)}")
            return gerar_pdf_informativo(temp_dir, num_processo, f"Erro na consulta: {str(e)}")
        
        # Extrair dados do processo
        try:
            dados = extract_mni_data(resposta)
        except Exception as e:
            logger.error(f"Erro ao extrair dados da resposta: {str(e)}")
            return gerar_pdf_informativo(temp_dir, num_processo, 
                                        f"Erro ao processar resposta: {str(e)}")
        
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
        
        # Processar documentos individualmente com timeouts
        processados = 0
        erros = 0
        arquivos_documentos = []
        
        # Usar menos workers para economizar memória e reduzir problemas de timeout
        max_workers = min(3, len(documentos))
        logger.debug(f"Processando com {max_workers} workers")
        
        # Função para processar um único documento com timeout
        def processar_documento_seguro(doc_id, doc_tipo):
            try:
                # Tentar processar o documento com timeout
                with ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(
                        processar_documento_robusto,
                        num_processo, doc_id, doc_tipo, cpf, senha, temp_dir
                    )
                    return future.result(timeout=DOCUMENTO_TIMEOUT)
            except TimeoutError:
                logger.warning(f"Timeout ao processar documento {doc_id} ({DOCUMENTO_TIMEOUT}s)")
                # Criar um PDF informativo para o documento com timeout
                pdf_path = os.path.join(temp_dir, f"{doc_id}_timeout.pdf")
                create_info_pdf(
                    f"Não foi possível baixar o documento {doc_id} do tipo {doc_tipo} por timeout ({DOCUMENTO_TIMEOUT}s)",
                    pdf_path, doc_id, doc_tipo
                )
                return {'id': doc_id, 'caminho_pdf': pdf_path}
            except Exception as e:
                logger.error(f"Erro ao processar documento {doc_id}: {str(e)}")
                # Criar um PDF informativo para o documento com erro
                pdf_path = os.path.join(temp_dir, f"{doc_id}_erro.pdf")
                create_info_pdf(
                    f"Erro ao processar documento {doc_id} do tipo {doc_tipo}: {str(e)}",
                    pdf_path, doc_id, doc_tipo
                )
                return {'id': doc_id, 'caminho_pdf': pdf_path}
        
        # Processar documentos em lotes pequenos para gerenciar memória
        lote_size = 5
        doc_lotes = [documentos[i:i+lote_size] for i in range(0, len(documentos), lote_size)]
        
        for lote_idx, lote in enumerate(doc_lotes):
            logger.debug(f"Processando lote {lote_idx+1}/{len(doc_lotes)} ({len(lote)} documentos)")
            lote_results = []
            
            # Processar cada documento do lote
            for doc in lote:
                doc_id = doc.get('id')
                doc_tipo = doc.get('tipoDocumento', 'Desconhecido')
                
                # Processar documento com timeout
                resultado = processar_documento_seguro(doc_id, doc_tipo)
                
                if resultado and resultado.get('caminho_pdf') and os.path.exists(resultado.get('caminho_pdf')):
                    lote_results.append(resultado)
                    arquivos_documentos.append(resultado.get('caminho_pdf'))
                    processados += 1
                    logger.debug(f"Documento {doc_id} processado com sucesso ({processados}/{len(documentos)})")
                else:
                    logger.warning(f"Documento {doc_id} não gerou arquivo válido")
                    erros += 1
            
            # Mesclar este lote com o PDF principal
            if lote_results:
                # Mesclar PDFs deste lote
                lote_pdf = os.path.join(temp_dir, f"lote_{lote_idx}.pdf")
                
                try:
                    with PdfMerger() as merger:
                        merger.append(output_path)  # Adicionar o que já temos
                        
                        # Adicionar cada documento do lote
                        for resultado in lote_results:
                            pdf_path = resultado.get('caminho_pdf')
                            if pdf_path and os.path.exists(pdf_path):
                                try:
                                    merger.append(pdf_path)
                                except Exception as e:
                                    logger.error(f"Erro ao adicionar documento {resultado.get('id')} ao PDF: {str(e)}")
                        
                        # Salvar resultado intermediário
                        temp_pdf = os.path.join(temp_dir, f"temp_merged_{lote_idx}.pdf")
                        with open(temp_pdf, 'wb') as f:
                            merger.write(f)
                        
                        # Substituir o arquivo de saída pelo mesclado
                        os.replace(temp_pdf, output_path)
                        
                        # Limpar arquivos individuais deste lote após mesclar
                        for resultado in lote_results:
                            pdf_path = resultado.get('caminho_pdf')
                            if pdf_path and pdf_path != output_path and os.path.exists(pdf_path):
                                try:
                                    os.remove(pdf_path)
                                except:
                                    pass
                except Exception as e:
                    logger.error(f"Erro ao mesclar lote {lote_idx}: {str(e)}")
        
        # Verificar se algum documento foi processado
        if processados == 0:
            logger.error("Nenhum documento foi processado com sucesso")
            return gerar_pdf_informativo(temp_dir, num_processo,
                                        "Não foi possível processar nenhum documento deste processo.")
        
        # Calcular estatísticas
        tempo_total = time.time() - start_time
        taxa_sucesso = (processados / len(documentos)) * 100
        
        # Adicionar página final com informações de processamento
        adicionar_pagina_info(output_path, {
            'processo': num_processo,
            'total_documentos': len(documentos),
            'processados': processados,
            'taxa_sucesso': f"{taxa_sucesso:.1f}%",
            'tempo_total': f"{tempo_total:.2f} segundos"
        })
        
        logger.info(f"PDF gerado com sucesso em {tempo_total:.2f}s. "
                   f"Processados: {processados}/{len(documentos)} documentos ({taxa_sucesso:.1f}%)")
        
        return output_path
        
    except Exception as e:
        logger.error(f"Erro ao gerar PDF completo: {str(e)}")
        traceback.print_exc()
        
        if temp_dir:
            return gerar_pdf_informativo(temp_dir, num_processo, 
                                         f"Erro ao gerar PDF completo: {str(e)}")
        return None

def processar_documento_robusto(num_processo, id_documento, tipo_documento, cpf, senha, temp_dir):
    """
    Versão mais robusta da função de processamento de documento, com melhor tratamento de erros
    e suporte para diferentes formatos e estruturas de documentos.
    
    Args:
        num_processo (str): Número do processo
        id_documento (str): ID do documento
        tipo_documento (str): Tipo do documento
        cpf (str): CPF/CNPJ do consultante
        senha (str): Senha do consultante
        temp_dir (str): Diretório temporário para armazenar arquivos
        
    Returns:
        dict: Informações do documento processado, incluindo caminho para o PDF gerado
    """
    try:
        # Importar aqui para evitar problemas com circular imports
        from funcoes_mni import retorna_documento_processo
        
        # Obter o documento
        resposta = retorna_documento_processo(num_processo, id_documento, cpf=cpf, senha=senha)
        
        if 'msg_erro' in resposta:
            logger.error(f"Erro ao obter documento {id_documento}: {resposta['msg_erro']}")
            # Criar um PDF informativo sobre o erro
            arquivo_temp = os.path.join(temp_dir, f"doc_{id_documento}")
            pdf_path = f"{arquivo_temp}.pdf"
            message = f"Erro ao obter documento {id_documento}: {resposta['msg_erro']}"
            create_info_pdf(message, pdf_path, id_documento, tipo_documento)
            return {'id': id_documento, 'caminho_pdf': pdf_path}
            
        mimetype = resposta.get('mimetype', '')
        conteudo = resposta.get('conteudo', b'')  # Garantir que conteúdo nunca seja None
        
        # Verificar se temos conteúdo válido
        if not conteudo:
            logger.warning(f"Documento {id_documento} sem conteúdo")
            # Criar um PDF informativo sobre o erro
            arquivo_temp = os.path.join(temp_dir, f"doc_{id_documento}")
            pdf_path = f"{arquivo_temp}.pdf"
            message = f"Documento {id_documento} ({tipo_documento}) não possui conteúdo"
            create_info_pdf(message, pdf_path, id_documento, tipo_documento)
            return {'id': id_documento, 'caminho_pdf': pdf_path}
        
        # Caminho para o arquivo temporário
        arquivo_temp = os.path.join(temp_dir, f"doc_{id_documento}")
        
        # Variável para armazenar o caminho do PDF final
        pdf_path = None
            
        if mimetype == 'application/pdf':
            # Já é PDF, salvar diretamente
            pdf_path = f"{arquivo_temp}.pdf"
            with open(pdf_path, 'wb') as f:
                f.write(conteudo)
                
        elif mimetype == 'text/html':
            # Converter HTML para PDF
            html_path = f"{arquivo_temp}.html"
            pdf_path = f"{arquivo_temp}.pdf"
            
            with open(html_path, 'wb') as f:
                f.write(conteudo)
                
            # Gerar PDF a partir do HTML usando WeasyPrint
            try:
                import weasyprint
                html = weasyprint.HTML(filename=html_path)
                html.write_pdf(pdf_path)
                logger.debug(f"Arquivo HTML convertido para PDF: {pdf_path}")
            except Exception as e:
                logger.error(f"Erro ao converter HTML para PDF: {str(e)}")
                # Tenta criar um PDF simples com o texto
                try:
                    texto_html = conteudo.decode('utf-8', errors='ignore')
                    create_text_pdf(texto_html, pdf_path, id_documento, tipo_documento)
                except Exception as ex:
                    logger.error(f"Erro secundário ao processar HTML: {str(ex)}")
                    return None
                
        elif mimetype in ['text/plain', 'text/xml']:
            # Converter texto para PDF
            try:
                text = conteudo.decode('utf-8', errors='ignore')
                pdf_path = f"{arquivo_temp}.pdf"
                create_text_pdf(text, pdf_path, id_documento, tipo_documento)
            except Exception as e:
                logger.error(f"Erro ao converter texto para PDF: {str(e)}")
                return None
                
        else:
            # Outros tipos de arquivos: salvar e criar PDF informativo
            extension = get_extension_for_mimetype(mimetype)
            original_path = f"{arquivo_temp}{extension}"
            
            # Salvar o arquivo original
            with open(original_path, 'wb') as f:
                f.write(conteudo)
                
            # Criar um PDF informativo sobre este arquivo
            pdf_path = f"{arquivo_temp}.pdf"
            message = f"Documento {id_documento} do tipo {tipo_documento}\nFormato: {mimetype}\n"
            message += f"O arquivo original foi salvo como {os.path.basename(original_path)}"
            
            create_info_pdf(message, pdf_path, id_documento, tipo_documento)
        
        # Adicionar cabeçalho ao PDF final
        if pdf_path and os.path.exists(pdf_path):
            try:
                add_document_header(pdf_path, id_documento, tipo_documento)
            except Exception as e:
                logger.warning(f"Erro ao adicionar cabeçalho ao PDF: {str(e)}")
            
            return {
                'id': id_documento,
                'tipo': tipo_documento,
                'caminho_pdf': pdf_path,
                'mimetype': mimetype
            }
        else:
            logger.error(f"Falha ao gerar PDF para o documento {id_documento}")
            return None
            
    except Exception as e:
        logger.error(f"Erro ao processar documento {id_documento}: {str(e)}")
        
        # Tentar gerar um PDF informativo sobre o erro
        try:
            arquivo_temp = os.path.join(temp_dir, f"doc_{id_documento}")
            pdf_path = f"{arquivo_temp}.pdf"
            message = f"Erro ao processar documento {id_documento} ({tipo_documento}): {str(e)}"
            create_text_pdf(message, pdf_path, id_documento, tipo_documento)
            
            return {
                'id': id_documento,
                'tipo': tipo_documento,
                'caminho_pdf': pdf_path,
                'mimetype': 'application/pdf'
            }
        except:
            # Se falhar até a criação do PDF informativo, retornar None
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
    pdf = canvas.Canvas(output_path, pagesize=letter)
    width, height = letter
    
    # Configurar metadados
    pdf.setTitle(f"Documento {doc_id}")
    pdf.setSubject(f"Tipo: {doc_type}")
    
    # Configurar fonte e tamanho
    pdf.setFont("Helvetica", 10)
    
    # Função para quebrar o texto em linhas
    def wrap_text(text, width, pdf):
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
                if pdf.stringWidth(current_line + ' ' + word, "Helvetica", 10) < width - 144:  # 72 pontos por polegada * 2 (margens)
                    current_line += ' ' + word
                else:
                    lines.append(current_line)
                    current_line = word
            
            lines.append(current_line)
        
        return lines
    
    # Quebrar o texto em linhas
    lines = wrap_text(text, width, pdf)
    
    # Posição inicial
    y = height - 72  # Começar 1 polegada do topo
    
    # Desenhar linhas de texto
    for line in lines:
        if y < 72:  # Se chegou a 1 polegada do fundo da página
            pdf.showPage()  # Nova página
            pdf.setFont("Helvetica", 10)
            y = height - 72  # Resetar para o topo
        
        pdf.drawString(72, y, line)
        y -= 14  # Espaçamento entre linhas
    
    pdf.showPage()
    pdf.save()

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
    pdf = canvas.Canvas(output_path, pagesize=letter)
    width, height = letter
    
    # Configurar metadados
    pdf.setTitle(f"Informação - Documento {doc_id}")
    pdf.setSubject(f"Tipo: {doc_type}")
    
    # Título 
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(72, height - 72, f"Informação sobre o Documento {doc_id}")
    
    # Tipo de documento
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(72, height - 100, f"Tipo: {doc_type}")
    
    # Função para quebrar a mensagem em linhas
    def wrap_message(message, width):
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
                if pdf.stringWidth(current_line + ' ' + word, "Helvetica", 10) < width - 144:  # 72 pontos por polegada * 2 (margens)
                    current_line += ' ' + word
                else:
                    lines.append(current_line)
                    current_line = word
            
            lines.append(current_line)
            
        return lines
    
    # Quebrar a mensagem em linhas
    lines = wrap_message(message, width)
    
    # Posição inicial
    y = height - 130
    
    # Desenhar mensagem
    pdf.setFont("Helvetica", 10)
    for line in lines:
        pdf.drawString(72, y, line)
        y -= 14  # Espaçamento entre linhas
        
        # Verificar se precisa de nova página
        if y < 72:  # Se chegou a 1 polegada do fundo da página
            pdf.showPage()
            pdf.setFont("Helvetica", 10)
            y = height - 72
    
    pdf.showPage()
    pdf.save()

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
        can = canvas.Canvas(packet, pagesize=letter)
        width, height = letter
        
        # Desenhar cabeçalho na parte superior
        can.setFont("Helvetica-Bold", 10)
        can.drawString(72, height - 40, f"Documento: {doc_id}")
        can.drawString(72, height - 55, f"Tipo: {doc_type}")
        can.drawString(72, height - 70, f"Data de download: {time.strftime('%d/%m/%Y %H:%M:%S')}")
        
        # Linha separadora
        can.line(72, height - 80, width - 72, height - 80)
        
        can.save()
        
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
    # Mapeamento de mimetypes comuns para extensões
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
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': '.xlsx',
        'application/vnd.ms-powerpoint': '.ppt',
        'application/vnd.openxmlformats-officedocument.presentationml.presentation': '.pptx'
    }
    
    return extensions.get(mimetype, '.bin')  # .bin como fallback

def gerar_cabecalho_processo(dados_processo):
    """
    Gera um PDF contendo informações básicas do processo como cabeçalho.
    
    Args:
        dados_processo (dict): Dados do processo
        
    Returns:
        io.BytesIO: Buffer com o PDF gerado
    """
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    pdf.setTitle(f"Informações do Processo {dados_processo.get('processo', {}).get('numero', '')}")
    
    # Configurar fonte e tamanho
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(72, 750, "INFORMAÇÕES DO PROCESSO")
    
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(72, 720, f"Processo: {dados_processo.get('processo', {}).get('numero', 'N/A')}")
    
    pdf.setFont("Helvetica", 12)
    y = 690
    
    # Dados básicos
    if 'processo' in dados_processo:
        proc = dados_processo['processo']
        
        # Classe processual
        classe_desc = ''
        if proc.get('classeProcessual'):
            classe_desc = f"Classe: {proc.get('classeProcessual', 'N/A')}"
        pdf.drawString(72, y, classe_desc)
        y -= 20
        
        # Órgão julgador
        if proc.get('orgaoJulgador'):
            pdf.drawString(72, y, f"Órgão Julgador: {proc.get('orgaoJulgador', 'N/A')}")
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
            pdf.drawString(72, y, f"Data de Ajuizamento: {data_str}")
            y -= 30
    
    # Adicionar lista de documentos
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(72, y, "DOCUMENTOS DO PROCESSO")
    y -= 20
    
    pdf.setFont("Helvetica", 10)
    for i, doc in enumerate(dados_processo.get('documentos', []), 1):
        pdf.drawString(72, y, f"{i}. {doc.get('tipoDocumento', 'Documento')} (ID: {doc.get('id', 'N/A')})")
        if doc.get('dataDocumento'):
            pdf.drawString(350, y, f"Data: {doc.get('dataDocumento', 'N/A')}")
        y -= 15
        
        # Evitar que o texto ultrapasse a página
        if y < 72:
            pdf.showPage()
            pdf.setFont("Helvetica", 10)
            y = 750
    
    pdf.showPage()
    pdf.save()
    
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
        can = canvas.Canvas(packet, pagesize=letter)
        width, height = letter
        
        # Título
        can.setFont("Helvetica-Bold", 14)
        can.drawString(72, height - 72, "INFORMAÇÕES DE PROCESSAMENTO")
        
        # Dados
        can.setFont("Helvetica", 12)
        y = height - 100
        
        for key, value in info_dict.items():
            if key == 'processo':
                can.drawString(72, y, f"Processo: {value}")
            elif key == 'total_documentos':
                can.drawString(72, y, f"Total de documentos: {value}")
            elif key == 'processados':
                can.drawString(72, y, f"Documentos processados: {value}")
            elif key == 'taxa_sucesso':
                can.drawString(72, y, f"Taxa de sucesso: {value}")
            elif key == 'tempo_total':
                can.drawString(72, y, f"Tempo de processamento: {value}")
            else:
                can.drawString(72, y, f"{key}: {value}")
            
            y -= 20
        
        # Adicionar nota de rodapé
        can.setFont("Helvetica-Italic", 10)
        can.drawString(72, 72, "PDF gerado automaticamente pelo sistema de consulta processual")
        can.drawString(72, 60, f"Data/Hora: {time.strftime('%d/%m/%Y %H:%M:%S')}")
        
        can.save()
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
    
    pdf = canvas.Canvas(output_path, pagesize=letter)
    width, height = letter
    
    # Configurar metadados
    pdf.setTitle(f"Informação - Processo {num_processo}")
    
    # Título 
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(72, height - 72, f"Informação sobre o Processo {num_processo}")
    
    # Data e hora
    pdf.setFont("Helvetica", 10)
    pdf.drawString(72, height - 100, f"Data/Hora: {time.strftime('%d/%m/%Y %H:%M:%S')}")
    
    # Mensagem
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(72, height - 130, "Mensagem:")
    
    # Quebrar a mensagem em linhas
    pdf.setFont("Helvetica", 10)
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
            if pdf.stringWidth(current_line + ' ' + word, "Helvetica", 10) < width - 144:
                current_line += ' ' + word
            else:
                pdf.drawString(72, y, current_line)
                y -= 14
                current_line = word
                
                # Verificar se precisa de nova página
                if y < 72:
                    pdf.showPage()
                    pdf.setFont("Helvetica", 10)
                    y = height - 72
        
        pdf.drawString(72, y, current_line)
        y -= 14
    
    # Adicionar nota de rodapé
    pdf.drawString(72, 40, "PDF gerado automaticamente pelo sistema de consulta processual")
    
    pdf.showPage()
    pdf.save()
    
    return output_path
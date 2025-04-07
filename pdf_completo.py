"""
Módulo para geração de PDF completo de processos judiciais.
Implementação otimizada com processamento paralelo e múltiplas melhorias.

Características:
1. Processamento paralelo dos documentos
2. Melhor tratamento de erros e timeouts
3. Conversão avançada de HTML para PDF
4. Suporte a diferentes tipos de documentos
5. Geração de cabeçalho informativo por documento
"""

import tempfile
import os
import time
import logging
import io
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
from PyPDF2 import PdfReader, PdfWriter, PdfMerger
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from funcoes_mni import retorna_processo, retorna_documento_processo
from utils import extract_mni_data
import weasyprint

# Configurar logging
logger = logging.getLogger(__name__)

# Configurações
MAX_WORKERS = 5
TIMEOUT_DOCUMENTO = 30  # segundos
MAX_DOCUMENTOS = 50    # número máximo de documentos por PDF

def processar_documento(num_processo, id_documento, tipo_documento, cpf, senha, temp_dir):
    """
    Processa um documento do processo, convertendo para PDF se necessário.
    
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
        logger.debug(f"Iniciando processamento do documento {id_documento} - {tipo_documento}")
        
        # Obter conteúdo do documento
        inicio = time.time()
        resposta = retorna_documento_processo(num_processo, id_documento, cpf=cpf, senha=senha)
        logger.debug(f"Documento {id_documento} obtido em {time.time() - inicio:.2f}s")
        
        # Verificar erro
        if 'msg_erro' in resposta:
            logger.warning(f"Erro ao obter documento {id_documento}: {resposta['msg_erro']}")
            return {
                'erro': resposta['msg_erro'],
                'id': id_documento
            }
            
        # Determinar formato e processar conforme
        mimetype = resposta.get('mimetype', '').lower()
        logger.debug(f"Documento {id_documento} tem mimetype: {mimetype}")
        
        if not mimetype:
            logger.warning(f"Documento {id_documento} sem mimetype definido")
            output_path = os.path.join(temp_dir, f"{id_documento}_info.pdf")
            create_info_pdf("Documento sem formato definido", output_path, id_documento, tipo_documento)
            return {
                'caminho_pdf': output_path,
                'mimetype': 'application/pdf',
                'id': id_documento
            }
            
        # Processar baseado no mimetype
        if 'pdf' in mimetype:
            # Documento já é PDF
            output_path = os.path.join(temp_dir, f"{id_documento}.pdf")
            
            with open(output_path, 'wb') as f:
                f.write(resposta['conteudo'])
                
            # Adicionar cabeçalho ao PDF
            try:
                add_document_header(output_path, id_documento, tipo_documento)
            except Exception as e:
                logger.error(f"Erro ao adicionar cabeçalho ao PDF {id_documento}: {str(e)}")
                
            return {
                'caminho_pdf': output_path,
                'mimetype': mimetype,
                'id': id_documento
            }
            
        elif 'html' in mimetype or 'text' in mimetype:
            # Converter HTML para PDF
            output_path = os.path.join(temp_dir, f"{id_documento}.pdf")
            
            try:
                # Obter conteúdo como texto
                conteudo_texto = resposta['conteudo']
                if isinstance(conteudo_texto, bytes):
                    conteudo_texto = conteudo_texto.decode('utf-8', errors='ignore')
                    
                # Tentar converter usando WeasyPrint
                try:
                    logger.debug(f"Convertendo HTML para PDF usando WeasyPrint: {id_documento}")
                    html = weasyprint.HTML(string=conteudo_texto)
                    html.write_pdf(output_path)
                    
                    # Adicionar cabeçalho
                    add_document_header(output_path, id_documento, tipo_documento)
                    
                except Exception as html_error:
                    logger.warning(f"Erro ao converter HTML com WeasyPrint: {str(html_error)}")
                    logger.debug(f"Usando método alternativo para HTML: {id_documento}")
                    create_text_pdf(conteudo_texto, output_path, id_documento, tipo_documento)
                
                return {
                    'caminho_pdf': output_path,
                    'mimetype': mimetype,
                    'id': id_documento
                }
                
            except Exception as e:
                logger.error(f"Erro ao converter HTML para PDF {id_documento}: {str(e)}")
                # Criar PDF de erro
                output_path = os.path.join(temp_dir, f"{id_documento}_error.pdf")
                create_info_pdf(f"Erro ao converter HTML: {str(e)}", output_path, id_documento, tipo_documento)
                return {
                    'caminho_pdf': output_path,
                    'mimetype': 'application/pdf',
                    'id': id_documento
                }
                
        else:
            # Mimetype não suportado
            logger.warning(f"Documento {id_documento} com mimetype não suportado: {mimetype}")
            output_path = os.path.join(temp_dir, f"{id_documento}_info.pdf")
            create_info_pdf(f"Documento no formato {mimetype} não suportado nesta versão", 
                           output_path, id_documento, tipo_documento)
            return {
                'caminho_pdf': output_path,
                'mimetype': 'application/pdf',
                'id': id_documento
            }
                
    except Exception as e:
        logger.error(f"Erro geral ao processar documento {id_documento}: {str(e)}")
        # Em caso de erro, criar PDF informativo
        try:
            output_path = os.path.join(temp_dir, f"{id_documento}_error.pdf")
            create_info_pdf(f"Erro ao processar documento: {str(e)}", output_path, id_documento, tipo_documento)
            return {
                'caminho_pdf': output_path,
                'mimetype': 'application/pdf',
                'id': id_documento,
                'erro': str(e)
            }
        except:
            # Se nem isso funcionar, retornar apenas erro
            return {
                'erro': str(e),
                'id': id_documento
            }


def add_document_header(pdf_path, doc_id, doc_type):
    """
    Adiciona um cabeçalho com informações ao PDF existente.
    
    Args:
        pdf_path (str): Caminho do PDF a ser modificado
        doc_id (str): ID do documento
        doc_type (str): Tipo do documento
    """
    try:
        # Criar PDF temporário com cabeçalho
        temp_header_path = f"{pdf_path}.header.pdf"
        
        # Gerar cabeçalho
        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=letter)
        c.setFont("Helvetica-Bold", 12)
        c.drawString(30, 780, f"DOCUMENTO: {doc_type}")
        c.setFont("Helvetica", 10)
        c.drawString(30, 760, f"ID: {doc_id}")
        c.drawLine(30, 750, 550, 750)
        c.save()
        buffer.seek(0)
        
        # Escrever cabeçalho para arquivo temporário
        with open(temp_header_path, 'wb') as f:
            f.write(buffer.read())
        
        # Criar merger
        merger = PdfMerger()
        
        # Adicionar cabeçalho e documento original
        merger.append(temp_header_path)
        merger.append(pdf_path)
        
        # Salvar no arquivo original
        temp_output = f"{pdf_path}.with_header.pdf"
        with open(temp_output, 'wb') as f:
            merger.write(f)
            
        merger.close()
        
        # Substituir arquivo original
        os.replace(temp_output, pdf_path)
        
        # Limpar arquivos temporários
        try:
            os.remove(temp_header_path)
        except:
            pass
            
    except Exception as e:
        logger.error(f"Erro ao adicionar cabeçalho: {str(e)}")
        raise


def create_text_pdf(text, output_path, doc_id, doc_type):
    """
    Cria um PDF a partir de texto.
    
    Args:
        text (str): Texto a ser convertido
        output_path (str): Caminho para salvar o PDF
        doc_id (str): ID do documento
        doc_type (str): Tipo do documento
    """
    try:
        c = canvas.Canvas(output_path, pagesize=letter)
        
        # Adicionar cabeçalho
        c.setFont("Helvetica-Bold", 12)
        c.drawString(30, 780, f"DOCUMENTO: {doc_type}")
        c.setFont("Helvetica", 10)
        c.drawString(30, 760, f"ID: {doc_id}")
        c.drawLine(30, 750, 550, 750)
        
        # Adicionar texto do documento
        y = 730
        c.setFont("Helvetica", 10)
        
        # Quebrar texto em linhas
        wrap_text(text, 500, c, start_y=y)
        
        c.save()
        
    except Exception as e:
        logger.error(f"Erro ao criar PDF de texto: {str(e)}")
        # Tentar método alternativo em caso de erro
        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=letter)
        c.setFont("Helvetica-Bold", 12)
        c.drawString(30, 780, f"DOCUMENTO: {doc_type}")
        c.setFont("Helvetica", 10)
        c.drawString(30, 760, f"ID: {doc_id}")
        c.drawLine(30, 750, 550, 750)
        c.drawString(30, 720, "Erro ao processar texto completo.")
        c.drawString(30, 700, str(e)[:100])
        c.save()
        buffer.seek(0)
        
        with open(output_path, 'wb') as f:
            f.write(buffer.read())


def wrap_text(text, width, pdf, start_y=730):
    """
    Quebra texto em linhas para caber no PDF.
    
    Args:
        text (str): Texto a ser quebrado
        width (int): Largura máxima em pontos
        pdf (Canvas): Objeto canvas do reportlab
        start_y (int): Posição Y inicial
    """
    y = start_y
    
    # Processar cada linha
    for line in text.split('\n'):
        if not line.strip():
            y -= 12  # linha vazia
            if y < 30:
                pdf.showPage()
                pdf.setFont("Helvetica", 10)
                y = 780
            continue
        
        # Quebrar linha se necessário
        words = line.split()
        if not words:
            continue
            
        current_line = words[0]
        for word in words[1:]:
            # Verificar se a palavra cabe na linha atual
            if pdf.stringWidth(current_line + ' ' + word) < width:
                current_line += ' ' + word
            else:
                # Escrever linha atual e começar nova linha
                pdf.drawString(30, y, current_line)
                y -= 12
                if y < 30:  # Nova página se necessário
                    pdf.showPage()
                    pdf.setFont("Helvetica", 10)
                    y = 780
                current_line = word
                
        # Escrever última linha
        pdf.drawString(30, y, current_line)
        y -= 12
        if y < 30:
            pdf.showPage()
            pdf.setFont("Helvetica", 10)
            y = 780


def create_info_pdf(message, output_path, doc_id, doc_type):
    """
    Cria um PDF informativo quando o tipo de arquivo não é suportado.
    
    Args:
        message (str): Mensagem a ser incluída no PDF
        output_path (str): Caminho para salvar o PDF
        doc_id (str): ID do documento
        doc_type (str): Tipo do documento
    """
    c = canvas.Canvas(output_path, pagesize=letter)
    
    # Adicionar cabeçalho
    c.setFont("Helvetica-Bold", 12)
    c.drawString(30, 780, f"DOCUMENTO: {doc_type}")
    c.setFont("Helvetica", 10)
    c.drawString(30, 760, f"ID: {doc_id}")
    c.drawLine(30, 750, 550, 750)
    
    # Adicionar mensagem
    c.setFont("Helvetica-Bold", 12)
    c.drawString(30, 720, "INFORMAÇÃO:")
    c.setFont("Helvetica", 10)
    c.drawString(30, 700, message)
    
    c.save()


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
        if proc.get('classeProcessual'):
            pdf.drawString(72, y, f"Classe: {proc.get('classeProcessual', 'N/A')}")
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
    for i, doc in enumerate(dados_processo.get('documentos', [])[:MAX_DOCUMENTOS], 1):
        pdf.drawString(72, y, f"{i}. {doc.get('tipoDocumento', 'Documento')} (ID: {doc.get('id', 'N/A')})")
        if doc.get('dataDocumento'):
            pdf.drawString(350, y, f"Data: {doc.get('dataDocumento', 'N/A')}")
        y -= 15
        
        # Evitar que o texto ultrapasse a página
        if y < 72:
            pdf.showPage()
            pdf.setFont("Helvetica", 10)
            y = 750
    
    # Se houver mais documentos que o limite
    if len(dados_processo.get('documentos', [])) > MAX_DOCUMENTOS:
        pdf.drawString(72, y, f"... e mais {len(dados_processo.get('documentos', [])) - MAX_DOCUMENTOS} documentos não listados")
    
    pdf.showPage()
    pdf.save()
    
    buffer.seek(0)
    return buffer


def gerar_pdf_completo(num_processo, cpf, senha, limite=None):
    """
    Gera um PDF único contendo todos os documentos do processo.
    Versão otimizada com processamento paralelo.
    
    Args:
        num_processo (str): Número do processo judicial
        cpf (str): CPF/CNPJ do consultante
        senha (str): Senha do consultante
        limite (int, optional): Limite máximo de documentos a processar
        
    Returns:
        dict: Informações sobre o PDF gerado, incluindo caminho do arquivo
    """
    start_time = time.time()
    logger.info(f"Iniciando geração otimizada do PDF completo para o processo {num_processo}")
    
    try:
        # Consultar o processo para obter lista de documentos
        resposta_processo = retorna_processo(num_processo, cpf=cpf, senha=senha)
        dados = extract_mni_data(resposta_processo)
        
        if not dados.get('documentos') or len(dados.get('documentos', [])) == 0:
            return {
                'erro': 'Processo sem documentos',
                'mensagem': 'O processo não possui documentos para gerar PDF'
            }
            
        documentos = dados['documentos']
        logger.info(f"Encontrados {len(documentos)} documentos no processo {num_processo}")
        
        # Aplicar limite se especificado
        if limite and limite > 0:
            documentos = documentos[:int(limite)]
            logger.info(f"Limitando a {limite} documentos")
            
        # Criar diretório temporário para armazenar arquivos
        temp_dir = tempfile.mkdtemp()
        pdf_merger = PdfMerger()
        
        # Adicionar cabeçalho com informações do processo
        cabecalho_buffer = gerar_cabecalho_processo(dados)
        pdf_merger.append(cabecalho_buffer)
        
        # Contadores
        processados = 0
        erros = 0
        
        # Calcular número de workers adequado
        max_workers = min(MAX_WORKERS, len(documentos))
        logger.debug(f"Usando {max_workers} workers para processamento paralelo")
        
        # Processar documentos em paralelo
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submeter tarefas
            futures = {
                executor.submit(
                    processar_documento, 
                    num_processo, doc['id'], 
                    doc.get('tipoDocumento', 'Documento'), 
                    cpf, senha, temp_dir
                ): (i, doc) 
                for i, doc in enumerate(documentos)
            }
            
            # Lista para armazenar resultados na ordem correta
            resultados = [None] * len(documentos)
            
            # Processar resultados conforme concluídos
            for future in as_completed(futures):
                idx, doc = futures[future]
                
                try:
                    # Obter resultado com timeout
                    resultado = future.result(timeout=TIMEOUT_DOCUMENTO)
                    
                    if resultado and resultado.get('caminho_pdf'):
                        # Armazenar resultado para processamento em ordem depois
                        resultados[idx] = resultado
                        processados += 1
                        logger.debug(f"Documento {doc['id']} processado com sucesso (índice {idx})")
                    else:
                        logger.warning(f"Documento {doc['id']} não gerou PDF válido: {resultado.get('erro', 'motivo desconhecido')}")
                        erros += 1
                        
                except TimeoutError:
                    logger.error(f"Timeout ao processar documento {doc['id']}")
                    erros += 1
                    # Criar PDF de erro para este documento
                    try:
                        error_path = os.path.join(temp_dir, f"{doc['id']}_timeout.pdf")
                        create_info_pdf(f"Documento excedeu o tempo limite de processamento ({TIMEOUT_DOCUMENTO}s)",
                                       error_path, doc['id'], doc.get('tipoDocumento', 'Documento'))
                        resultados[idx] = {
                            'caminho_pdf': error_path,
                            'mimetype': 'application/pdf',
                            'id': doc['id'],
                            'erro': 'timeout'
                        }
                    except:
                        pass
                        
                except Exception as e:
                    logger.error(f"Erro ao processar documento {doc['id']}: {str(e)}")
                    erros += 1
            
            # Adicionar PDFs ao merger na ordem correta
            for resultado in resultados:
                if resultado and resultado.get('caminho_pdf'):
                    try:
                        pdf_merger.append(resultado['caminho_pdf'])
                    except Exception as e:
                        logger.error(f"Erro ao adicionar documento {resultado.get('id', 'desconhecido')} ao PDF final: {str(e)}")
                        erros += 1
                        processados -= 1
        
        # Verificar se processou algum documento
        if processados == 0:
            return {
                'erro': 'Falha no processamento',
                'mensagem': f'Não foi possível processar nenhum documento. Erros: {erros}',
                'tempo': time.time() - start_time
            }
            
        # Gerar o arquivo PDF final
        output_path = os.path.join(temp_dir, f"processo_{num_processo}.pdf")
        with open(output_path, 'wb') as f:
            pdf_merger.write(f)
            
        pdf_merger.close()
        
        # Calcular estatísticas
        tempo_total = time.time() - start_time
        taxa_sucesso = (processados / len(documentos)) * 100
        
        logger.info(f"PDF gerado com sucesso em {tempo_total:.2f}s. "
                   f"Processados: {processados}/{len(documentos)} documentos ({taxa_sucesso:.1f}%)")
        
        return {
            'caminho_pdf': output_path,
            'documentos_processados': processados,
            'documentos_total': len(documentos),
            'erros': erros,
            'tempo': tempo_total
        }
            
    except Exception as e:
        logger.error(f"Erro geral ao gerar PDF completo: {str(e)}")
        return {
            'erro': str(e),
            'mensagem': 'Erro ao gerar PDF completo do processo',
            'tempo': time.time() - start_time
        }
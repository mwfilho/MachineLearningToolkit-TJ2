"""
Módulo simplificado para gerar PDF completo de processos judiciais.
Otimizado para ambientes Replit com limitações de recursos.

Esta versão:
1. Limita o tempo máximo de processamento por documento
2. É single-threaded para evitar sobrecarga
3. Não usa API complexas para conversão HTML->PDF
4. Inclui apenas textos e PDFs, ignorando outros formatos
"""

import tempfile
import os
import time
import logging
import io
from PyPDF2 import PdfReader, PdfWriter, PdfMerger
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from funcoes_mni import retorna_processo, retorna_documento_processo
from utils import extract_mni_data
import threading
import signal

# Configurar logging
logger = logging.getLogger(__name__)

# Constantes de configuração
TIMEOUT_DOCUMENTO = 3  # segundos
MAX_DOCUMENTOS = 30    # número máximo de documentos

def timeout_handler(signum, frame):
    """Handler para timeout de documentos"""
    raise TimeoutError("Tempo limite excedido ao processar documento")

def processar_documento_com_timeout(num_processo, id_documento, tipo_documento, cpf, senha, temp_dir):
    """
    Processa um documento com timeout para evitar bloqueios.
    
    Args:
        num_processo (str): Número do processo
        id_documento (str): ID do documento
        tipo_documento (str): Tipo do documento
        cpf (str): CPF do consultante
        senha (str): Senha do consultante
        temp_dir (str): Diretório temporário
        
    Returns:
        dict: Informações do documento processado ou None em caso de timeout
    """
    # Configurar timeout
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(TIMEOUT_DOCUMENTO)
    
    try:
        resposta = retorna_documento_processo(num_processo, id_documento, cpf=cpf, senha=senha)
        
        if 'msg_erro' in resposta:
            logger.warning(f"Erro ao obter documento {id_documento}: {resposta['msg_erro']}")
            signal.alarm(0)  # Cancelar alarme
            return None
            
        # Verificar mimetype
        mimetype = resposta.get('mimetype', '').lower()
        if not mimetype:
            logger.warning(f"Documento {id_documento} sem mimetype definido")
            signal.alarm(0)
            return None
            
        # Processar com base no mimetype
        if 'pdf' in mimetype:
            # Documento já é PDF
            output_path = os.path.join(temp_dir, f"{id_documento}.pdf")
            with open(output_path, 'wb') as f:
                f.write(resposta['conteudo'])
            
            # Adicionar cabeçalho ao PDF existente
            try:
                pdf_com_cabecalho = adicionar_cabecalho_pdf(output_path, id_documento, tipo_documento)
                os.replace(pdf_com_cabecalho, output_path)
            except Exception as e:
                logger.error(f"Erro ao adicionar cabeçalho ao PDF {id_documento}: {str(e)}")
                
            signal.alarm(0)
            return {
                'caminho_pdf': output_path,
                'mimetype': mimetype,
                'id': id_documento
            }
            
        elif 'html' in mimetype or 'text' in mimetype:
            # Converter HTML para PDF simples (apenas texto)
            output_path = os.path.join(temp_dir, f"{id_documento}.pdf")
            
            try:
                conteudo_texto = resposta['conteudo']
                if isinstance(conteudo_texto, bytes):
                    conteudo_texto = conteudo_texto.decode('utf-8', errors='ignore')
                    
                # Criar PDF simplificado com o texto
                create_text_pdf(conteudo_texto, output_path, id_documento, tipo_documento)
                
                signal.alarm(0)
                return {
                    'caminho_pdf': output_path,
                    'mimetype': mimetype,
                    'id': id_documento
                }
            except Exception as e:
                logger.error(f"Erro ao converter HTML para PDF {id_documento}: {str(e)}")
                signal.alarm(0)
                return None
                
        else:
            # Mimetype não suportado
            logger.warning(f"Documento {id_documento} com mimetype não suportado: {mimetype}")
            output_path = os.path.join(temp_dir, f"{id_documento}_info.pdf")
            create_info_pdf(f"Documento no formato {mimetype} não suportado", output_path, id_documento, tipo_documento)
            
            signal.alarm(0)
            return {
                'caminho_pdf': output_path,
                'mimetype': 'application/pdf',
                'id': id_documento
            }
                
    except TimeoutError:
        logger.warning(f"Documento {id_documento} atingiu timeout ({TIMEOUT_DOCUMENTO}s)")
        return None
    except Exception as e:
        logger.error(f"Erro ao processar documento {id_documento}: {str(e)}")
        signal.alarm(0)
        return None
    finally:
        # Garantir que o alarme seja cancelado
        signal.alarm(0)


def adicionar_cabecalho_pdf(pdf_path, doc_id, doc_type):
    """
    Adiciona um cabeçalho ao PDF com informações do documento.
    
    Args:
        pdf_path (str): Caminho do PDF original
        doc_id (str): ID do documento
        doc_type (str): Tipo do documento
        
    Returns:
        str: Caminho do PDF com cabeçalho
    """
    output_path = pdf_path.replace('.pdf', '_with_header.pdf')
    
    try:
        # Criar PDF do cabeçalho
        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=letter)
        c.setFont("Helvetica-Bold", 12)
        c.drawString(30, 780, f"DOCUMENTO: {doc_type}")
        c.setFont("Helvetica", 10)
        c.drawString(30, 760, f"ID: {doc_id}")
        c.drawLine(30, 750, 550, 750)
        c.save()
        buffer.seek(0)
        
        # Criar o merger
        merger = PdfMerger()
        
        # Adicionar cabeçalho
        merger.append(buffer)
        
        # Adicionar documento original
        merger.append(pdf_path)
        
        # Salvar documento final
        with open(output_path, 'wb') as f:
            merger.write(f)
            
        merger.close()
        return output_path
        
    except Exception as e:
        logger.error(f"Erro ao adicionar cabeçalho: {str(e)}")
        # Em caso de erro, retornar o PDF original
        return pdf_path


def create_text_pdf(text, output_path, doc_id, doc_type):
    """
    Cria um PDF simples a partir de texto.
    
    Args:
        text (str): Texto a ser incluído no PDF
        output_path (str): Caminho para salvar o PDF
        doc_id (str): ID do documento
        doc_type (str): Tipo do documento
    """
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    
    # Adicionar cabeçalho
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(30, 780, f"DOCUMENTO: {doc_type}")
    pdf.setFont("Helvetica", 10)
    pdf.drawString(30, 760, f"ID: {doc_id}")
    pdf.drawLine(30, 750, 550, 750)
    
    # Adicionar texto
    y = 730
    pdf.setFont("Helvetica", 10)
    
    # Quebrar texto em linhas
    for line in text.split('\n'):
        # Quebrar linha se for muito longa
        words = line.split()
        if not words:
            y -= 12  # linha vazia
            continue
            
        current_line = words[0]
        for word in words[1:]:
            if pdf.stringWidth(current_line + ' ' + word) < 500:
                current_line += ' ' + word
            else:
                pdf.drawString(30, y, current_line)
                y -= 12
                if y < 30:  # Nova página
                    pdf.showPage()
                    pdf.setFont("Helvetica", 10)
                    y = 780
                current_line = word
                
        pdf.drawString(30, y, current_line)
        y -= 12
        if y < 30:
            pdf.showPage()
            pdf.setFont("Helvetica", 10)
            y = 780
    
    pdf.save()
    buffer.seek(0)
    
    with open(output_path, 'wb') as f:
        f.write(buffer.read())


def create_info_pdf(message, output_path, doc_id, doc_type):
    """
    Cria um PDF informativo quando o formato não é suportado.
    
    Args:
        message (str): Mensagem informativa
        output_path (str): Caminho para salvar o PDF
        doc_id (str): ID do documento
        doc_type (str): Tipo do documento
    """
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    
    # Adicionar cabeçalho
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(30, 780, f"DOCUMENTO: {doc_type}")
    pdf.setFont("Helvetica", 10)
    pdf.drawString(30, 760, f"ID: {doc_id}")
    pdf.drawLine(30, 750, 550, 750)
    
    # Adicionar mensagem
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(30, 700, "INFORMAÇÃO:")
    pdf.setFont("Helvetica", 10)
    pdf.drawString(30, 680, message)
    
    pdf.save()
    buffer.seek(0)
    
    with open(output_path, 'wb') as f:
        f.write(buffer.read())


def gerar_cabecalho_processo(dados_processo):
    """
    Gera um PDF com informações básicas do processo.
    
    Args:
        dados_processo (dict): Dados do processo
        
    Returns:
        io.BytesIO: Buffer com o PDF gerado
    """
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    
    # Configurar título
    pdf.setTitle(f"Informações do Processo {dados_processo.get('processo', {}).get('numero', '')}")
    
    # Informações do processo
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(30, 780, "INFORMAÇÕES DO PROCESSO")
    
    # Número do processo
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(30, 750, f"Processo: {dados_processo.get('processo', {}).get('numero', 'N/A')}")
    
    # Dados básicos
    y = 720
    pdf.setFont("Helvetica", 11)
    
    if 'processo' in dados_processo:
        proc = dados_processo['processo']
        
        # Classe
        if proc.get('classeProcessual'):
            pdf.drawString(30, y, f"Classe: {proc.get('classeProcessual', 'N/A')}")
            y -= 20
            
        # Órgão julgador
        if proc.get('orgaoJulgador'):
            pdf.drawString(30, y, f"Órgão Julgador: {proc.get('orgaoJulgador', 'N/A')}")
            y -= 20
            
        # Data de ajuizamento
        if proc.get('dataAjuizamento'):
            data_str = proc.get('dataAjuizamento')
            if len(data_str) == 8:
                data_str = f"{data_str[6:8]}/{data_str[4:6]}/{data_str[0:4]}"
            pdf.drawString(30, y, f"Data de Ajuizamento: {data_str}")
            y -= 30
            
    # Adicionar lista de documentos
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(30, y, "DOCUMENTOS DO PROCESSO")
    y -= 20
    
    pdf.setFont("Helvetica", 10)
    # Limitar o número de documentos mostrados para evitar PDFs enormes
    docs_to_show = dados_processo.get('documentos', [])[:MAX_DOCUMENTOS]
    
    for i, doc in enumerate(docs_to_show, 1):
        pdf.drawString(30, y, f"{i}. {doc.get('tipoDocumento', 'Documento')} (ID: {doc.get('id', 'N/A')})")
        y -= 15
        
        # Nova página se necessário
        if y < 30:
            pdf.showPage()
            pdf.setFont("Helvetica", 10)
            y = 780
    
    # Se houver mais documentos além do limite
    if len(dados_processo.get('documentos', [])) > MAX_DOCUMENTOS:
        pdf.drawString(30, y, f"... e mais {len(dados_processo.get('documentos', [])) - MAX_DOCUMENTOS} documentos")
        
    pdf.showPage()
    pdf.save()
    
    buffer.seek(0)
    return buffer


def gerar_pdf_completo_ultra_simples(num_processo, cpf, senha, limite=None):
    """
    Versão ultra simplificada do gerador de PDF completo,
    otimizada para ambientes com restrições de recursos.
    
    Args:
        num_processo (str): Número do processo
        cpf (str): CPF do consultante
        senha (str): Senha do consultante
        limite (int, optional): Limite máximo de documentos a processar
        
    Returns:
        dict: Informações sobre o PDF gerado, incluindo caminho
    """
    start_time = time.time()
    logger.info(f"Iniciando geração ultra simplificada do PDF para {num_processo}")
    
    try:
        # Consultar o processo
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
            
        # Criar diretório temporário
        temp_dir = tempfile.mkdtemp()
        pdf_merger = PdfMerger()
        
        # Adicionar cabeçalho do processo
        cabecalho_buffer = gerar_cabecalho_processo(dados)
        pdf_merger.append(cabecalho_buffer)
        
        # Contadores
        processados = 0
        erros = 0
        
        # Processar documentos sequencialmente (single-threaded)
        for doc in documentos:
            logger.debug(f"Processando documento {doc['id']} - {doc.get('tipoDocumento', 'N/A')}")
            
            resultado = processar_documento_com_timeout(
                num_processo, 
                doc['id'], 
                doc.get('tipoDocumento', 'Documento'), 
                cpf, senha, temp_dir
            )
            
            if resultado and resultado.get('caminho_pdf'):
                try:
                    pdf_merger.append(resultado['caminho_pdf'])
                    processados += 1
                    logger.debug(f"Documento {doc['id']} adicionado com sucesso")
                except Exception as e:
                    logger.error(f"Erro ao adicionar documento {doc['id']} ao PDF final: {str(e)}")
                    erros += 1
            else:
                erros += 1
                
        # Verificar se processou algum documento
        if processados == 0:
            return {
                'erro': 'Falha no processamento',
                'mensagem': f'Não foi possível processar nenhum documento. Erros: {erros}',
                'tempo': time.time() - start_time
            }
            
        # Gerar PDF final
        output_path = os.path.join(temp_dir, f"processo_{num_processo}.pdf")
        with open(output_path, 'wb') as f:
            pdf_merger.write(f)
            
        pdf_merger.close()
        
        # Calcular estatísticas
        tempo_total = time.time() - start_time
        logger.info(f"PDF gerado com sucesso em {tempo_total:.2f}s. Processados: {processados}/{len(documentos)} documentos")
        
        return {
            'caminho_pdf': output_path,
            'documentos_processados': processados,
            'documentos_total': len(documentos),
            'erros': erros,
            'tempo': tempo_total
        }
            
    except Exception as e:
        logger.error(f"Erro ao gerar PDF completo ultra simples: {str(e)}")
        return {
            'erro': str(e),
            'mensagem': 'Erro ao gerar PDF completo do processo',
            'tempo': time.time() - start_time
        }
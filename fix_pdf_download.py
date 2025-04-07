import logging
import os
import tempfile
import time
import base64
import io
from datetime import datetime
from PyPDF2 import PdfReader, PdfWriter, PdfMerger
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter

from funcoes_mni import retorna_processo, retorna_documento_processo
from utils import extract_mni_data

# Configurar logging
logging.basicConfig(level=logging.DEBUG, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

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
    max_retries = 3
    retry_count = 0
    last_error = None
    
    while retry_count < max_retries:
        try:
            # Obter o documento com timeout maior
            logger.debug(f"Tentativa {retry_count+1}/{max_retries} para documento {id_documento}")
            resposta = retorna_documento_processo(num_processo, id_documento, cpf=cpf, senha=senha)
            
            if 'msg_erro' in resposta:
                logger.warning(f"Erro ao obter documento {id_documento}: {resposta['msg_erro']}")
                # Criar um PDF informativo sobre o erro
                arquivo_temp = os.path.join(temp_dir, f"doc_{id_documento}")
                pdf_path = f"{arquivo_temp}.pdf"
                message = f"Erro ao obter documento {id_documento}: {resposta['msg_erro']}"
                create_info_pdf(message, pdf_path, id_documento, tipo_documento)
                return {'id': id_documento, 'caminho_pdf': pdf_path}
                
            # Verificar se o documento tem um caminho alternativo para o conteúdo
            mimetype = resposta.get('mimetype', '')
            conteudo = resposta.get('conteudo', b'')
            
            # Se não tiver conteúdo, verificar se há algum erro específico
            if not conteudo:
                logger.warning(f"Documento {id_documento} sem conteúdo")
                
                # Tentar obter o processo completo para ver se conseguimos o documento de outra forma
                try:
                    resposta_completa = retorna_processo(num_processo, cpf=cpf, senha=senha)
                    dados = extract_mni_data(resposta_completa)
                    
                    # Procurar o documento nos dados completos
                    for doc in dados.get('documentos', []):
                        if doc['id'] == id_documento:
                            logger.info(f"Documento {id_documento} encontrado no processo completo")
                            
                            # Tentar consulta específica novamente
                            logger.debug("Tentando nova consulta específica")
                            resposta_nova = retorna_documento_processo(num_processo, id_documento, cpf=cpf, senha=senha)
                            
                            if resposta_nova.get('conteudo'):
                                conteudo = resposta_nova.get('conteudo')
                                mimetype = resposta_nova.get('mimetype', mimetype)
                                logger.info(f"Conteúdo recuperado na segunda tentativa: {len(conteudo)} bytes")
                            break
                except Exception as e:
                    logger.warning(f"Falha na tentativa alternativa: {str(e)}")
                
                # Se ainda não tiver conteúdo, criar PDF informativo
                if not conteudo:
                    arquivo_temp = os.path.join(temp_dir, f"doc_{id_documento}")
                    pdf_path = f"{arquivo_temp}.pdf"
                    message = f"Documento {id_documento} ({tipo_documento}) não possui conteúdo"
                    create_info_pdf(message, pdf_path, id_documento, tipo_documento)
                    return {'id': id_documento, 'caminho_pdf': pdf_path}
            
            # Caminho para o arquivo temporário
            arquivo_temp = os.path.join(temp_dir, f"doc_{id_documento}")
            
            # Variável para armazenar o caminho do PDF final
            pdf_path = None
            
            # Determinar o melhor processamento com base no mimetype
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
                    
                    create_text_pdf(text, pdf_path, id_documento, tipo_documento)
            
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
                        create_text_pdf(html_content, pdf_path, id_documento, tipo_documento)
                        logger.debug(f"Arquivo HTML convertido para PDF como texto: {pdf_path}")
                        success = True
                    except Exception as ex:
                        logger.error(f"Erro ao criar PDF a partir do texto HTML: {str(ex)}")
                        return None
            
            elif mimetype in ['text/plain', 'text/xml', 'application/xml']:
                # Converter texto para PDF
                try:
                    text = conteudo.decode('utf-8', errors='ignore')
                    pdf_path = f"{arquivo_temp}.pdf"
                    create_text_pdf(text, pdf_path, id_documento, tipo_documento)
                except Exception as e:
                    logger.error(f"Erro ao criar PDF de texto: {str(e)}")
                    return None
            
            elif mimetype == 'application/zip' or mimetype.startswith('image/'):
                # Para arquivos binários, criar PDF com informações
                logger.info(f"Tipo binário: {mimetype}, criando PDF informativo")
                pdf_path = f"{arquivo_temp}.pdf"
                message = f"Documento {id_documento} ({tipo_documento}) possui formato binário: {mimetype}"
                create_info_pdf(message, pdf_path, id_documento, tipo_documento)
                
                # Salvar o arquivo original também
                original_path = f"{arquivo_temp}{get_extension_for_mimetype(mimetype)}"
                with open(original_path, 'wb') as f:
                    f.write(conteudo)
                
                logger.debug(f"Arquivo original salvo em: {original_path}")
            
            else:
                # Para outros tipos, criar um PDF com informações básicas
                logger.warning(f"Tipo de arquivo não suportado diretamente: {mimetype}")
                pdf_path = f"{arquivo_temp}.pdf"
                message = f"Documento {id_documento} ({tipo_documento}) possui formato não suportado: {mimetype}"
                create_info_pdf(message, pdf_path, id_documento, tipo_documento)
            
            # Verificar se o PDF foi gerado com sucesso
            if pdf_path and os.path.exists(pdf_path):
                # Adicionar cabeçalho ao PDF com informações do documento
                try:
                    add_document_header(pdf_path, id_documento, tipo_documento)
                    logger.debug(f"Documento {id_documento} processado com sucesso")
                    return {'id': id_documento, 'caminho_pdf': pdf_path}
                except Exception as e:
                    logger.error(f"Erro ao adicionar cabeçalho ao PDF: {str(e)}")
                    return {'id': id_documento, 'caminho_pdf': pdf_path}
            else:
                logger.error(f"Falha ao gerar PDF para o documento {id_documento}")
                return None
                
        except Exception as e:
            last_error = e
            logger.warning(f"Erro na tentativa {retry_count+1} para documento {id_documento}: {str(e)}")
            retry_count += 1
            time.sleep(1)  # Esperar um pouco antes de tentar novamente
    
    # Se chegou aqui, todas as tentativas falharam
    logger.error(f"Falha em todas as tentativas para documento {id_documento}: {str(last_error)}")
    
    # Criar um PDF com informações sobre o erro
    try:
        arquivo_temp = os.path.join(temp_dir, f"doc_{id_documento}")
        pdf_path = f"{arquivo_temp}.pdf"
        message = f"Não foi possível processar o documento {id_documento} após {max_retries} tentativas: {str(last_error)}"
        create_info_pdf(message, pdf_path, id_documento, tipo_documento)
        return {'id': id_documento, 'caminho_pdf': pdf_path}
    except:
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
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    
    width, height = letter
    margin = 72  # 1 inch margins
    y = height - margin
    
    # Título
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(margin, y, f"Documento: {doc_type}")
    y -= 20
    
    pdf.setFont("Helvetica", 10)
    pdf.drawString(margin, y, f"ID: {doc_id}")
    y -= 30
    
    # Dividir o texto em linhas
    pdf.setFont("Courier", 10)
    linha_altura = 12
    max_width = width - 2 * margin
    
    # Função para quebrar texto em linhas
    def wrap_text(text, width, pdf):
        lines = []
        for paragraph in text.split('\n'):
            if len(paragraph) == 0:
                lines.append("")
                continue
                
            line = ""
            for word in paragraph.split():
                # Verificar se a palavra cabe na linha atual
                test_line = line + " " + word if line else word
                test_width = pdf.stringWidth(test_line, "Courier", 10)
                
                if test_width <= width:
                    line = test_line
                else:
                    lines.append(line)
                    line = word
            
            if line:
                lines.append(line)
        
        return lines
    
    # Limitar o texto a no máximo 50.000 caracteres para evitar PDFs muito grandes
    if len(text) > 50000:
        text = text[:50000] + "\n\n... (texto truncado devido ao tamanho)"
    
    lines = wrap_text(text, max_width, pdf)
    
    # Adicionar linhas ao PDF, criando novas páginas quando necessário
    page_num = 1
    for i, line in enumerate(lines):
        # Se não houver mais espaço na página atual, criar uma nova
        if y <= margin:
            pdf.setFont("Helvetica", 8)
            pdf.drawString(margin, margin / 2, f"Página {page_num}")
            pdf.showPage()
            page_num += 1
            y = height - margin
            
            # Título da nova página
            pdf.setFont("Helvetica-Bold", 10)
            pdf.drawString(margin, y, f"Documento: {doc_type} (continuação)")
            y -= 15
            
            pdf.setFont("Helvetica", 8)
            pdf.drawString(margin, y, f"ID: {doc_id}")
            y -= 20
            
            pdf.setFont("Courier", 10)
        
        # Adicionar a linha ao PDF
        pdf.drawString(margin, y, line)
        y -= linha_altura
    
    # Adicionar número da página final
    pdf.setFont("Helvetica", 8)
    pdf.drawString(margin, margin / 2, f"Página {page_num}")
    
    # Salvar o PDF
    pdf.save()
    
    with open(output_path, 'wb') as f:
        f.write(buffer.getvalue())


def create_info_pdf(message, output_path, doc_id, doc_type):
    """
    Cria um PDF informativo quando o tipo de arquivo não é suportado.
    
    Args:
        message (str): Mensagem a ser incluída no PDF
        output_path (str): Caminho para salvar o PDF
        doc_id (str): ID do documento
        doc_type (str): Tipo do documento
    """
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    
    width, height = letter
    margin = 72  # 1 inch margins
    y = height - margin
    
    # Título
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(margin, y, "Informação sobre o Documento")
    y -= 30
    
    # Detalhes do documento
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(margin, y, f"Tipo: {doc_type}")
    y -= 20
    
    pdf.drawString(margin, y, f"ID: {doc_id}")
    y -= 20
    
    pdf.drawString(margin, y, f"Data: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    y -= 40
    
    # Mensagem
    pdf.setFont("Helvetica", 12)
    pdf.drawString(margin, y, "Mensagem:")
    y -= 20
    
    # Dividir a mensagem em linhas
    pdf.setFont("Helvetica", 10)
    linha_altura = 12
    
    # Função para quebrar texto em linhas
    def wrap_message(message, width):
        words = message.split()
        lines = []
        line = ""
        
        for word in words:
            test_line = line + " " + word if line else word
            test_width = pdf.stringWidth(test_line, "Helvetica", 10)
            
            if test_width <= width:
                line = test_line
            else:
                lines.append(line)
                line = word
        
        if line:
            lines.append(line)
        
        return lines
    
    lines = wrap_message(message, width - 2 * margin)
    
    for line in lines:
        pdf.drawString(margin, y, line)
        y -= linha_altura
    
    # Adicionar um aviso sobre como obter o documento original
    y -= 40
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(margin, y, "Nota:")
    y -= 15
    
    pdf.setFont("Helvetica", 10)
    pdf.drawString(margin, y, "Este PDF foi gerado automaticamente como um substituto para")
    y -= 12
    pdf.drawString(margin, y, "o documento original que não pôde ser processado corretamente.")
    y -= 12
    pdf.drawString(margin, y, "Para visualizar o documento original, use a opção 'Baixar Documento'")
    y -= 12
    pdf.drawString(margin, y, "específica para este documento no sistema.")
    
    # Salvar o PDF
    pdf.save()
    
    with open(output_path, 'wb') as f:
        f.write(buffer.getvalue())


def add_document_header(pdf_path, doc_id, doc_type):
    """
    Adiciona um cabeçalho com informações ao PDF existente.
    
    Args:
        pdf_path (str): Caminho do PDF a ser modificado
        doc_id (str): ID do documento
        doc_type (str): Tipo do documento
    """
    try:
        # Verificar se o arquivo pode ser aberto
        with open(pdf_path, 'rb') as file:
            reader = PdfReader(file)
            writer = PdfWriter()
            
            # Adicionar todas as páginas do PDF original
            for i in range(len(reader.pages)):
                writer.add_page(reader.pages[i])
            
            # Adicionar metadados
            metadata = {
                '/Title': f'Documento {doc_id} - {doc_type}',
                '/Author': 'Sistema de Consulta MNI',
                '/Subject': f'Documento {doc_type}',
                '/Keywords': f'MNI, Documento, {doc_id}, {doc_type}',
                '/Producer': 'Sistema de Consulta MNI',
                '/CreationDate': datetime.now().strftime('D:%Y%m%d%H%M%S')
            }
            writer.add_metadata(metadata)
            
            # Salvar o PDF modificado
            with open(pdf_path, 'wb') as output_file:
                writer.write(output_file)
                
    except Exception as e:
        logger.warning(f"Erro ao adicionar cabeçalho ao PDF: {str(e)}")
        # Não lançar exceção, apenas registrar o erro


def get_extension_for_mimetype(mimetype):
    """Helper para obter a extensão apropriada para um mimetype"""
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
        'application/xml': '.xml',
        'text/xml': '.xml',
    }
    return mime_to_extension.get(mimetype, '.bin')


def gerar_pdf_completo_otimizado(num_processo, cpf, senha, limite_docs=None):
    """
    Versão otimizada e mais robusta da função para gerar PDF completo de um processo.
    Implementa melhor tratamento de erros e mais opções para converter tipos de documentos.
    
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
        logger.info(f"Iniciando geração do PDF completo para o processo {num_processo}")
        
        # Consultar o processo para obter lista de documentos
        logger.info(f"Consultando dados do processo {num_processo}")
        resposta_processo = retorna_processo(num_processo, cpf=cpf, senha=senha)
        dados = extract_mni_data(resposta_processo)
        
        if not dados.get('documentos') or len(dados.get('documentos', [])) == 0:
            # Logar quantos documentos foram encontrados para debug
            docs_originais = dados.get('processo', {}).get('documentos', [])
            logger.warning(f"Documentos no formato original: {len(docs_originais)}")
            logger.warning(f"Documentos no formato API: {len(dados.get('documentos', []))}")
            
            return None
            
        # Criar diretório temporário para armazenar arquivos
        temp_dir = tempfile.mkdtemp()
        logger.debug(f"Diretório temporário criado: {temp_dir}")
        
        # Configurar arquivo de saída final
        output_path = os.path.join(temp_dir, f"processo_{num_processo}.pdf")
        documentos = dados['documentos']
        
        # Limitar o número de documentos se necessário
        if limite_docs and limite_docs > 0 and limite_docs < len(documentos):
            logger.info(f"Limitando processamento a {limite_docs} de {len(documentos)} documentos")
            documentos = documentos[:limite_docs]
            output_filename = f"processo_{num_processo}_parcial.pdf"
        else:
            output_filename = f"processo_{num_processo}.pdf"
            
        total_docs = len(documentos)
        
        logger.info(f"Processando {total_docs} documentos do processo {num_processo}")
        
        # Usar um tamanho de lote menor para evitar timeouts
        batch_size = min(5, max(2, total_docs // 10))
        max_workers = min(3, batch_size)  # Limitar paralelismo para melhor estabilidade
        
        # Iniciar com um PDF contendo o cabeçalho
        cabecalho_buffer = gerar_cabecalho_processo(dados)
        with open(output_path, 'wb') as f:
            cabecalho_buffer.seek(0)
            f.write(cabecalho_buffer.getvalue())
        
        # Processamento em lotes para gerenciar melhor a memória
        processados = 0
        erros = 0
        doc_batches = [documentos[i:i+batch_size] for i in range(0, total_docs, batch_size)]
        
        # Reportar o início do processamento em lotes
        logger.info(f"Iniciando processamento em {len(doc_batches)} lotes, com até {batch_size} documentos por lote")
        
        # Processar cada lote
        for batch_num, batch_docs in enumerate(doc_batches, 1):
            batch_start_time = time.time()
            logger.debug(f"Processando lote {batch_num}/{len(doc_batches)} ({len(batch_docs)} documentos)")
            
            # Arquivo temporário para o lote atual
            batch_pdf_path = os.path.join(temp_dir, f"batch_{batch_num}.pdf")
            
            # Processar documentos do lote em paralelo
            batch_results = []
            
            # Definir um timeout para cada worker
            timeout_per_doc = 20  # segundos
            
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_doc = {}
                
                # Submeter tarefas com timeout
                for doc in batch_docs:
                    future = executor.submit(
                        processar_documento_robusto, 
                        num_processo, doc['id'], 
                        doc.get('tipoDocumento', ''), 
                        cpf, senha, temp_dir
                    )
                    future_to_doc[future] = doc
                
                # Coletar resultados conforme são concluídos
                for future in concurrent.futures.as_completed(future_to_doc):
                    doc = future_to_doc[future]
                    try:
                        # Aguardar conclusão com timeout
                        resultado = future.result(timeout=timeout_per_doc)
                        if resultado and resultado.get('caminho_pdf'):
                            batch_results.append(resultado)
                            processados += 1
                            logger.debug(f"Documento {doc['id']} processado com sucesso")
                        else:
                            logger.warning(f"Documento {doc['id']} não gerou PDF válido")
                            erros += 1
                    except concurrent.futures.TimeoutError:
                        logger.warning(f"Timeout ao processar documento {doc['id']}")
                        # Criar um PDF informativo sobre o timeout
                        arquivo_temp = os.path.join(temp_dir, f"doc_{doc['id']}")
                        pdf_path = f"{arquivo_temp}.pdf"
                        message = f"Timeout ao processar documento {doc['id']} ({doc.get('tipoDocumento', '')})"
                        create_info_pdf(message, pdf_path, doc['id'], doc.get('tipoDocumento', ''))
                        batch_results.append({'id': doc['id'], 'caminho_pdf': pdf_path})
                        erros += 1
                    except Exception as e:
                        logger.error(f"Erro ao processar documento {doc['id']}: {str(e)}")
                        erros += 1
            
            # Se nenhum documento foi processado neste lote, continuar para o próximo
            if not batch_results:
                logger.warning(f"Nenhum documento processado no lote {batch_num}")
                continue
                
            # Mesclar os documentos do lote atual
            with PdfMerger() as batch_merger:
                # Ordenar os resultados para manter a ordem original dos documentos
                batch_results.sort(key=lambda r: batch_docs.index(next(d for d in batch_docs if d['id'] == r['id'])))
                
                # Adicionar cada documento ao merger
                for resultado in batch_results:
                    try:
                        batch_merger.append(resultado['caminho_pdf'])
                    except Exception as e:
                        logger.error(f"Erro ao adicionar documento {resultado['id']} ao lote: {str(e)}")
                
                # Salvar o lote em um arquivo temporário
                with open(batch_pdf_path, 'wb') as f:
                    batch_merger.write(f)
            
            # Adicionar o lote ao PDF principal
            with PdfMerger() as merger:
                merger.append(output_path)  # PDF atual
                merger.append(batch_pdf_path)  # Novo lote
                
                # Arquivo temporário para o resultado intermediário
                temp_merged = os.path.join(temp_dir, f"temp_merged_{batch_num}.pdf")
                with open(temp_merged, 'wb') as f:
                    merger.write(f)
                
                # Substituir o arquivo principal pelo mesclado
                os.replace(temp_merged, output_path)
            
            # Remover o arquivo do lote para liberar espaço
            if os.path.exists(batch_pdf_path):
                os.remove(batch_pdf_path)
            
            # Limpar arquivos PDF individuais dos documentos após mesclar o lote
            for resultado in batch_results:
                try:
                    if os.path.exists(resultado['caminho_pdf']):
                        os.remove(resultado['caminho_pdf'])
                except Exception as e:
                    logger.warning(f"Não foi possível remover arquivo temporário: {str(e)}")
            
            batch_time = time.time() - batch_start_time
            progress = (batch_num / len(doc_batches)) * 100
            logger.debug(f"Lote {batch_num} concluído em {batch_time:.2f}s - Progresso: {progress:.1f}%")
        
        # Verificar se pelo menos um documento foi processado
        if processados == 0:
            logger.error("Não foi possível processar nenhum documento")
            return None
            
        # Calcular estatísticas
        taxa_sucesso = (processados / total_docs) * 100
        tempo_total = time.time() - start_time
        
        # Verificar se o arquivo final foi gerado e tem tamanho válido
        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            logger.error("Arquivo PDF final não foi gerado corretamente")
            return None
        
        logger.info(f"PDF gerado com sucesso. Processados: {processados}/{total_docs} documentos ({taxa_sucesso:.1f}%). "
                    f"Tempo total: {tempo_total:.2f} segundos.")
        
        return output_path
            
    except Exception as e:
        logger.error(f"Erro ao gerar PDF completo: {str(e)}", exc_info=True)
        return None
    finally:
        # Certificar-se de que o tempo de execução está disponível
        if 'start_time' in locals():
            tempo_total = time.time() - start_time
            logger.debug(f"Tempo total de execução (incluindo erros): {tempo_total:.2f}s")


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
            
            # Formatar data (AAAAMMDD -> DD/MM/AAAA)
            if len(data_str) == 8:
                data_str = f"{data_str[6:8]}/{data_str[4:6]}/{data_str[0:4]}"
                
            pdf.drawString(72, y, f"Data de Ajuizamento: {data_str}")
            y -= 20
    
    # Adicionar polos do processo, se disponíveis
    if 'processo' in dados_processo and 'polos' in dados_processo['processo']:
        polos = dados_processo['processo']['polos']
        
        y -= 10  # Espaço adicional
        pdf.setFont("Helvetica-Bold", 12)
        pdf.drawString(72, y, "Partes do Processo:")
        y -= 20
        
        pdf.setFont("Helvetica", 10)
        for polo in polos:
            polo_nome = polo.get('polo', 'N/A')
            pdf.drawString(72, y, f"Polo: {polo_nome}")
            y -= 15
            
            # Listar partes do polo
            for parte in polo.get('partes', []):
                nome = parte.get('nome', 'N/A')
                pdf.drawString(90, y, f"- {nome}")
                y -= 15
                
                # Advogados da parte
                if 'advogados' in parte and parte['advogados']:
                    for adv in parte['advogados']:
                        adv_nome = adv.get('nome', 'N/A')
                        adv_oab = adv.get('numeroOAB', '')
                        oab_str = f" (OAB: {adv_oab})" if adv_oab else ''
                        pdf.drawString(108, y, f"Adv. {adv_nome}{oab_str}")
                        y -= 15
            
            y -= 5  # Espaço entre polos
    
    # Adicionar assuntos do processo, se disponíveis
    if 'processo' in dados_processo and 'assuntos' in dados_processo['processo']:
        assuntos = dados_processo['processo']['assuntos']
        
        if assuntos:
            y -= 10  # Espaço adicional
            pdf.setFont("Helvetica-Bold", 12)
            pdf.drawString(72, y, "Assuntos:")
            y -= 20
            
            pdf.setFont("Helvetica", 10)
            for assunto in assuntos:
                descricao = assunto.get('descricao', 'N/A')
                principal = ' (Principal)' if assunto.get('principal') else ''
                pdf.drawString(90, y, f"- {descricao}{principal}")
                y -= 15
    
    # Adicionar lista de documentos
    if 'documentos' in dados_processo:
        documentos = dados_processo['documentos']
        
        # Se tiver muitos documentos, limitamos para não sobrecarregar o cabeçalho
        if len(documentos) > 0:
            y -= 10  # Espaço adicional
            pdf.setFont("Helvetica-Bold", 12)
            pdf.drawString(72, y, f"Documentos do Processo ({len(documentos)} documentos):")
            y -= 20
            
            # Limitar para os primeiros 15 documentos
            pdf.setFont("Helvetica", 9)
            for i, doc in enumerate(documentos[:15]):
                tipo = doc.get('tipoDocumento', 'N/A')
                doc_id = doc.get('id', '')
                
                # Verificar espaço na página
                if y < 100:
                    pdf.drawString(72, y, "(Lista truncada, muitos documentos)")
                    break
                    
                pdf.drawString(90, y, f"- {tipo} (ID: {doc_id})")
                y -= 12
                
            # Se houver mais documentos, indicar
            if len(documentos) > 15:
                pdf.drawString(90, y, f"... e mais {len(documentos) - 15} documentos")
    
    # Adicionar rodapé
    pdf.setFont("Helvetica", 8)  # Usando Helvetica normal em vez de Helvetica-Italic
    pdf.drawString(72, 40, "Este PDF contém todos os documentos do processo judicial, gerado automaticamente.")
    pdf.drawString(72, 30, f"Data de geração: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    
    # Finalizar o PDF
    pdf.save()
    
    # Retornar o buffer para uso posterior
    buffer.seek(0)
    return buffer


if __name__ == "__main__":
    # Este script pode ser usado para testar ou como função auxiliar
    print("Este módulo fornece funções otimizadas para processamento de documentos judiciais.")
    print("Importe este módulo para usar as seguintes funções:")
    print("  - processar_documento_robusto: versão melhorada de processamento de documentos")
    print("  - gerar_pdf_completo_otimizado: versão otimizada de geração de PDF completo")
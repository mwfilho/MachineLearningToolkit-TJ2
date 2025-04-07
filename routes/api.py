from flask import Blueprint, jsonify, send_file, request
import os
import gc
import logging
from funcoes_mni import retorna_processo, retorna_documento_processo, retorna_peticao_inicial_e_anexos
from utils import extract_mni_data, extract_capa_processo
import core
import tempfile
import time
import io
from PyPDF2 import PdfReader, PdfWriter, PdfMerger
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
import weasyprint
import concurrent.futures

# Configure logging
logger = logging.getLogger(__name__)

# Criar o blueprint da API
api = Blueprint('api', __name__, url_prefix='/api/v1')

def get_mni_credentials():
    """Obtém credenciais do MNI dos headers ou environment"""
    cpf = request.headers.get('X-MNI-CPF') or os.environ.get('MNI_ID_CONSULTANTE')
    senha = request.headers.get('X-MNI-SENHA') or os.environ.get('MNI_SENHA_CONSULTANTE')
    return cpf, senha

@api.before_request
def log_request_info():
    """Log detalhes da requisição para debug"""
    logger.debug('Headers: %s', dict(request.headers))
    logger.debug('Body: %s', request.get_data())
    logger.debug('URL: %s', request.url)

@api.route('/processo/<num_processo>', methods=['GET'])
def get_processo(num_processo):
    """
    Retorna os dados do processo incluindo lista de documentos
    """
    try:
        logger.debug(f"API: Consultando processo {num_processo}")
        cpf, senha = get_mni_credentials()

        if not cpf or not senha:
            return jsonify({
                'erro': 'Credenciais MNI não fornecidas',
                'mensagem': 'Forneça as credenciais nos headers X-MNI-CPF e X-MNI-SENHA'
            }), 401

        resposta = retorna_processo(num_processo, cpf=cpf, senha=senha)

        # Extrair dados relevantes
        dados = extract_mni_data(resposta)
        return jsonify(dados)

    except Exception as e:
        logger.error(f"API: Erro ao consultar processo: {str(e)}", exc_info=True)
        return jsonify({
            'erro': str(e),
            'mensagem': 'Erro ao consultar processo'
        }), 500

@api.route('/processo/<num_processo>/documento/<num_documento>', methods=['GET'])
def download_documento(num_processo, num_documento):
    """
    Faz download de um documento específico do processo
    """
    try:
        logger.debug(f"API: Download do documento {num_documento} do processo {num_processo}")
        cpf, senha = get_mni_credentials()

        if not cpf or not senha:
            return jsonify({
                'erro': 'Credenciais MNI não fornecidas',
                'mensagem': 'Forneça as credenciais nos headers X-MNI-CPF e X-MNI-SENHA'
            }), 401

        resposta = retorna_documento_processo(num_processo, num_documento, cpf=cpf, senha=senha)

        if 'msg_erro' in resposta:
            return jsonify({
                'erro': resposta['msg_erro'],
                'mensagem': 'Erro ao baixar documento'
            }), 404

        # Criar arquivo temporário para download
        extensao = core.mime_to_extension.get(resposta['mimetype'], '.bin')
        temp_dir = tempfile.mkdtemp()
        file_path = os.path.join(temp_dir, f'{num_documento}{extensao}')

        with open(file_path, 'wb') as f:
            f.write(resposta['conteudo'])

        return send_file(
            file_path,
            mimetype=resposta['mimetype'],
            as_attachment=True,
            download_name=f'documento_{num_documento}{extensao}'
        )

    except Exception as e:
        logger.error(f"API: Erro ao baixar documento: {str(e)}", exc_info=True)
        return jsonify({
            'erro': str(e),
            'mensagem': 'Erro ao baixar documento'
        }), 500
        
@api.route('/processo/<num_processo>/peticao-inicial', methods=['GET'])
def get_peticao_inicial(num_processo):
    """
    Retorna a petição inicial e seus anexos para o processo informado
    """
    try:
        logger.debug(f"API: Buscando petição inicial do processo {num_processo}")
        cpf, senha = get_mni_credentials()

        if not cpf or not senha:
            return jsonify({
                'erro': 'Credenciais MNI não fornecidas',
                'mensagem': 'Forneça as credenciais nos headers X-MNI-CPF e X-MNI-SENHA'
            }), 401

        resposta = retorna_peticao_inicial_e_anexos(num_processo, cpf=cpf, senha=senha)

        if 'msg_erro' in resposta:
            return jsonify({
                'erro': resposta['msg_erro'],
                'mensagem': 'Erro ao buscar petição inicial'
            }), 404

        return jsonify(resposta)

    except Exception as e:
        logger.error(f"API: Erro ao buscar petição inicial: {str(e)}", exc_info=True)
        return jsonify({
            'erro': str(e),
            'mensagem': 'Erro ao buscar petição inicial'
        }), 500
        
@api.route('/processo/<num_processo>/capa', methods=['GET'])
def get_capa_processo(num_processo):
    """
    Retorna apenas os dados da capa do processo (sem documentos),
    incluindo dados básicos, assuntos, polos e movimentações
    """
    try:
        logger.debug(f"API: Consultando capa do processo {num_processo}")
        cpf, senha = get_mni_credentials()

        if not cpf or not senha:
            return jsonify({
                'erro': 'Credenciais MNI não fornecidas',
                'mensagem': 'Forneça as credenciais nos headers X-MNI-CPF e X-MNI-SENHA'
            }), 401

        # Usando o parâmetro incluir_documentos=False para melhor performance
        resposta = retorna_processo(num_processo, cpf=cpf, senha=senha, incluir_documentos=False)

        # Extrair apenas os dados da capa do processo
        dados = extract_capa_processo(resposta)
        return jsonify(dados)

    except Exception as e:
        logger.error(f"API: Erro ao consultar capa do processo: {str(e)}", exc_info=True)
        return jsonify({
            'erro': str(e),
            'mensagem': 'Erro ao consultar capa do processo'
        }), 500
        
        
@api.route('/processo/<num_processo>/pdf-completo', methods=['GET'])
def gerar_pdf_completo(num_processo):
    """
    Gera um PDF único contendo todos os documentos do processo.
    Lida com documentos em diferentes formatos (PDF e HTML).
    
    Args:
        num_processo (str): Número do processo judicial
        
    Returns:
        O arquivo PDF combinado para download ou uma mensagem de erro
    """
    try:
        start_time = time.time()
        logger.debug(f"API: Iniciando geração do PDF completo para o processo {num_processo}")
        
        # Obter credenciais
        cpf, senha = get_mni_credentials()
        if not cpf or not senha:
            return jsonify({
                'erro': 'Credenciais MNI não fornecidas',
                'mensagem': 'Forneça as credenciais nos headers X-MNI-CPF e X-MNI-SENHA'
            }), 401
            
        # Consultar o processo para obter lista de documentos
        resposta_processo = retorna_processo(num_processo, cpf=cpf, senha=senha)
        dados = extract_mni_data(resposta_processo)
        
        if not dados.get('documentos') or len(dados.get('documentos', [])) == 0:
            # Logar quantos documentos foram encontrados em cada estrutura para debug
            docs_originais = dados.get('processo', {}).get('documentos', [])
            logger.debug(f"Documentos no formato original: {len(docs_originais)}")
            logger.debug(f"Documentos no formato API: {len(dados.get('documentos', []))}")
            
            return jsonify({
                'erro': 'Processo sem documentos',
                'mensagem': 'O processo não possui documentos para gerar PDF ou não foi possível acessá-los com as credenciais fornecidas'
            }), 404
            
        documentos = dados['documentos']
        total_documentos = len(documentos)
        logger.debug(f"Encontrados {total_documentos} documentos no processo {num_processo}")
        logger.debug(f"Primeiro documento: {documentos[0] if documentos else 'Nenhum'}")
        
        # Verificar se o processo tem muitos documentos, limitar para evitar problemas de memória
        max_docs_por_requisicao = 20
        if total_documentos > max_docs_por_requisicao:
            logger.warning(f"Processo com muitos documentos ({total_documentos}). Limitando a {max_docs_por_requisicao} para evitar problemas de memória.")
            documentos = documentos[:max_docs_por_requisicao]
            
            # Avisar ao cliente que o PDF está truncado
            retorno_truncado = True
        else:
            retorno_truncado = False
        
        # Criar diretório temporário para armazenar arquivos
        temp_dir = tempfile.mkdtemp()
        pdf_merger = PdfMerger()
        
        # Verificar se o PDF está truncado
        truncado_info = ""
        if 'retorno_truncado' in locals() and retorno_truncado:
            truncado_info = f"ATENÇÃO: O PDF está truncado! O processo contém {total_documentos} documentos, mas apenas os primeiros {max_docs_por_requisicao} foram incluídos para evitar problemas de memória."
        
        # Adicionar cabeçalho com informações do processo
        cabecalho_buffer = gerar_cabecalho_processo(dados, truncado_info)
        pdf_merger.append(cabecalho_buffer)
        
        # Contador de documentos processados
        processados = 0
        erros = 0
        
        # Determinar o máximo de workers baseado na quantidade de documentos
        max_workers = min(10, len(documentos))  # Limita a 10 threads simultâneas
        
        # Processar documentos em lotes para economizar memória
        tamanho_lote = 3  # Processar apenas 3 documentos por vez para minimizar uso de memória
        total_docs = len(documentos)
        pdf_paths = []
        
        for inicio_lote in range(0, total_docs, tamanho_lote):
            fim_lote = min(inicio_lote + tamanho_lote, total_docs)
            lote_atual = documentos[inicio_lote:fim_lote]
            logger.info(f"Processando lote de documentos {inicio_lote+1}-{fim_lote} de {total_docs}")
            
            # Limitar o número máximo de workers ao tamanho do lote
            lote_max_workers = min(max_workers, len(lote_atual)) 
            
            # Usar ThreadPoolExecutor para processamento paralelo do lote atual
            with concurrent.futures.ThreadPoolExecutor(max_workers=lote_max_workers) as executor:
                # Mapear a função de processamento para cada documento do lote
                future_to_doc = {
                    executor.submit(
                        processar_documento, 
                        num_processo, doc['id'], 
                        doc.get('tipoDocumento', ''), 
                        cpf, senha, temp_dir
                    ): (doc, documentos.index(doc))  # Incluir índice original 
                    for doc in lote_atual
                }
                
                # Processar resultados conforme forem concluídos
                for future in concurrent.futures.as_completed(future_to_doc):
                    doc, indice_original = future_to_doc[future]
                    try:
                        resultado = future.result()
                        if resultado and resultado.get('caminho_pdf'):
                            try:
                                # Armazenar caminho e ID para processar na ordem correta depois
                                logger.debug(f"Documento {doc['id']} processado com sucesso")
                                pdf_paths.append({
                                    'id': doc['id'],
                                    'caminho': resultado['caminho_pdf'],
                                    'index': indice_original  # Manter a ordem original
                                })
                                processados += 1
                            except Exception as e:
                                logger.error(f"Erro ao registrar documento {doc['id']}: {str(e)}", exc_info=True)
                                erros += 1
                        else:
                            logger.warning(f"Documento {doc['id']} não gerou PDF válido")
                            erros += 1
                    except Exception as e:
                        logger.error(f"Erro ao processar documento {doc['id']}: {str(e)}", exc_info=True)
                        erros += 1
            
            # Liberar um pouco de memória antes de processar o próximo lote
            gc.collect()
        
        # Ordenar PDFs conforme a ordem original dos documentos
        pdf_paths.sort(key=lambda x: x['index'])
        
        # Adicionar PDFs ao merger na ordem correta (também em lotes para economizar memória)
        for i, pdf_info in enumerate(pdf_paths):
            try:
                logger.debug(f"Adicionando documento {i+1}/{len(pdf_paths)} ao PDF combinado")
                pdf_merger.append(pdf_info['caminho'])
                
                # A cada 5 documentos, liberar memória
                if (i + 1) % 5 == 0:
                    gc.collect()
            except Exception as e:
                logger.error(f"Erro ao adicionar documento {pdf_info['id']} ao PDF: {str(e)}", exc_info=True)
                erros += 1
                processados -= 1  # Ajustar contador
        
        if processados == 0:
            erros_message = f"Total de erros: {erros}"
            if erros > 0:
                erros_message += ". Verifique os logs para mais detalhes."
                
            return jsonify({
                'erro': 'Falha no processamento',
                'mensagem': f'Não foi possível processar nenhum documento do processo {num_processo}. {erros_message}',
                'total_documentos': len(documentos),
                'erros': erros
            }), 500
            
        # Gerar o arquivo PDF final
        output_path = os.path.join(temp_dir, f"processo_{num_processo}.pdf")
        with open(output_path, 'wb') as f:
            pdf_merger.write(f)
            
        # Fechar o PDF merger para liberar recursos
        pdf_merger.close()
        
        # Calcular estatísticas
        total_docs = len(documentos)
        taxa_sucesso = (processados / total_docs) * 100
        tempo_total = time.time() - start_time
        
        logger.info(f"PDF gerado com sucesso. Processados: {processados}/{total_docs} documentos ({taxa_sucesso:.1f}%). "
                    f"Tempo total: {tempo_total:.2f} segundos.")
        
        # Criar cabeçalho personalizado para indicar se o PDF está truncado
        headers = {}
        if 'retorno_truncado' in locals() and retorno_truncado:
            headers['X-PDF-Truncado'] = 'true'
            headers['X-Total-Documentos'] = str(total_documentos)
            headers['X-Documentos-Incluidos'] = str(max_docs_por_requisicao)
        
        return send_file(
            output_path,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f'processo_completo_{num_processo}.pdf',
            headers=headers
        )
            
    except Exception as e:
        logger.error(f"API: Erro ao gerar PDF completo: {str(e)}", exc_info=True)
        return jsonify({
            'erro': str(e),
            'mensagem': 'Erro ao gerar PDF completo do processo'
        }), 500


def gerar_cabecalho_processo(dados_processo, truncado_info=""):
    """
    Gera um PDF contendo informações básicas do processo como cabeçalho.
    
    Args:
        dados_processo (dict): Dados do processo
        truncado_info (str, optional): Mensagem a ser exibida quando o PDF está truncado
        
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
    
    # Adicionar informação de truncamento se houver
    if truncado_info:
        # Adicionar uma caixa de alerta vermelha
        pdf.setFillColorRGB(1, 0.9, 0.9)  # Vermelho claro
        pdf.rect(72, y-30, 450, 50, fill=True)
        
        # Texto de alerta
        pdf.setFillColorRGB(0.8, 0, 0)  # Vermelho escuro
        pdf.setFont("Helvetica-Bold", 12)
        pdf.drawString(82, y-10, "ATENÇÃO: PDF TRUNCADO")
        
        # Mensagem detalhada
        pdf.setFillColorRGB(0, 0, 0)  # Preto
        pdf.setFont("Helvetica", 10)
        
        # Quebrar o texto se for muito longo
        linhas = []
        palavras = truncado_info.split()
        linha_atual = ""
        
        for palavra in palavras:
            teste_linha = linha_atual + " " + palavra if linha_atual else palavra
            if pdf.stringWidth(teste_linha, "Helvetica", 10) < 430:
                linha_atual = teste_linha
            else:
                linhas.append(linha_atual)
                linha_atual = palavra
        
        if linha_atual:
            linhas.append(linha_atual)
        
        # Escrever as linhas
        for i, linha in enumerate(linhas):
            pdf.drawString(82, y-20-(i*12), linha)
        
        y -= 60  # Espaçamento extra depois da caixa de alerta
    
    # Adicionar lista de documentos
    pdf.setFillColorRGB(0, 0, 0)  # Voltar para preto
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
        try:
            # Obter o documento
            resposta = retorna_documento_processo(num_processo, id_documento, cpf=cpf, senha=senha)
            
            if resposta is None:
                logger.error(f"Resposta nula para documento {id_documento}")
                arquivo_temp = os.path.join(temp_dir, f"doc_{id_documento}")
                pdf_path = f"{arquivo_temp}.pdf"
                message = f"Erro ao obter documento {id_documento}: Resposta nula da API"
                create_info_pdf(message, pdf_path, id_documento, tipo_documento)
                return {'id': id_documento, 'caminho_pdf': pdf_path}
            
            if 'msg_erro' in resposta:
                logger.error(f"Erro ao obter documento {id_documento}: {resposta['msg_erro']}")
                # Criar um PDF informativo sobre o erro
                arquivo_temp = os.path.join(temp_dir, f"doc_{id_documento}")
                pdf_path = f"{arquivo_temp}.pdf"
                message = f"Erro ao obter documento {id_documento}: {resposta['msg_erro']}"
                create_info_pdf(message, pdf_path, id_documento, tipo_documento)
                return {'id': id_documento, 'caminho_pdf': pdf_path}
        except Exception as e:
            logger.error(f"Exceção ao buscar documento {id_documento}: {str(e)}", exc_info=True)
            arquivo_temp = os.path.join(temp_dir, f"doc_{id_documento}")
            pdf_path = f"{arquivo_temp}.pdf"
            message = f"Falha ao buscar documento {id_documento}: {str(e)}"
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
                logger.error(f"Erro ao criar PDF de texto: {str(e)}")
                return None
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
        logger.error(f"Erro ao processar documento {id_documento}: {str(e)}", exc_info=True)
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
            if not paragraph:
                lines.append('')
                continue
                
            words = paragraph.split(' ')
            line = ''
            
            for word in words:
                test_line = line + word + ' '
                if pdf.stringWidth(test_line, "Courier", 10) < width:
                    line = test_line
                else:
                    lines.append(line)
                    line = word + ' '
            
            if line:
                lines.append(line)
                
        return lines
    
    lines = wrap_text(text, max_width, pdf)
    
    for line in lines:
        if y < margin:
            pdf.showPage()
            y = height - margin
            pdf.setFont("Courier", 10)
            
        pdf.drawString(margin, y, line)
        y -= linha_altura
    
    pdf.showPage()
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
    
    # Título
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(72, height - 72, "INFORMAÇÃO DO DOCUMENTO")
    
    # Informações do documento
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(72, height - 100, f"Documento: {doc_type}")
    pdf.drawString(72, height - 120, f"ID: {doc_id}")
    
    # Mensagem
    pdf.setFont("Helvetica", 12)
    pdf.drawString(72, height - 160, message)
    pdf.drawString(72, height - 180, "Este documento não pôde ser convertido para PDF.")
    
    pdf.showPage()
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
        # Verificar se o arquivo PDF é válido
        try:
            with open(pdf_path, 'rb') as test_file:
                test_content = test_file.read(20)  # Ler primeiros bytes
                if not test_content.startswith(b'%PDF'):
                    logger.error(f"Arquivo {pdf_path} não é um PDF válido")
                    # Se não for PDF válido, criar um PDF informativo
                    create_info_pdf(f"Documento {doc_id} não pôde ser processado - arquivo inválido", 
                                   pdf_path, doc_id, doc_type)
                    return True  # Retornar True para evitar erro
        except Exception as e:
            logger.error(f"Erro ao verificar PDF {pdf_path}: {str(e)}")
            # Recriar arquivo se estiver corrompido
            create_info_pdf(f"Documento {doc_id} não pôde ser processado: {str(e)}", 
                           pdf_path, doc_id, doc_type)
            return True  # Retornar True para evitar erro
        
        # Criar um novo arquivo para armazenar o resultado
        temp_output = f"{pdf_path}.temp.pdf"
        
        # Ler o PDF existente
        try:
            reader = PdfReader(pdf_path)
            writer = PdfWriter()
        except Exception as e:
            logger.error(f"Erro ao ler PDF {pdf_path}: {str(e)}")
            # Recriar arquivo se estiver corrompido
            create_info_pdf(f"Documento {doc_id} não pôde ser lido: {str(e)}", 
                           pdf_path, doc_id, doc_type)
            return True  # Retornar True para evitar erro
        
        # Para cada página do PDF original
        for i in range(len(reader.pages)):
            page = reader.pages[i]
            
            # Se for a primeira página, adicionar o cabeçalho
            if i == 0:
                # Criar um PDF com o cabeçalho
                packet = io.BytesIO()
                can = canvas.Canvas(packet, pagesize=letter)
                
                # Desenhar um retângulo cinza como plano de fundo para o cabeçalho
                can.setFillColorRGB(0.9, 0.9, 0.9)  # Cinza claro
                can.rect(10, 10, 575, 50, fill=True)
                
                # Adicionar texto do cabeçalho
                can.setFillColorRGB(0, 0, 0)  # Preto
                can.setFont("Helvetica-Bold", 12)
                can.drawString(20, 40, f"Documento: {doc_type}")
                can.setFont("Helvetica", 10)
                can.drawString(20, 25, f"ID: {doc_id}")
                
                can.save()
                
                # Mover para o início do buffer
                packet.seek(0)
                header_pdf = PdfReader(packet)
                header_page = header_pdf.pages[0]
                
                # Sobrepor o cabeçalho na página original
                page.merge_page(header_page)
            
            # Adicionar a página ao PDF de saída
            writer.add_page(page)
        
        # Salvar o PDF modificado
        with open(temp_output, 'wb') as f:
            writer.write(f)
            
        # Substituir o PDF original pelo modificado
        os.replace(temp_output, pdf_path)
        
    except Exception as e:
        logger.error(f"Erro ao adicionar cabeçalho ao PDF: {str(e)}")
        # Se falhar, não modifica o arquivo original
        return False
        
    return True
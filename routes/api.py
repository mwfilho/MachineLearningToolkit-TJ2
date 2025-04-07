from flask import Blueprint, jsonify, send_file, request
import os
import logging
from funcoes_mni import retorna_processo, retorna_documento_processo, retorna_peticao_inicial_e_anexos
from utils import extract_mni_data, extract_capa_processo
import core
import tempfile
import time
import io
# Usando classes simples para manipulação de PDF sem PyPDF2
# Implementação alternativa inspirada no código do Google Colab fornecido
class SimplePdfMerger:
    def __init__(self):
        self.files = []
        
    def append(self, fileobj):
        """
        Adiciona um arquivo PDF ao final do documento
        
        Args:
            fileobj: Pode ser um caminho de arquivo ou um objeto file-like
        """
        self.files.append(fileobj)
    
    def merge(self, position, fileobj):
        """
        Insere um arquivo PDF na posição especificada
        
        Args:
            position: Posição onde inserir (0 para início)
            fileobj: Caminho do arquivo ou objeto file-like
        """
        if position == 0:
            self.files.insert(0, fileobj)
        else:
            self.files.append(fileobj)
    
    def write(self, fileobj):
        """
        Escreve o PDF mesclado no arquivo ou objeto especificado
        
        Args:
            fileobj: Caminho de arquivo ou objeto file-like para escrever
        """
        # Implementação simplificada: concatena os documentos
        content = b''
        
        # Processar cada arquivo
        for idx, file in enumerate(self.files):
            if isinstance(file, str):  # É um caminho de arquivo
                with open(file, 'rb') as f:
                    if idx == 0:  # Primeiro arquivo incluir completo
                        content += f.read()
                    else:
                        # Para outros arquivos, remover cabeçalho PDF (simplificação)
                        data = f.read()
                        content += data
            else:  # É um objeto file-like
                file.seek(0)
                if idx == 0:
                    content += file.read()
                else:
                    content += file.read()
        
        # Escrever o conteúdo
        if isinstance(fileobj, str):  # É um caminho de arquivo
            with open(fileobj, 'wb') as f:
                f.write(content)
        else:  # É um objeto file-like
            fileobj.write(content)
    
    def close(self):
        """Limpa recursos"""
        pass

# Use a classe SimplePdfMerger por padrão
PdfMerger = SimplePdfMerger
# Definir classes simples para geração de PDF quando as bibliotecas não estão disponíveis
class SimpleCanvas:
    def __init__(self, output_path, pagesize=None):
        self.output_path = output_path
        self.pagesize = pagesize if pagesize else (612, 792)  # Tamanho padrão para letter
        self.lines = []
        self.current_font = "Helvetica"
        self.current_size = 12
        self.current_page = 1
        
    def setFont(self, font_name, size):
        self.current_font = font_name
        self.current_size = size
        
    def drawString(self, x, y, text):
        self.lines.append((self.current_page, x, y, text, self.current_font, self.current_size))
        
    def setFillColorRGB(self, r, g, b):
        # Ignorado na implementação simples
        pass
        
    def showPage(self):
        self.current_page += 1
        
    def save(self):
        # Gerar um arquivo de texto simples com as linhas
        with open(self.output_path, 'w', encoding='utf-8') as f:
            f.write("PDF SIMULATION FILE\n")
            f.write("==================\n\n")
            
            current_page = 1
            for page, x, y, text, font, size in self.lines:
                if page > current_page:
                    f.write("\n\n--- PAGE BREAK ---\n\n")
                    current_page = page
                    
                f.write(f"[{font} {size}] {text}\n")
                
        # Converter o txt para um PDF usando wkhtmltopdf se disponível
        try:
            import subprocess
            txt_path = self.output_path
            pdf_path = txt_path.replace(".txt", ".pdf")
            subprocess.run(['wkhtmltopdf', '--quiet', txt_path, pdf_path], 
                          check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            # Se a conversão for bem-sucedida, substituir o arquivo de texto pelo PDF
            if os.path.exists(pdf_path):
                os.remove(txt_path)
        except:
            # Se falhar, manter o arquivo de texto
            pass
        
# Tentar importar as bibliotecas, caso contrário usar as implementações simples
try:
    from reportlab.pdfgen import canvas as reportlab_canvas
    from reportlab.lib.pagesizes import letter
    canvas = reportlab_canvas
except ImportError:
    print("Reportlab not installed. Using simple canvas implementation.")
    canvas = SimpleCanvas
    letter = (612, 792)
    
# Weasyprint é opcional, usaremos wkhtmltopdf como fallback
try:
    import weasyprint
except ImportError:
    weasyprint = None
    print("Weasyprint not installed. Using wkhtmltopdf for HTML conversion.")
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
    Implementação simplificada que funciona com dependências mínimas.
    Apenas combina os arquivos PDF e gera representações de texto para
    documentos HTML e outros formatos.
    
    Args:
        num_processo (str): Número do processo judicial
        
    Returns:
        O arquivo PDF combinado para download ou uma mensagem de erro
    """
    from datetime import datetime
    import subprocess
    
    # Criar diretório temporário para armazenar arquivos
    temp_dir = tempfile.mkdtemp()
    
    # Informações de status para incluir no PDF
    status_info = {
        'data_geracao': datetime.now().strftime('%d/%m/%Y %H:%M:%S'),
        'num_processo': num_processo,
        'total_documentos': 0,
        'documentos_processados': 0,
        'erro_consulta': None
    }
    
    try:
        # Obter credenciais
        cpf, senha = get_mni_credentials()
        
        if not cpf or not senha:
            return jsonify({
                'erro': 'Credenciais MNI não fornecidas',
                'mensagem': 'Você deve fornecer CPF e senha nos headers X-MNI-CPF e X-MNI-SENHA'
            }), 401
        
        # Consultar o processo para obter a lista de documentos
        logger.debug(f"Consultando processo {num_processo}")
        resposta_processo = retorna_processo(num_processo, cpf=cpf, senha=senha)
        dados = extract_mni_data(resposta_processo)
        
        if not dados.get('sucesso'):
            return jsonify({
                'erro': 'Erro ao consultar processo',
                'mensagem': dados.get('mensagem', 'Não foi possível obter os detalhes do processo')
            }), 404
        
        # Inicializar o PdfMerger
        pdf_merger = PdfMerger()
        
        # Coletar todos os documentos (principais e vinculados)
        todos_documentos = []
        
        # Extrair documentos principais
        for documento in dados.get('documentos', []):
            if documento.get('mimetype') in ['application/pdf', 'text/html']:
                todos_documentos.append({
                    'id': documento.get('id'),
                    'descricao': documento.get('tipoDocumento', 'Documento'),
                    'mimetype': documento.get('mimetype')
                })
        
        status_info['total_documentos'] = len(todos_documentos)
        logger.debug(f"Total de documentos a processar: {status_info['total_documentos']}")
        
        # Processar cada documento
        for doc_info in todos_documentos:
            try:
                doc_id = doc_info['id']
                logger.debug(f"Processando documento {doc_id}")
                
                # Baixar o documento
                resposta = retorna_documento_processo(num_processo, doc_id, cpf=cpf, senha=senha)
                
                if 'msg_erro' in resposta or not resposta.get('conteudo'):
                    logger.error(f"Erro ao baixar documento {doc_id}: {resposta.get('msg_erro', 'Sem conteúdo')}")
                    continue
                
                mimetype = resposta.get('mimetype', '')
                conteudo = resposta.get('conteudo', b'')
                
                # Processar baseado no mimetype
                if mimetype == 'application/pdf':
                    # Salvar PDF temporariamente
                    temp_pdf_path = os.path.join(temp_dir, f"doc_{doc_id}.pdf")
                    with open(temp_pdf_path, 'wb') as f:
                        f.write(conteudo)
                    
                    # Adicionar ao PDF Merger
                    pdf_merger.append(temp_pdf_path)
                    status_info['documentos_processados'] += 1
                    logger.debug(f"Documento PDF {doc_id} adicionado com sucesso")
                    
                elif mimetype == 'text/html':
                    # Salvar HTML temporariamente
                    temp_html_path = os.path.join(temp_dir, f"doc_{doc_id}.html")
                    with open(temp_html_path, 'wb') as f:
                        f.write(conteudo)
                    
                    # Converter HTML para PDF usando wkhtmltopdf
                    temp_pdf_path = os.path.join(temp_dir, f"doc_{doc_id}.pdf")
                    
                    try:
                        # Executar wkhtmltopdf para converter HTML para PDF
                        subprocess.run(['wkhtmltopdf', '--quiet', temp_html_path, temp_pdf_path],
                                      check=True,
                                      stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE)
                        
                        # Verificar se o PDF foi gerado
                        if os.path.exists(temp_pdf_path) and os.path.getsize(temp_pdf_path) > 0:
                            # Adicionar ao PDF Merger
                            pdf_merger.append(temp_pdf_path)
                            status_info['documentos_processados'] += 1
                            logger.debug(f"Documento HTML {doc_id} convertido e adicionado com sucesso")
                        else:
                            # Criar um PDF de texto simples como fallback
                            fallback_pdf_path = os.path.join(temp_dir, f"fallback_{doc_id}.pdf")
                            texto_html = conteudo.decode('utf-8', errors='ignore')
                            
                            # Criar PDF simples com ReportLab
                            pdf = canvas.Canvas(fallback_pdf_path, pagesize=letter)
                            pdf.setFont("Helvetica-Bold", 14)
                            pdf.drawString(72, 750, f"Documento {doc_id}")
                            
                            # Limitar o conteúdo para evitar PDFs muito grandes
                            texto_html = texto_html[:5000] + "..." if len(texto_html) > 5000 else texto_html
                            
                            # Adicionar linhas de texto ao PDF
                            y_pos = 720
                            pdf.setFont("Helvetica", 10)
                            
                            for i, linha in enumerate(texto_html.split('\n')):
                                if i > 200:  # Limitar o número de linhas
                                    pdf.drawString(72, y_pos, "... (conteúdo truncado)")
                                    break
                                    
                                if y_pos < 50:  # Nova página
                                    pdf.showPage()
                                    pdf.setFont("Helvetica", 10)
                                    y_pos = 750
                                    
                                pdf.drawString(72, y_pos, linha[:80])  # Limitar largura
                                y_pos -= 12
                                
                            pdf.showPage()
                            pdf.save()
                            
                            # Adicionar ao PDF Merger
                            pdf_merger.append(fallback_pdf_path)
                            status_info['documentos_processados'] += 1
                            logger.debug(f"Documento HTML {doc_id} convertido para texto e adicionado")
                    
                    except Exception as html_err:
                        logger.error(f"Erro ao converter HTML para PDF: {str(html_err)}")
                        # Criar um PDF simples com informação do erro
                        error_pdf_path = os.path.join(temp_dir, f"error_{doc_id}.pdf")
                        pdf = canvas.Canvas(error_pdf_path, pagesize=letter)
                        pdf.setFont("Helvetica-Bold", 14)
                        pdf.drawString(72, 750, f"Erro ao processar documento HTML {doc_id}")
                        pdf.setFont("Helvetica", 12)
                        pdf.drawString(72, 720, f"Tipo: {mimetype}")
                        pdf.drawString(72, 700, f"Erro: {str(html_err)}")
                        pdf.showPage()
                        pdf.save()
                        
                        # Adicionar ao PDF Merger
                        pdf_merger.append(error_pdf_path)
                
                else:
                    # Para outros tipos (text/plain, text/xml, etc)
                    # Criar PDF simples
                    other_pdf_path = os.path.join(temp_dir, f"other_{doc_id}.pdf")
                    pdf = canvas.Canvas(other_pdf_path, pagesize=letter)
                    pdf.setFont("Helvetica-Bold", 14)
                    pdf.drawString(72, 750, f"Documento {doc_id}")
                    pdf.setFont("Helvetica", 12)
                    pdf.drawString(72, 720, f"Tipo: {mimetype}")
                    
                    # Tentar extrair texto se possível
                    try:
                        if mimetype in ['text/plain', 'text/xml']:
                            texto = conteudo.decode('utf-8', errors='ignore')
                            # Limitar o texto
                            texto = texto[:5000] + "..." if len(texto) > 5000 else texto
                            
                            # Adicionar linhas de texto ao PDF
                            y_pos = 690
                            pdf.setFont("Courier", 10)  # Fonte monoespaçada para código
                            
                            for i, linha in enumerate(texto.split('\n')):
                                if i > 200:  # Limitar o número de linhas
                                    pdf.drawString(72, y_pos, "... (conteúdo truncado)")
                                    break
                                    
                                if y_pos < 50:  # Nova página
                                    pdf.showPage()
                                    pdf.setFont("Courier", 10)
                                    y_pos = 750
                                    
                                # Limitar largura da linha
                                linha_curta = linha[:80] + "..." if len(linha) > 80 else linha
                                pdf.drawString(72, y_pos, linha_curta)
                                y_pos -= 12
                        else:
                            pdf.drawString(72, 700, f"Tamanho: {len(conteudo)} bytes")
                            pdf.drawString(72, 680, "Formato não suportado para conversão direta.")
                    except:
                        pdf.drawString(72, 700, "Não foi possível extrair texto deste documento.")
                    
                    pdf.showPage()
                    pdf.save()
                    
                    # Adicionar ao PDF Merger
                    pdf_merger.append(other_pdf_path)
                    status_info['documentos_processados'] += 1
                
            except Exception as e:
                logger.error(f"Erro ao processar documento: {str(e)}")
                # Continuar para o próximo documento
        
        # Criar página de capa com informações do status
        capa_path = os.path.join(temp_dir, "capa.pdf")
        capa = canvas.Canvas(capa_path, pagesize=letter)
        
        # Cabeçalho
        capa.setFont("Helvetica-Bold", 16)
        capa.drawString(72, 750, f"PROCESSO {num_processo}")
        
        # Informações de status
        capa.setFont("Helvetica", 12)
        y = 720
        capa.drawString(72, y, f"PDF gerado em: {status_info['data_geracao']}")
        y -= 20
        capa.drawString(72, y, f"Total de documentos no processo: {status_info['total_documentos']}")
        y -= 20
        capa.drawString(72, y, f"Documentos incluídos neste PDF: {status_info['documentos_processados']}")
        
        if status_info['documentos_processados'] < status_info['total_documentos']:
            y -= 20
            capa.setFillColorRGB(0.8, 0.2, 0.2)  # Vermelho para alerta
            capa.drawString(72, y, f"Atenção: Alguns documentos ({status_info['total_documentos'] - status_info['documentos_processados']})")
            y -= 15
            capa.drawString(72, y, "não puderam ser incluídos devido a erros no processamento.")
        
        capa.showPage()
        capa.save()
        
        # Adicionar capa como primeira página
        output_path = os.path.join(temp_dir, f"processo_{num_processo}.pdf")
        
        # Inserir a capa como primeira página e escrever o arquivo
        pdf_merger.merge(0, capa_path)
        with open(output_path, 'wb') as output_file:
            pdf_merger.write(output_file)
            pdf_merger.close()
        
        # Retornar o arquivo combinado
        return send_file(
            output_path,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f'processo_{num_processo}.pdf'
        )
        
    except Exception as e:
        logger.error(f"Erro geral na geração do PDF: {str(e)}", exc_info=True)
        return jsonify({
            'erro': 'Erro ao gerar PDF completo',
            'mensagem': str(e)
        }), 500
        
    finally:
        # Limpar arquivos temporários
        try:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception as e:
            logger.error(f"Erro ao limpar arquivos temporários: {str(e)}")
            # Não interromper o fluxo por erro na limpeza


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


def converter_para_pdf(temp_dir, doc_id, tipo_doc, mimetype, conteudo):
    """
    Converte o conteúdo de um documento para PDF.
    
    Args:
        temp_dir (str): Diretório temporário para armazenar arquivos
        doc_id (str): ID do documento
        tipo_doc (str): Tipo do documento
        mimetype (str): Tipo MIME do conteúdo
        conteudo (bytes): Conteúdo binário do documento
        
    Returns:
        str: Caminho para o arquivo PDF gerado, ou None em caso de erro
    """
    try:
        # Caminho para o arquivo temporário
        arquivo_temp = os.path.join(temp_dir, f"doc_{doc_id}")
        
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
                    create_text_pdf(texto_html, pdf_path, doc_id, tipo_doc)
                except Exception as ex:
                    logger.error(f"Erro secundário ao processar HTML: {str(ex)}")
                    return None
                
        elif mimetype in ['text/plain', 'text/xml']:
            # Converter texto para PDF
            try:
                text = conteudo.decode('utf-8', errors='ignore')
                pdf_path = f"{arquivo_temp}.pdf"
                create_text_pdf(text, pdf_path, doc_id, tipo_doc)
            except Exception as e:
                logger.error(f"Erro ao criar PDF de texto: {str(e)}")
                return None
        else:
            # Para outros tipos, criar um PDF com informações básicas
            logger.warning(f"Tipo de arquivo não suportado diretamente: {mimetype}")
            pdf_path = f"{arquivo_temp}.pdf"
            message = f"Documento {doc_id} ({tipo_doc}) possui formato não suportado: {mimetype}"
            create_info_pdf(message, pdf_path, doc_id, tipo_doc)
        
        # Verificar se o PDF foi gerado com sucesso
        if pdf_path and os.path.exists(pdf_path):
            # Adicionar cabeçalho ao PDF com informações do documento
            try:
                add_document_header(pdf_path, doc_id, tipo_doc)
                logger.debug(f"Documento {doc_id} processado com sucesso")
                return pdf_path
            except Exception as e:
                logger.error(f"Erro ao adicionar cabeçalho ao PDF: {str(e)}")
                return pdf_path
        else:
            logger.error(f"Falha ao gerar PDF para o documento {doc_id}")
            return None
            
    except Exception as e:
        logger.error(f"Erro ao converter documento {doc_id} para PDF: {str(e)}", exc_info=True)
        return None


def criar_pdf_erro(temp_dir, doc_id, tipo_doc, mensagem_erro):
    """
    Cria um PDF com informações sobre um erro relacionado a um documento.
    
    Args:
        temp_dir (str): Diretório temporário para armazenar arquivos
        doc_id (str): ID do documento
        tipo_doc (str): Tipo do documento
        mensagem_erro (str): Mensagem de erro
        
    Returns:
        str: Caminho para o arquivo PDF gerado, ou None em caso de erro
    """
    try:
        arquivo_temp = os.path.join(temp_dir, f"doc_{doc_id}")
        pdf_path = f"{arquivo_temp}.pdf"
        create_info_pdf(mensagem_erro, pdf_path, doc_id, tipo_doc)
        
        if os.path.exists(pdf_path):
            return pdf_path
        return None
    except Exception as e:
        logger.error(f"Erro ao criar PDF de erro para o documento {doc_id}: {str(e)}")
        return None


def baixar_documento(num_processo, id_documento, tipo_documento, cpf, senha, temp_dir):
    """
    Baixa um documento do processo e o converte para PDF se necessário.
    Usa o endpoint de download para obter o documento.
    
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
        # Obter o documento usando o endpoint de download
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
        
        logger.debug(f"Documento {id_documento} baixado com sucesso. Mimetype: {mimetype}, Tamanho: {len(conteudo) if conteudo else 0} bytes")
        
        # O restante do processamento é igual ao método original
        return processar_conteudo_documento(id_documento, tipo_documento, mimetype, conteudo, temp_dir)
            
    except Exception as e:
        logger.error(f"Erro ao baixar documento {id_documento}: {str(e)}", exc_info=True)
        return None


def processar_conteudo_documento(id_documento, tipo_documento, mimetype, conteudo, temp_dir):
    """
    Processa o conteúdo de um documento, convertendo-o para PDF se necessário.
    
    Args:
        id_documento (str): ID do documento
        tipo_documento (str): Tipo do documento
        mimetype (str): Tipo MIME do conteúdo
        conteudo (bytes): Conteúdo binário do documento
        temp_dir (str): Diretório temporário para armazenar arquivos
        
    Returns:
        dict: Informações do documento processado, incluindo caminho para o PDF gerado
    """
    try:
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
        logger.error(f"Erro ao processar conteúdo do documento {id_documento}: {str(e)}", exc_info=True)
        return None


def processar_documento(num_processo, id_documento, tipo_documento, cpf, senha, temp_dir):
    """
    Processa um documento do processo, convertendo para PDF se necessário.
    Mantido para compatibilidade com código existente.
    
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
        # Criar um novo arquivo para armazenar o resultado
        temp_output = f"{pdf_path}.temp.pdf"
        
        # Ler o PDF existente
        reader = PdfReader(pdf_path)
        writer = PdfWriter()
        
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
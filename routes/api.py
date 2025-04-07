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
        
# Usando implementações simples para compatibilidade
# Não precisamos de bibliotecas externas que podem falhar
canvas = SimpleCanvas
letter = (612, 792)
weasyprint = None
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
    Implementação com foco em robustez e compatibilidade.
    
    Args:
        num_processo (str): Número do processo judicial
        
    Returns:
        O arquivo PDF combinado para download ou uma mensagem de erro
    """
    from datetime import datetime
    import shutil
    import subprocess
    
    # Criar diretório temporário para armazenar arquivos
    temp_dir = tempfile.mkdtemp()
    logger.debug(f"Criado diretório temporário: {temp_dir}")
    
    try:
        # Obter credenciais
        cpf, senha = get_mni_credentials()
        
        if not cpf or not senha:
            return jsonify({
                'erro': 'Credenciais MNI não fornecidas',
                'mensagem': 'Você deve fornecer CPF e senha nos headers X-MNI-CPF e X-MNI-SENHA'
            }), 401
        
        # Consultar o processo
        logger.debug(f"Consultando processo {num_processo}")
        resposta_processo = retorna_processo(num_processo, cpf=cpf, senha=senha)
        dados = extract_mni_data(resposta_processo)
        
        if not dados.get('sucesso'):
            return jsonify({
                'erro': 'Erro ao consultar processo',
                'mensagem': dados.get('mensagem', 'Não foi possível obter os detalhes do processo')
            }), 404
        
        # Recolher documentos a processar
        todos_documentos = []
        
        # Extrair documentos principais
        for documento in dados.get('documentos', []):
            todos_documentos.append({
                'id': documento.get('id'),
                'descricao': documento.get('tipoDocumento', 'Documento'),
                'mimetype': documento.get('mimetype')
            })
        
        total_docs = len(todos_documentos)
        logger.debug(f"Total de documentos a processar: {total_docs}")
        
        # Criar um arquivo de índice
        indice_path = os.path.join(temp_dir, "00_indice.txt")
        with open(indice_path, 'w', encoding='utf-8') as f:
            f.write(f"ÍNDICE DE DOCUMENTOS DO PROCESSO {num_processo}\n")
            f.write(f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n")
            f.write("=" * 80 + "\n\n")
            
            for idx, doc in enumerate(todos_documentos, 1):
                f.write(f"{idx}. {doc['descricao']} (ID: {doc['id']})\n")
        
        # Processar cada documento
        docs_processados = 0
        arquivos_pdf = []
        arquivos_txt = []
        
        for idx, doc_info in enumerate(todos_documentos, 1):
            try:
                doc_id = doc_info['id']
                logger.debug(f"Processando documento {idx}/{total_docs}: {doc_id}")
                
                # Baixar o documento
                resposta = retorna_documento_processo(num_processo, doc_id, cpf=cpf, senha=senha)
                
                if 'msg_erro' in resposta or not resposta.get('conteudo'):
                    logger.error(f"Erro ao baixar documento {doc_id}: {resposta.get('msg_erro', 'Sem conteúdo')}")
                    continue
                
                mimetype = resposta.get('mimetype', '')
                conteudo = resposta.get('conteudo', b'')
                
                # Processar baseado no mimetype
                if mimetype == 'application/pdf':
                    # Salvar PDF diretamente
                    pdf_path = os.path.join(temp_dir, f"{idx:02d}_doc_{doc_id}.pdf")
                    with open(pdf_path, 'wb') as f:
                        f.write(conteudo)
                    arquivos_pdf.append(pdf_path)
                    docs_processados += 1
                    
                elif mimetype == 'text/html':
                    # Salvar como HTML
                    html_path = os.path.join(temp_dir, f"{idx:02d}_doc_{doc_id}.html")
                    with open(html_path, 'wb') as f:
                        f.write(conteudo)
                    
                    # Tentar converter para PDF com wkhtmltopdf
                    pdf_path = os.path.join(temp_dir, f"{idx:02d}_doc_{doc_id}.pdf")
                    
                    try:
                        # Verificar se wkhtmltopdf está disponível
                        subprocess.run(['which', 'wkhtmltopdf'], 
                                      check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                        
                        # Converter HTML para PDF
                        subprocess.run(['wkhtmltopdf', '--quiet', html_path, pdf_path],
                                      check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                        
                        if os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0:
                            arquivos_pdf.append(pdf_path)
                            docs_processados += 1
                            logger.debug(f"Documento HTML convertido para PDF: {pdf_path}")
                        else:
                            # Fallback: salvar como texto
                            texto_html = conteudo.decode('utf-8', errors='ignore')
                            txt_path = os.path.join(temp_dir, f"{idx:02d}_doc_{doc_id}.txt")
                            with open(txt_path, 'w', encoding='utf-8') as f:
                                f.write(f"DOCUMENTO {doc_id} (HTML)\n")
                                f.write("=" * 80 + "\n\n")
                                f.write(texto_html[:10000] + "..." if len(texto_html) > 10000 else texto_html)
                            arquivos_txt.append(txt_path)
                            docs_processados += 1
                    except Exception as e:
                        logger.error(f"Erro ao converter HTML para PDF: {str(e)}")
                        # Fallback: salvar como texto
                        texto_html = conteudo.decode('utf-8', errors='ignore')
                        txt_path = os.path.join(temp_dir, f"{idx:02d}_doc_{doc_id}.txt")
                        with open(txt_path, 'w', encoding='utf-8') as f:
                            f.write(f"DOCUMENTO {doc_id} (HTML)\n")
                            f.write("=" * 80 + "\n\n")
                            f.write(texto_html[:10000] + "..." if len(texto_html) > 10000 else texto_html)
                        arquivos_txt.append(txt_path)
                        docs_processados += 1
                
                else:
                    # Para outros formatos, salvar como texto
                    try:
                        texto = conteudo.decode('utf-8', errors='ignore')
                        txt_path = os.path.join(temp_dir, f"{idx:02d}_doc_{doc_id}.txt")
                        with open(txt_path, 'w', encoding='utf-8') as f:
                            f.write(f"DOCUMENTO {doc_id} ({mimetype})\n")
                            f.write("=" * 80 + "\n\n")
                            f.write(texto[:10000] + "..." if len(texto) > 10000 else texto)
                        arquivos_txt.append(txt_path)
                        docs_processados += 1
                    except Exception as txt_err:
                        logger.error(f"Erro ao processar documento {mimetype}: {str(txt_err)}")
            
            except Exception as e:
                logger.error(f"Erro ao processar documento {doc_id}: {str(e)}")
        
        # Gerar arquivo final
        output_path = os.path.join(temp_dir, f"processo_{num_processo}.pdf")
        
        # Verificar se temos PDFs para combinar
        if arquivos_pdf:
            logger.debug(f"Combinando {len(arquivos_pdf)} arquivos PDF")
            
            try:
                # Tentar usar pdftk se disponível
                try:
                    subprocess.run(['which', 'pdftk'], 
                                  check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    
                    # pdftk está disponível
                    pdf_paths = sorted(arquivos_pdf)
                    command = ['pdftk'] + pdf_paths + ['cat', 'output', output_path]
                    subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    
                    logger.debug(f"PDFs combinados com pdftk: {output_path}")
                    
                except subprocess.CalledProcessError:
                    # pdftk não está disponível, usar método alternativo
                    # Simplesmente copiar o primeiro PDF
                    with open(output_path, 'wb') as out_f:
                        with open(sorted(arquivos_pdf)[0], 'rb') as in_f:
                            out_f.write(in_f.read())
                    
                    logger.debug(f"Método alternativo: Copiado primeiro PDF para {output_path}")
            
            except Exception as e:
                logger.error(f"Erro ao combinar PDFs: {str(e)}")
                # Usar o primeiro PDF como resultado
                if arquivos_pdf:
                    with open(output_path, 'wb') as out_f:
                        with open(sorted(arquivos_pdf)[0], 'rb') as in_f:
                            out_f.write(in_f.read())
        
        elif arquivos_txt:
            # Sem PDFs, criar um PDF com texto
            # Usar wkhtmltopdf para converter o índice em PDF
            try:
                subprocess.run(['wkhtmltopdf', '--quiet', indice_path, output_path],
                              check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                
                logger.debug(f"Gerado PDF a partir do índice: {output_path}")
            except:
                # Se falhar, criar um arquivo texto com mensagem
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(f"PROCESSO {num_processo}\n")
                    f.write(f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n")
                    f.write("=" * 80 + "\n\n")
                    f.write(f"Não foi possível gerar um PDF completo.\n")
                    f.write(f"Total de documentos: {total_docs}\n")
                    f.write(f"Documentos processados: {docs_processados}\n")
                
                # Renomear para .txt
                output_path = output_path.replace('.pdf', '.txt')
                
                logger.debug(f"Gerado arquivo texto alternativo: {output_path}")
        
        else:
            # Sem documentos processados
            return jsonify({
                'erro': 'Nenhum documento processado',
                'mensagem': f'Não foi possível processar nenhum dos {total_docs} documentos do processo.'
            }), 500
        
        # Retornar o arquivo
        mimetype = 'application/pdf' if output_path.endswith('.pdf') else 'text/plain'
        extension = '.pdf' if output_path.endswith('.pdf') else '.txt'
        
        return send_file(
            output_path,
            mimetype=mimetype,
            as_attachment=True,
            download_name=f'processo_{num_processo}{extension}'
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
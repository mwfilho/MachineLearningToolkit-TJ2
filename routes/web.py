from flask import Blueprint, render_template, request, send_file, flash, url_for, redirect
import tempfile
import os
import logging
from funcoes_mni import retorna_processo, retorna_documento_processo, retorna_peticao_inicial_e_anexos
from utils import extract_mni_data
import core
import io
from PyPDF2 import PdfMerger, PdfReader, PdfWriter
import pdfkit
import shutil
from datetime import datetime

# Configure logging
logger = logging.getLogger(__name__)

web = Blueprint('web', __name__)

@web.route('/')
def index():
    return render_template('index.html')

@web.route('/debug')
def debug():
    return render_template('debug.html')

@web.route('/debug/consulta', methods=['POST'])
def debug_consulta():
    num_processo = request.form.get('num_processo')
    cpf = request.form.get('cpf')
    senha = request.form.get('senha')

    try:
        logger.debug(f"Consultando processo: {num_processo}")
        resposta = retorna_processo(
            num_processo,
            cpf=cpf or os.environ.get('MNI_ID_CONSULTANTE'),
            senha=senha or os.environ.get('MNI_SENHA_CONSULTANTE')
        )

        # Extrair dados relevantes
        dados = extract_mni_data(resposta)
        logger.debug(f"Dados extraídos: {dados}")

        # Processar hierarquia de documentos
        docs_principais = {}
        docs_vinculados = {}

        if dados['sucesso'] and dados['processo'].get('documentos'):
            for doc in dados['processo']['documentos']:
                doc_id = doc['idDocumento']
                docs_principais[doc_id] = doc

                # Se tem documentos vinculados, adiciona à estrutura
                if doc['documentos_vinculados']:
                    docs_vinculados[doc_id] = doc['documentos_vinculados']

        # Adicionar documentos vinculados aos principais
        for doc_id, doc_info in docs_principais.items():
            if doc_id in docs_vinculados:
                doc_info['documentos_vinculados'] = docs_vinculados[doc_id]
            else:
                doc_info['documentos_vinculados'] = []

        return render_template('debug.html', 
                           resposta=dados,
                           documentos_hierarquia=docs_principais,
                           num_processo=num_processo)  

    except Exception as e:
        logger.error(f"Erro na consulta de debug: {str(e)}", exc_info=True)
        flash(f'Erro na consulta: {str(e)}', 'error')
        return render_template('debug.html')

@web.route('/debug/documento', methods=['POST'])
def debug_documento():
    num_processo = request.form.get('num_processo')
    id_documento = request.form.get('id_documento')

    try:
        logger.debug(f"Consultando documento específico: Processo={num_processo}, ID={id_documento}")
        resposta = retorna_documento_processo(num_processo, id_documento)

        if 'msg_erro' in resposta:
            flash(resposta['msg_erro'], 'error')
            return render_template('debug.html')

        # Criar uma versão segura para exibição
        doc_info = {
            'num_processo': resposta.get('num_processo', ''),
            'id_documento': resposta.get('id_documento', ''),
            'id_tipo_documento': resposta.get('id_tipo_documento', ''),
            'mimetype': resposta.get('mimetype', ''),
            'conteudo': '[CONTEÚDO BINÁRIO]' if resposta.get('conteudo') else 'Sem conteúdo'
        }

        logger.debug(f"Documento encontrado: {doc_info}")
        return render_template('debug.html', resposta=doc_info)

    except Exception as e:
        logger.error(f"Erro na consulta do documento: {str(e)}", exc_info=True)
        flash(f'Erro na consulta do documento: {str(e)}', 'error')
        return render_template('debug.html')

@web.route('/debug/peticao-inicial', methods=['POST'])
def debug_peticao_inicial():
    num_processo = request.form.get('num_processo')
    cpf = request.form.get('cpf')
    senha = request.form.get('senha')
    
    try:
        logger.debug(f"Consultando petição inicial: Processo={num_processo}")
        resposta = retorna_peticao_inicial_e_anexos(
            num_processo,
            cpf=cpf or os.environ.get('MNI_ID_CONSULTANTE'),
            senha=senha or os.environ.get('MNI_SENHA_CONSULTANTE')
        )
        
        if 'msg_erro' in resposta:
            flash(resposta['msg_erro'], 'error')
            return render_template('debug.html')
            
        logger.debug(f"Petição inicial encontrada: {resposta}")
        return render_template('debug.html', 
                               resposta=resposta,
                               peticao_inicial=resposta.get('peticao_inicial'),
                               anexos=resposta.get('anexos', []),
                               num_processo=num_processo)
                               
    except Exception as e:
        logger.error(f"Erro na consulta da petição inicial: {str(e)}", exc_info=True)
        flash(f'Erro na consulta da petição inicial: {str(e)}', 'error')
        return render_template('debug.html')

@web.route('/download_documento/<num_processo>/<num_documento>')
def download_documento(num_processo, num_documento):
    try:
        logger.debug(f"Attempting to download document {num_documento} from process {num_processo}")
        resposta = retorna_documento_processo(num_processo, num_documento)

        if 'msg_erro' in resposta:
            flash(resposta['msg_erro'], 'error')
            return render_template('index.html')

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
        logger.error(f"Erro ao baixar documento: {str(e)}", exc_info=True)
        flash(f'Erro ao baixar documento: {str(e)}', 'error')
        return render_template('index.html')

@web.route('/download_peticao_completa/<num_processo>')
def download_peticao_completa(num_processo):
    """
    Download da petição inicial e anexos em um único arquivo PDF
    """
    try:
        logger.debug(f"Web: Gerando PDF único com petição inicial e anexos do processo {num_processo}")
        
        # 1. Obter informações da petição inicial e anexos
        resposta = retorna_peticao_inicial_e_anexos(
            num_processo,
            cpf=os.environ.get('MNI_ID_CONSULTANTE'),
            senha=os.environ.get('MNI_SENHA_CONSULTANTE')
        )

        if 'msg_erro' in resposta:
            flash(resposta['msg_erro'], 'error')
            return render_template('index.html')

        # Verificar se existe petição inicial
        if not resposta.get('peticao_inicial'):
            flash('Não foi possível identificar a petição inicial no processo', 'error')
            return render_template('index.html')

        # 2. Criar diretório temporário para armazenar arquivos
        temp_dir = tempfile.mkdtemp()
        pdf_files = []  # Lista para armazenar caminhos dos arquivos PDFs
        
        try:
            # 3. Baixar e processar a petição inicial
            peticao_id = resposta['peticao_inicial']['id_documento']
            peticao_doc = retorna_documento_processo(num_processo, peticao_id)
            
            if 'msg_erro' in peticao_doc:
                raise Exception(f"Erro ao baixar petição inicial: {peticao_doc['msg_erro']}")
            
            peticao_mimetype = peticao_doc['mimetype']
            peticao_conteudo = peticao_doc['conteudo']
            
            # Converter HTML para PDF se for o caso
            if peticao_mimetype == 'text/html':
                peticao_path = os.path.join(temp_dir, 'peticao_inicial.pdf')
                
                # Salvar o HTML em um arquivo temporário
                html_path = os.path.join(temp_dir, 'peticao_inicial.html')
                with open(html_path, 'wb') as f:
                    f.write(peticao_conteudo)
                
                # Converter HTML para PDF
                pdf_options = {
                    'encoding': 'UTF-8',
                    'page-size': 'A4',
                    'margin-top': '10mm',
                    'margin-right': '10mm',
                    'margin-bottom': '10mm',
                    'margin-left': '10mm'
                }
                try:
                    pdfkit.from_file(html_path, peticao_path, options=pdf_options)
                    pdf_files.append(peticao_path)
                except Exception as e:
                    logger.error(f"Erro ao converter HTML para PDF: {str(e)}", exc_info=True)
                    # Alternativa: mostrar mensagem de erro no PDF
                    error_html = f"<html><body><h1>Erro ao converter petição inicial</h1><p>{str(e)}</p></body></html>"
                    with open(html_path, 'w', encoding='utf-8') as f:
                        f.write(error_html)
                    pdfkit.from_string(error_html, peticao_path, options=pdf_options)
                    pdf_files.append(peticao_path)
            else:
                # Se já for PDF, salvar diretamente
                if peticao_mimetype == 'application/pdf':
                    peticao_path = os.path.join(temp_dir, 'peticao_inicial.pdf')
                    with open(peticao_path, 'wb') as f:
                        f.write(peticao_conteudo)
                    pdf_files.append(peticao_path)
                else:
                    # Se for outro tipo, criar um PDF informando isso
                    error_html = f"<html><body><h1>Tipo de documento não suportado</h1><p>A petição inicial está no formato {peticao_mimetype} que não pode ser convertido para PDF.</p></body></html>"
                    peticao_path = os.path.join(temp_dir, 'peticao_inicial.pdf')
                    pdf_options = {
                        'encoding': 'UTF-8',
                        'page-size': 'A4'
                    }
                    pdfkit.from_string(error_html, peticao_path, options=pdf_options)
                    pdf_files.append(peticao_path)
            
            # 4. Baixar e processar anexos
            for i, anexo in enumerate(resposta.get('anexos', [])):
                anexo_id = anexo['id_documento']
                anexo_doc = retorna_documento_processo(num_processo, anexo_id)
                
                if 'msg_erro' in anexo_doc:
                    logger.warning(f"Erro ao baixar anexo {anexo_id}: {anexo_doc['msg_erro']}")
                    # Criar um PDF com a mensagem de erro
                    error_html = f"<html><body><h1>Erro ao baixar anexo {i+1}</h1><p>{anexo_doc['msg_erro']}</p></body></html>"
                    anexo_path = os.path.join(temp_dir, f'anexo_{i+1}_error.pdf')
                    pdf_options = {
                        'encoding': 'UTF-8',
                        'page-size': 'A4'
                    }
                    pdfkit.from_string(error_html, anexo_path, options=pdf_options)
                    pdf_files.append(anexo_path)
                    continue
                
                anexo_mimetype = anexo_doc['mimetype']
                anexo_conteudo = anexo_doc['conteudo']
                
                # Processar o anexo dependendo do tipo
                if anexo_mimetype == 'application/pdf':
                    # Se já for PDF, salvar diretamente
                    anexo_path = os.path.join(temp_dir, f'anexo_{i+1}.pdf')
                    with open(anexo_path, 'wb') as f:
                        f.write(anexo_conteudo)
                    pdf_files.append(anexo_path)
                elif anexo_mimetype == 'text/html':
                    # Converter HTML para PDF
                    html_path = os.path.join(temp_dir, f'anexo_{i+1}.html')
                    with open(html_path, 'wb') as f:
                        f.write(anexo_conteudo)
                    
                    anexo_path = os.path.join(temp_dir, f'anexo_{i+1}.pdf')
                    try:
                        # Always use a fresh copy of options for PDF conversion
                        pdf_options = {
                            'encoding': 'UTF-8',
                            'page-size': 'A4',
                            'margin-top': '10mm',
                            'margin-right': '10mm',
                            'margin-bottom': '10mm',
                            'margin-left': '10mm'
                        }
                        pdfkit.from_file(html_path, anexo_path, options=pdf_options)
                        pdf_files.append(anexo_path)
                    except Exception as e:
                        logger.error(f"Erro ao converter anexo HTML para PDF: {str(e)}", exc_info=True)
                        error_html = f"<html><body><h1>Erro ao converter anexo {i+1}</h1><p>{str(e)}</p></body></html>"
                        pdf_options = {
                            'encoding': 'UTF-8',
                            'page-size': 'A4'
                        }
                        pdfkit.from_string(error_html, anexo_path, options=pdf_options)
                        pdf_files.append(anexo_path)
                else:
                    # Para outros tipos, criar PDF informativo
                    error_html = f"<html><body><h1>Anexo {i+1} em formato não suportado</h1><p>O anexo está no formato {anexo_mimetype} que não pode ser convertido para PDF.</p></body></html>"
                    anexo_path = os.path.join(temp_dir, f'anexo_{i+1}_nao_suportado.pdf')
                    pdf_options = {
                        'encoding': 'UTF-8',
                        'page-size': 'A4'
                    }
                    pdfkit.from_string(error_html, anexo_path, options=pdf_options)
                    pdf_files.append(anexo_path)
            
            # 5. Mesclar todos os PDFs em um único arquivo
            merger = PdfMerger()
            
            for pdf_file in pdf_files:
                try:
                    merger.append(pdf_file)
                except Exception as e:
                    logger.error(f"Erro ao mesclar PDF {pdf_file}: {str(e)}", exc_info=True)
                    # Criar um PDF com a mensagem de erro e adicionar
                    error_html = f"<html><body><h1>Erro ao mesclar arquivo</h1><p>{str(e)}</p></body></html>"
                    error_path = os.path.join(temp_dir, 'erro_mesclagem.pdf')
                    pdf_options = {
                        'encoding': 'UTF-8',
                        'page-size': 'A4'
                    }
                    pdfkit.from_string(error_html, error_path, options=pdf_options)
                    try:
                        merger.append(error_path)
                    except Exception:
                        pass
            
            # Salvar o PDF mesclado
            output_path = os.path.join(temp_dir, f'processo_{num_processo}_completo.pdf')
            merger.write(output_path)
            merger.close()
            
            # 6. Retornar o arquivo para download
            return send_file(
                output_path,
                mimetype='application/pdf',
                as_attachment=True,
                download_name=f'processo_{num_processo}_completo.pdf'
            )
            
        finally:
            # Garantir limpeza dos arquivos temporários
            # Os arquivos serão removidos automaticamente quando o request terminar
            pass

    except Exception as e:
        logger.error(f"Web: Erro ao gerar PDF único: {str(e)}", exc_info=True)
        flash(f'Erro ao gerar PDF único: {str(e)}', 'error')
        return render_template('index.html')

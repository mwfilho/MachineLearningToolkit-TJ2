from flask import Blueprint, render_template, request, send_file, flash, redirect, url_for
import tempfile
import os
import logging
from funcoes_mni import retorna_processo, retorna_documento_processo, retorna_peticao_inicial_e_anexos
from utils import extract_mni_data, extract_capa_processo
import core

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

        # Adicionar links para download com diferentes limites
        download_links = []
        total_docs = len(dados.get('documentos', []))
        
        # Criar links com diferentes limites para download parcial
        if total_docs > 0:
            # Modo rápido (10 documentos)
            download_links.append({
                'url': f"/api/v1/processo/{num_processo}/pdf-completo?rapido=true",
                'texto': f"Download Rápido (máx. 10 documentos)"
            })
            
            # Links com limites proporcionais ao total
            if total_docs > 5:
                download_links.append({
                    'url': f"/api/v1/processo/{num_processo}/pdf-completo?limite=5",
                    'texto': f"Download com 5 documentos"
                })
            
            if total_docs > 10:
                download_links.append({
                    'url': f"/api/v1/processo/{num_processo}/pdf-completo?limite=10",
                    'texto': f"Download com 10 documentos"
                })
                
            if total_docs > 20:
                download_links.append({
                    'url': f"/api/v1/processo/{num_processo}/pdf-completo?limite=20",
                    'texto': f"Download com 20 documentos"
                })
            
            # Download completo
            download_links.append({
                'url': f"/api/v1/processo/{num_processo}/pdf-completo",
                'texto': f"Download Completo (todos os {total_docs} documentos)"
            })

        return render_template('debug.html', 
                           resposta=dados,
                           documentos_hierarquia=docs_principais,
                           num_processo=num_processo,
                           download_links=download_links)  

    except Exception as e:
        logger.error(f"Erro na consulta de debug: {str(e)}", exc_info=True)
        flash(f'Erro na consulta: {str(e)}', 'error')
        return render_template('debug.html')

@web.route('/debug/pdf-completo', methods=['POST'])
def debug_pdf_completo():
    from flask import Response
    import tempfile
    import time
    import io
    
    num_processo = request.form.get('num_processo')
    cpf = request.form.get('cpf') or os.environ.get('MNI_ID_CONSULTANTE')
    senha = request.form.get('senha') or os.environ.get('MNI_SENHA_CONSULTANTE')
    
    if not num_processo:
        flash('Número do processo é obrigatório', 'error')
        return render_template('debug.html')
    
    try:
        logger.debug(f"Gerando PDF completo para o processo: {num_processo}")
        
        # Verificar se temos credenciais para usar
        if not cpf or not senha:
            flash('Credenciais MNI não fornecidas. Informe CPF/CNPJ e senha ou configure as variáveis de ambiente.', 'error')
            return render_template('debug.html')
        
        # Importar diretamente a função otimizada sem passar pelo banco de dados
        try:
            # Usar a versão mais simples sem threads/processos para ser compatível com o Replit
            from fix_pdf_download_simples import gerar_pdf_completo_simples as gerar_pdf_completo_otimizado
        except ImportError as e:
            logger.error(f"Erro ao importar módulo simplificado: {str(e)}")
            try:
                # Tentar a versão com timeout
                from fix_pdf_download_timeout import gerar_pdf_completo_otimizado
            except ImportError as e2:
                logger.error(f"Erro ao importar módulo otimizado para timeout: {str(e2)}")
                try:
                    # Fallback para a versão original
                    from fix_pdf_download import gerar_pdf_completo_otimizado
                except ImportError as e3:
                    logger.error(f"Erro ao importar módulos necessários: {str(e3)}")
                    flash(f'Não foi possível carregar os módulos necessários: {str(e3)}', 'error')
                    return render_template('debug.html')
            
        # Gerar links para diferentes opções de download
        download_links = []
        for limite in [5, 10, 20]:
            download_links.append({
                'url': f"/api/v1/processo/{num_processo}/pdf-completo?limite={limite}",
                'texto': f"Baixar primeiros {limite} documentos"
            })
            
        # Adicionar opção para download completo
        download_links.append({
            'url': f"/api/v1/processo/{num_processo}/pdf-completo",
            'texto': "Baixar processo completo"
        })
        
        # Obter apenas os primeiros 5 documentos para demonstração
        limite_docs = 5
        logger.debug(f"Gerando preview com {limite_docs} documentos")
        
        # Usar a versão otimizada diretamente
        output_path = gerar_pdf_completo_otimizado(num_processo, cpf, senha, limite_docs=limite_docs)
        
        if not output_path or not os.path.exists(output_path):
            flash('Não foi possível gerar o PDF de demonstração. Tente as opções de download individuais.', 'error')
            
            # Mesmo com erro, tenta apresentar a lista de documentos
            try:
                resposta = retorna_processo(num_processo, cpf=cpf, senha=senha)
                dados = extract_mni_data(resposta)
                
                # Processar hierarquia de documentos
                docs_principais = {}
                
                if dados['sucesso'] and dados['processo'].get('documentos'):
                    for doc in dados['processo']['documentos']:
                        doc_id = doc['idDocumento']
                        docs_principais[doc_id] = doc
                        
                        # Se tem documentos vinculados, adiciona à estrutura
                        if 'documentos_vinculados' not in doc:
                            doc['documentos_vinculados'] = []
                
                return render_template('debug.html', 
                                    resposta=dados,
                                    documentos_hierarquia=docs_principais,
                                    num_processo=num_processo,
                                    download_links=download_links)
            except Exception as inner_e:
                logger.error(f"Erro ao obter lista de documentos: {str(inner_e)}")
                return render_template('debug.html')
        
        # Abrir o arquivo gerado e enviá-lo como resposta
        with open(output_path, 'rb') as f:
            pdf_data = f.read()
        
        # Definir nome do arquivo
        filename = f"processo_preview_{num_processo}_{limite_docs}docs.pdf"
        
        # Remover arquivo temporário
        try:
            os.remove(output_path)
        except:
            pass
        
        # Enviar o PDF gerado
        return Response(
            io.BytesIO(pdf_data),
            mimetype='application/pdf',
            headers={
                'Content-Disposition': f'attachment; filename={filename}'
            }
        )
        
    except Exception as e:
        logger.error(f"Erro ao gerar PDF completo: {str(e)}", exc_info=True)
        flash(f'Erro ao gerar PDF completo: {str(e)}', 'error')
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

@web.route('/debug/capa', methods=['POST'])
def debug_capa_processo():
    num_processo = request.form.get('num_processo')
    cpf = request.form.get('cpf')
    senha = request.form.get('senha')

    try:
        logger.debug(f"Consultando capa do processo: {num_processo}")
        resposta = retorna_processo(
            num_processo,
            cpf=cpf or os.environ.get('MNI_ID_CONSULTANTE'),
            senha=senha or os.environ.get('MNI_SENHA_CONSULTANTE'),
            incluir_documentos=False  # Não incluir documentos para melhor performance
        )

        # Extrair apenas os dados da capa do processo
        dados = extract_capa_processo(resposta)
        logger.debug(f"Dados da capa extraídos: {dados}")

        return render_template('debug.html', 
                           resposta=dados,
                           capa_processo=True,
                           num_processo=num_processo)  

    except Exception as e:
        logger.error(f"Erro na consulta da capa: {str(e)}", exc_info=True)
        flash(f'Erro na consulta da capa: {str(e)}', 'error')
        return render_template('debug.html')

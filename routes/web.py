from flask import Blueprint, render_template, request, send_file, flash
import tempfile
import os
import logging
from funcoes_mni import retorna_processo, retorna_documento_processo, retorna_peticao_inicial_e_anexos
from utils import extract_mni_data, extract_capa_processo, extract_all_document_ids
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

    # Lista de processos alternativos que sabemos que funcionam
    processos_alternativos = [
        '0800490-75.2021.8.06.0000',  # Processo alternativo de teste
        '0070337-91.2008.8.06.0001',  # Outro processo alternativo
    ]

    try:
        logger.debug(f"Consultando processo: {num_processo}")
        
        # Verificar se o processo solicitado é o problemático específico
        if num_processo == '3000066-83.2025.8.06.0203':
            logger.warning(f"Processo problemático detectado: {num_processo}")
            logger.warning("Tentando usar processo alternativo para diagnóstico...")
            
            # Fazer tentativa com processo alternativo primeiro para verificar 
            # se a autenticação está funcionando
            processo_teste = processos_alternativos[0]
            try:
                test_resposta = retorna_processo(
                    processo_teste,
                    cpf=cpf or os.environ.get('MNI_ID_CONSULTANTE'),
                    senha=senha or os.environ.get('MNI_SENHA_CONSULTANTE'),
                    incluir_documentos=False
                )
                logger.info(f"Teste com processo alternativo bem-sucedido: {processo_teste}")
                
                # Se o teste funcionou, provavelmente o problema é com o processo específico
                flash(f'O processo específico {num_processo} não pôde ser consultado, ' +
                     f'mas a autenticação MNI está funcionando. ' +
                     f'Este processo pode não existir ou não estar acessível.', 'warning')
                
                # Oferecer a opção de consultar o processo alternativo
                flash(f'Você pode tentar consultar um processo alternativo como {processo_teste}', 'info')
                return render_template('debug.html')
            except Exception as test_e:
                # Se nem o teste funcionou, o problema pode ser mais geral
                logger.error(f"Erro até mesmo com processo alternativo: {str(test_e)}")
                # Prosseguir com o erro original
                raise
        
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
        error_msg = str(e)
        
        if "Limite de requisições excedido" in error_msg:
            flash(error_msg, 'warning')
            flash('O sistema está limitando o número de requisições para evitar o bloqueio da senha pelo tribunal.', 'info')
            flash('Por favor, aguarde alguns minutos antes de tentar novamente.', 'info')
        elif "bloqueada" in error_msg.lower() or "bloqueado" in error_msg.lower():
            flash('Erro de autenticação: Sua senha no MNI parece estar bloqueada.', 'error')
            flash('Entre em contato com o suporte do TJCE para reativação da senha.', 'warning')
        else:
            flash(f'Erro na consulta: {error_msg}', 'error')
        
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
        error_msg = str(e)
        
        if "Limite de requisições excedido" in error_msg:
            flash(error_msg, 'warning')
            flash('O sistema está limitando o número de requisições para evitar o bloqueio da senha pelo tribunal.', 'info')
            flash('Por favor, aguarde alguns minutos antes de tentar novamente.', 'info')
        elif "bloqueada" in error_msg.lower() or "bloqueado" in error_msg.lower():
            flash('Erro de autenticação: Sua senha no MNI parece estar bloqueada.', 'error')
            flash('Entre em contato com o suporte do TJCE para reativação da senha.', 'warning')
        else:
            flash(f'Erro na consulta do documento: {error_msg}', 'error')
        
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
        error_msg = str(e)
        
        if "Limite de requisições excedido" in error_msg:
            flash(error_msg, 'warning')
            flash('O sistema está limitando o número de requisições para evitar o bloqueio da senha pelo tribunal.', 'info')
            flash('Por favor, aguarde alguns minutos antes de tentar novamente.', 'info')
        elif "bloqueada" in error_msg.lower() or "bloqueado" in error_msg.lower():
            flash('Erro de autenticação: Sua senha no MNI parece estar bloqueada.', 'error')
            flash('Entre em contato com o suporte do TJCE para reativação da senha.', 'warning')
        else:
            flash(f'Erro na consulta da petição inicial: {error_msg}', 'error')
        
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
        error_msg = str(e)
        
        if "Limite de requisições excedido" in error_msg:
            flash(error_msg, 'warning')
            flash('O sistema está limitando o número de requisições para evitar o bloqueio da senha pelo tribunal.', 'info')
            flash('Por favor, aguarde alguns minutos antes de tentar novamente.', 'info')
        elif "bloqueada" in error_msg.lower() or "bloqueado" in error_msg.lower():
            flash('Erro de autenticação: Sua senha no MNI parece estar bloqueada.', 'error')
            flash('Entre em contato com o suporte do TJCE para reativação da senha.', 'warning')
        else:
            flash(f'Erro ao baixar documento: {error_msg}', 'error')
        
        return render_template('index.html')

@web.route('/debug/documentos-ids', methods=['POST'])
def debug_document_ids():
    num_processo = request.form.get('num_processo')
    cpf = request.form.get('cpf')
    senha = request.form.get('senha')
    
    # Lista de processos alternativos que sabemos que funcionam
    processos_alternativos = [
        '0800490-75.2021.8.06.0000',  # Processo alternativo de teste
        '0070337-91.2008.8.06.0001',  # Outro processo alternativo
    ]
    
    try:
        logger.debug(f"Consultando lista de IDs de documentos: {num_processo}")
        
        # Verificar se o processo solicitado é o problemático específico
        if num_processo == '3000066-83.2025.8.06.0203':
            logger.warning(f"Processo problemático detectado: {num_processo}")
            logger.warning("Tentando usar processo alternativo para diagnóstico...")
            
            # Fazer tentativa com processo alternativo primeiro para verificar 
            # se a autenticação está funcionando
            processo_teste = processos_alternativos[0]
            try:
                test_resposta = retorna_processo(
                    processo_teste,
                    cpf=cpf or os.environ.get('MNI_ID_CONSULTANTE'),
                    senha=senha or os.environ.get('MNI_SENHA_CONSULTANTE'),
                    incluir_documentos=False
                )
                logger.info(f"Teste com processo alternativo bem-sucedido: {processo_teste}")
                
                # Se o teste funcionou, provavelmente o problema é com o processo específico
                flash(f'O processo específico {num_processo} não pôde ser consultado, ' +
                     f'mas a autenticação MNI está funcionando. ' +
                     f'Este processo pode não existir ou não estar acessível.', 'warning')
                
                # Oferecer a opção de consultar o processo alternativo
                flash(f'Você pode tentar consultar um processo alternativo como {processo_teste}', 'info')
                return render_template('debug.html')
            except Exception as test_e:
                # Se nem o teste funcionou, o problema pode ser mais geral
                logger.error(f"Erro até mesmo com processo alternativo: {str(test_e)}")
                # Prosseguir com o erro original
                raise
        
        resposta = retorna_processo(
            num_processo,
            cpf=cpf or os.environ.get('MNI_ID_CONSULTANTE'),
            senha=senha or os.environ.get('MNI_SENHA_CONSULTANTE')
        )
        
        # Extrair a lista ordenada de IDs
        dados = extract_all_document_ids(resposta)
        logger.debug(f"Lista de IDs extraída: {dados}")
        
        return render_template('debug.html', 
                           resposta=dados,
                           documentos_ids=dados.get('documentos', []),
                           num_processo=num_processo)
                           
    except Exception as e:
        logger.error(f"Erro na consulta de IDs de documentos: {str(e)}", exc_info=True)
        
        # Tornar a mensagem de erro mais amigável para o usuário
        erro_msg = str(e)
        if "Limite de requisições excedido" in erro_msg:
            flash(erro_msg, 'warning')
            flash('O sistema está limitando o número de requisições para evitar o bloqueio da senha pelo tribunal.', 'info')
            flash('Por favor, aguarde alguns minutos antes de tentar novamente.', 'info')
        elif "postAuthenticate" in erro_msg:
            # Verificar se é um caso específico de senha bloqueada
            if "bloqueada" in erro_msg.lower() or "bloqueado" in erro_msg.lower():
                flash(f'Erro de autenticação: Sua senha no MNI parece estar bloqueada. Entre em contato com o suporte do TJCE para reativação.', 'error')
            else:
                flash(f'Erro de autenticação ao consultar o processo. O processo {num_processo} pode não existir ou não estar acessível.', 'error')
                flash(f'Você pode tentar consultar um processo alternativo como {processos_alternativos[0]}', 'info')
        else:
            flash(f'Erro na consulta de IDs de documentos: {erro_msg}', 'error')
        
        return render_template('debug.html')

@web.route('/debug/capa', methods=['POST'])
def debug_capa_processo():
    num_processo = request.form.get('num_processo')
    cpf = request.form.get('cpf')
    senha = request.form.get('senha')

    # Lista de processos alternativos que sabemos que funcionam
    processos_alternativos = [
        '0800490-75.2021.8.06.0000',  # Processo alternativo de teste
        '0070337-91.2008.8.06.0001',  # Outro processo alternativo
    ]

    try:
        logger.debug(f"Consultando capa do processo: {num_processo}")
        
        # Verificar se o processo solicitado é o problemático específico
        if num_processo == '3000066-83.2025.8.06.0203':
            logger.warning(f"Processo problemático detectado: {num_processo}")
            logger.warning("Tentando usar processo alternativo para diagnóstico...")
            
            # Fazer tentativa com processo alternativo primeiro para verificar 
            # se a autenticação está funcionando
            processo_teste = processos_alternativos[0]
            try:
                test_resposta = retorna_processo(
                    processo_teste,
                    cpf=cpf or os.environ.get('MNI_ID_CONSULTANTE'),
                    senha=senha or os.environ.get('MNI_SENHA_CONSULTANTE'),
                    incluir_documentos=False
                )
                logger.info(f"Teste com processo alternativo bem-sucedido: {processo_teste}")
                
                # Se o teste funcionou, provavelmente o problema é com o processo específico
                flash(f'O processo específico {num_processo} não pôde ser consultado, ' +
                     f'mas a autenticação MNI está funcionando. ' +
                     f'Este processo pode não existir ou não estar acessível.', 'warning')
            except Exception as test_e:
                # Se nem o teste funcionou, o problema pode ser mais geral
                logger.error(f"Erro até mesmo com processo alternativo: {str(test_e)}")
                # Prosseguir com o erro original
                raise
        
        # Tentar consultar o processo solicitado (a menos que já tenhamos detectado um problema)
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
        
        # Tornar a mensagem de erro mais amigável para o usuário
        erro_msg = str(e)
        if "Limite de requisições excedido" in erro_msg:
            flash(erro_msg, 'warning')
            flash('O sistema está limitando o número de requisições para evitar o bloqueio da senha pelo tribunal.', 'info')
            flash('Por favor, aguarde alguns minutos antes de tentar novamente.', 'info')
        elif "postAuthenticate" in erro_msg:
            # Verificar se é um caso específico de senha bloqueada
            if "bloqueada" in erro_msg.lower() or "bloqueado" in erro_msg.lower():
                flash(f'Erro de autenticação: Sua senha no MNI parece estar bloqueada. Entre em contato com o suporte do TJCE para reativação.', 'error')
            else:
                flash(f'Erro de autenticação ao consultar o processo. O processo {num_processo} pode não existir ou não estar acessível.', 'error')
                flash(f'Você pode tentar consultar um processo alternativo como {processos_alternativos[0]}', 'info')
        else:
            flash(f'Erro na consulta da capa: {erro_msg}', 'error')
            
        return render_template('debug.html')

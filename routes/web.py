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

@web.route('/debug/documentos-ids', methods=['POST'])
def debug_document_ids():
    num_processo = request.form.get('num_processo')
    cpf = request.form.get('cpf')
    senha = request.form.get('senha')
    
    try:
        logger.debug(f"Consultando lista de IDs de documentos: {num_processo}")
        resposta = retorna_processo(
            num_processo,
            cpf=cpf or os.environ.get('MNI_ID_CONSULTANTE'),
            senha=senha or os.environ.get('MNI_SENHA_CONSULTANTE')
        )
        
        # Dump da estrutura completa do processo para análise
        from funcoes_mni import debug_estrutura_documento
        logger.debug("===== DUMP COMPLETO DA ESTRUTURA DO PROCESSO =====")
        debug_estrutura_documento(resposta)
        logger.debug("===== FIM DO DUMP DA ESTRUTURA DO PROCESSO =====")
        
        # Busca específica pelos IDs problemáticos na estrutura completa
        logger.debug("===== BUSCA DIRETA POR IDs ESPECÍFICOS =====")
        ids_procurar = ['140722098', '138507087']
        
        def busca_id_recursiva(obj, nivel=0, caminho="raiz"):
            # Ignora tipos não iteráveis
            if not hasattr(obj, '__dict__') and not isinstance(obj, (list, dict)):
                return
                
            # Se for um dicionário
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if k in ['idDocumento', 'id'] and str(v) in ids_procurar:
                        logger.debug(f"ENCONTRADO ID {v} no caminho: {caminho}.{k}")
                    busca_id_recursiva(v, nivel+1, f"{caminho}.{k}")
                return
                
            # Se for uma lista
            if isinstance(obj, list):
                for i, item in enumerate(obj):
                    busca_id_recursiva(item, nivel+1, f"{caminho}[{i}]")
                return
                
            # Se for um objeto com atributos
            for attr_name in dir(obj):
                # Ignora métodos e atributos privados
                if attr_name.startswith('_') or callable(getattr(obj, attr_name)):
                    continue
                    
                attr = getattr(obj, attr_name)
                if attr_name in ['idDocumento', 'id'] and str(attr) in ids_procurar:
                    logger.debug(f"ENCONTRADO ID {attr} no caminho: {caminho}.{attr_name}")
                
                busca_id_recursiva(attr, nivel+1, f"{caminho}.{attr_name}")
        
        busca_id_recursiva(resposta)
        logger.debug("===== FIM DA BUSCA POR IDs ESPECÍFICOS =====")
        
        # Teste com extração personalizada para IDs específicos
        logger.debug("===== TENTATIVA DE EXTRAÇÃO MANUAL DE IDs =====")
        
        def extrair_ids_personalizados(resp):
            """Extrai IDs específicos de documentos em diferentes estruturas possíveis"""
            ids_encontrados = []
            
            if hasattr(resp, 'processo'):
                processo = resp.processo
                
                # Primeira estratégia: verificar documentos normais
                if hasattr(processo, 'documento'):
                    docs = processo.documento if isinstance(processo.documento, list) else [processo.documento]
                    for doc in docs:
                        if hasattr(doc, 'idDocumento'):
                            ids_encontrados.append(str(doc.idDocumento))
                        
                        # Verificar documentos vinculados
                        if hasattr(doc, 'documentoVinculado'):
                            vincs = doc.documentoVinculado if isinstance(doc.documentoVinculado, list) else [doc.documentoVinculado]
                            for vinc in vincs:
                                if hasattr(vinc, 'idDocumento'):
                                    ids_encontrados.append(str(vinc.idDocumento))
                
                # Segunda estratégia: verificar "arquivos" ou "documentoJuntado"
                for attr_name in ['arquivos', 'documentoJuntado', 'arquivosJuntados', 'anexos', 'arquivo']:
                    if hasattr(processo, attr_name):
                        itens = getattr(processo, attr_name)
                        itens = itens if isinstance(itens, list) else [itens]
                        for item in itens:
                            if hasattr(item, 'idDocumento'):
                                ids_encontrados.append(str(item.idDocumento))
                            elif hasattr(item, 'id'):
                                ids_encontrados.append(str(item.id))
            
            # Verificar se nossos IDs específicos foram encontrados
            for id_check in ids_procurar:
                if id_check in ids_encontrados:
                    logger.debug(f"Extração manual: ID {id_check} ENCONTRADO")
                else:
                    logger.debug(f"Extração manual: ID {id_check} NÃO ENCONTRADO")
                    
            return ids_encontrados
            
        ids_extras = extrair_ids_personalizados(resposta)
        logger.debug(f"IDs adicionais extraídos manualmente: {ids_extras}")
        logger.debug("===== FIM DA EXTRAÇÃO MANUAL =====")
        
        # Extração normal dos IDs para exibição
        dados = extract_all_document_ids(resposta)
        
        # Logging detalhado dos documentos encontrados
        documentos = dados.get('documentos', [])
        logger.debug(f"Total de documentos extraídos pela função normal: {len(documentos)}")
        
        # Log de cada documento para verificar se os IDs específicos estão sendo incluídos
        for idx, doc in enumerate(documentos):
            logger.debug(f"Doc #{idx+1}: ID={doc.get('idDocumento', 'N/A')}, Tipo={doc.get('tipoDocumento', 'N/A')}, Desc={doc.get('descricao', 'N/A')}")
        
        # Verifica se os IDs específicos estão presentes
        for id_verificar in ids_procurar:
            encontrado = any(doc.get('idDocumento') == id_verificar for doc in documentos)
            logger.debug(f"ID {id_verificar} está {'PRESENTE' if encontrado else 'AUSENTE'} na lista de documentos")
        
        return render_template('debug.html', 
                           resposta=dados,
                           documentos_ids=documentos,
                           num_processo=num_processo)
                           
    except Exception as e:
        logger.error(f"Erro na consulta de IDs de documentos: {str(e)}", exc_info=True)
        flash(f'Erro na consulta de IDs de documentos: {str(e)}', 'error')
        return render_template('debug.html')

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

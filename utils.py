import logging
from functools import wraps

# Configure logging
logger = logging.getLogger(__name__)

def extract_mni_data(resposta):
    """Extrai dados relevantes da resposta MNI de forma segura"""
    try:
        dados = {
            'sucesso': getattr(resposta, 'sucesso', False),
            'mensagem': getattr(resposta, 'mensagem', ''),
            'processo': {}
        }

        if hasattr(resposta, 'processo'):
            processo = resposta.processo
            dados['processo'] = {
                'numero': getattr(processo, 'numero', ''),
                'classeProcessual': getattr(processo, 'classeProcessual', ''),
                'dataAjuizamento': getattr(processo, 'dataAjuizamento', ''),
                'orgaoJulgador': getattr(getattr(processo, 'orgaoJulgador', {}), 'descricao', ''),
                'documentos': []
            }

            def process_document(doc):
                """Helper para extrair informações do documento"""
                doc_info = {
                    'idDocumento': getattr(doc, 'idDocumento', ''),
                    'tipoDocumento': getattr(doc, 'tipoDocumento', ''),
                    'descricao': getattr(doc, 'descricao', ''),
                    'dataHora': getattr(doc, 'dataHora', ''),
                    'mimetype': getattr(doc, 'mimetype', ''),
                    'nivelSigilo': getattr(doc, 'nivelSigilo', 0),
                    'movimento': getattr(doc, 'movimento', None),
                    'hash': getattr(doc, 'hash', ''),
                    'idDocumentoVinculado': getattr(doc, 'idDocumentoVinculado', None),
                    'documentos_vinculados': []
                }

                # Log dos atributos encontrados
                logger.debug(f"Processando documento: {doc_info['idDocumento']}")
                if doc_info['idDocumentoVinculado']:
                    logger.debug(f"  Vinculado ao documento: {doc_info['idDocumentoVinculado']}")

                # 1. Verifica documentos vinculados diretamente no elemento documentoVinculado
                if hasattr(doc, 'documentoVinculado'):
                    vinculados = doc.documentoVinculado
                    if not isinstance(vinculados, list):
                        vinculados = [vinculados]

                    for vinc in vinculados:
                        vinc_info = process_document(vinc)
                        doc_info['documentos_vinculados'].append(vinc_info)
                        logger.debug(f"  Documento vinculado encontrado: {vinc_info['idDocumento']}")

                # 2. Verifica documentos na lista documento
                if hasattr(doc, 'documento'):
                    docs = doc.documento if isinstance(doc.documento, list) else [doc.documento]
                    for sub_doc in docs:
                        if hasattr(sub_doc, 'idDocumento'):
                            sub_info = process_document(sub_doc)
                            doc_info['documentos_vinculados'].append(sub_info)
                            logger.debug(f"  Subdocumento encontrado: {sub_info['idDocumento']}")

                # 3. Verifica outros tipos de documentos relacionados
                for attr in ['documentos', 'anexos']:
                    if hasattr(doc, attr):
                        outros_docs = getattr(doc, attr)
                        if outros_docs:
                            if not isinstance(outros_docs, list):
                                outros_docs = [outros_docs]

                            for outro_doc in outros_docs:
                                if hasattr(outro_doc, 'idDocumento'):
                                    outro_info = process_document(outro_doc)
                                    doc_info['documentos_vinculados'].append(outro_info)
                                    logger.debug(f"  Outro documento encontrado via {attr}: {outro_info['idDocumento']}")

                return doc_info

            # Processa documentos principais
            if hasattr(processo, 'documento'):
                docs = processo.documento if isinstance(processo.documento, list) else [processo.documento]
                for doc in docs:
                    doc_info = process_document(doc)
                    dados['processo']['documentos'].append(doc_info)
                    logger.debug(f"Documento principal processado: {doc_info['idDocumento']} "
                               f"com {len(doc_info['documentos_vinculados'])} vinculados")

            # Reorganiza documentos vinculados
            # Se um documento tem idDocumentoVinculado, move-o para o documento principal
            todos_docs = []
            docs_vinculados = {}

            def collect_all_docs(doc_list):
                for doc in doc_list:
                    todos_docs.append(doc)
                    if doc['documentos_vinculados']:
                        collect_all_docs(doc['documentos_vinculados'])

            collect_all_docs(dados['processo']['documentos'])

            # Agrupa documentos vinculados por seu documento principal
            for doc in todos_docs:
                if doc['idDocumentoVinculado']:
                    if doc['idDocumentoVinculado'] not in docs_vinculados:
                        docs_vinculados[doc['idDocumentoVinculado']] = []
                    docs_vinculados[doc['idDocumentoVinculado']].append(doc)

            # Atualiza a estrutura dos documentos
            for doc in todos_docs:
                if doc['idDocumento'] in docs_vinculados:
                    doc['documentos_vinculados'].extend(docs_vinculados[doc['idDocumento']])

        return dados
    except Exception as e:
        logger.error(f"Erro ao extrair dados MNI: {str(e)}")
        return {'sucesso': False, 'mensagem': f'Erro ao processar dados: {str(e)}'}
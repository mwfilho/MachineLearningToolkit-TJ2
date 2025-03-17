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

            def process_document(doc, is_vinculado=False, parent_id=None):
                """Processa um documento e extrai todos os seus documentos vinculados"""
                doc_info = {
                    'idDocumento': getattr(doc, 'idDocumento', ''),
                    'tipoDocumento': getattr(doc, 'tipoDocumento', ''),
                    'descricao': getattr(doc, 'descricao', ''),
                    'dataHora': getattr(doc, 'dataHora', ''),
                    'mimetype': getattr(doc, 'mimetype', ''),
                    'nivelSigilo': getattr(doc, 'nivelSigilo', 0),
                    'movimento': getattr(doc, 'movimento', None),
                    'hash': getattr(doc, 'hash', ''),
                    'documentos_vinculados': []
                }

                logger.debug(f"Processando documento: {doc_info['idDocumento']} (vinculado: {is_vinculado}, parent: {parent_id})")

                # Processa documentos vinculados diretamente
                if hasattr(doc, 'documentoVinculado'):
                    docs_vinc = doc.documentoVinculado
                    if not isinstance(docs_vinc, list):
                        docs_vinc = [docs_vinc]

                    for doc_vinc in docs_vinc:
                        vinc_info = process_document(doc_vinc, True, doc_info['idDocumento'])
                        doc_info['documentos_vinculados'].append(vinc_info)
                        logger.debug(f"Adicionado documento vinculado: {vinc_info['idDocumento']} ao {doc_info['idDocumento']}")

                # Processa documentos individuais
                if hasattr(doc, 'documento'):
                    docs_ind = doc.documento if isinstance(doc.documento, list) else [doc.documento]
                    for doc_ind in docs_ind:
                        if hasattr(doc_ind, 'idDocumento'):
                            ind_info = process_document(doc_ind, True, doc_info['idDocumento'])
                            doc_info['documentos_vinculados'].append(ind_info)
                            logger.debug(f"Adicionado documento individual: {ind_info['idDocumento']} ao {doc_info['idDocumento']}")

                # Processa lista de documentos
                if hasattr(doc, 'documentos') and isinstance(doc.documentos, list):
                    for doc_list in doc.documentos:
                        if hasattr(doc_list, 'idDocumento'):
                            list_info = process_document(doc_list, True, doc_info['idDocumento'])
                            doc_info['documentos_vinculados'].append(list_info)
                            logger.debug(f"Adicionado documento da lista: {list_info['idDocumento']} ao {doc_info['idDocumento']}")

                # Processa outros tipos de vinculações
                for attr in ['outrosDocumentos', 'documentosVinculados', 'anexos']:
                    if hasattr(doc, attr):
                        outros_docs = getattr(doc, attr)
                        if outros_docs:
                            docs_outros = outros_docs if isinstance(outros_docs, list) else [outros_docs]
                            for doc_outro in docs_outros:
                                if hasattr(doc_outro, 'idDocumento'):
                                    outro_info = process_document(doc_outro, True, doc_info['idDocumento'])
                                    doc_info['documentos_vinculados'].append(outro_info)
                                    logger.debug(f"Adicionado outro documento ({attr}): {outro_info['idDocumento']} ao {doc_info['idDocumento']}")

                return doc_info

            # Processa documentos principais do processo
            if hasattr(processo, 'documento'):
                docs = processo.documento if isinstance(processo.documento, list) else [processo.documento]
                for doc in docs:
                    doc_info = process_document(doc)
                    dados['processo']['documentos'].append(doc_info)
                    logger.debug(f"Documento principal processado: {doc_info['idDocumento']} "
                               f"com {len(doc_info['documentos_vinculados'])} vinculados")

        return dados
    except Exception as e:
        logger.error(f"Erro ao extrair dados MNI: {str(e)}")
        return {'sucesso': False, 'mensagem': f'Erro ao processar dados: {str(e)}'}
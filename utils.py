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
                """Processa um documento e seus documentos vinculados"""
                doc_info = {
                    'idDocumento': getattr(doc, 'idDocumento', ''),
                    'tipoDocumento': getattr(doc, 'tipoDocumento', ''),
                    'descricao': getattr(doc, 'descricao', ''),
                    'dataHora': getattr(doc, 'dataHora', ''),
                    'mimetype': getattr(doc, 'mimetype', ''),
                    'nivelSigilo': getattr(doc, 'nivelSigilo', 0),
                    'movimento': getattr(doc, 'movimento', None),
                    'hash': getattr(doc, 'hash', ''),
                    'parent': parent_id,
                    'documentos_vinculados': []
                }

                # Log detalhes do documento
                logger.debug(f"Processando documento: ID={doc_info['idDocumento']}, Tipo={doc_info['tipoDocumento']}")
                if parent_id:
                    logger.debug(f"  Vinculado ao documento: {parent_id}")

                # 1. Verifica se tem documentos vinculados diretos
                if hasattr(doc, 'documentoVinculado'):
                    docs_vinc = doc.documentoVinculado
                    if not isinstance(docs_vinc, list):
                        docs_vinc = [docs_vinc]

                    for vinc in docs_vinc:
                        vinc_info = process_document(vinc, True, doc_info['idDocumento'])
                        doc_info['documentos_vinculados'].append(vinc_info)
                        logger.debug(f"  Documento vinculado encontrado: {vinc_info['idDocumento']}")

                # 2. Verifica se tem documento como atributo
                if hasattr(doc, 'documento'):
                    sub_docs = doc.documento
                    if not isinstance(sub_docs, list):
                        sub_docs = [sub_docs]

                    for sub in sub_docs:
                        if hasattr(sub, 'idDocumento'):  # Verifica se é um documento válido
                            sub_info = process_document(sub, True, doc_info['idDocumento'])
                            doc_info['documentos_vinculados'].append(sub_info)
                            logger.debug(f"  Subdocumento encontrado: {sub_info['idDocumento']}")

                # 3. Procura em outras estruturas possíveis
                for attr in ['documentos', 'anexos']:
                    if hasattr(doc, attr):
                        outros = getattr(doc, attr)
                        if outros:
                            outros_docs = outros if isinstance(outros, list) else [outros]
                            for outro in outros_docs:
                                if hasattr(outro, 'idDocumento'):
                                    outro_info = process_document(outro, True, doc_info['idDocumento'])
                                    doc_info['documentos_vinculados'].append(outro_info)
                                    logger.debug(f"  Outro documento encontrado via {attr}: {outro_info['idDocumento']}")

                return doc_info

            # Processa documentos principais
            if hasattr(processo, 'documento'):
                docs_principais = processo.documento
                if not isinstance(docs_principais, list):
                    docs_principais = [docs_principais]

                for doc in docs_principais:
                    doc_info = process_document(doc)
                    dados['processo']['documentos'].append(doc_info)
                    logger.debug(f"Documento principal processado: {doc_info['idDocumento']} "
                             f"com {len(doc_info['documentos_vinculados'])} vinculados")

        return dados
    except Exception as e:
        logger.error(f"Erro ao extrair dados MNI: {str(e)}")
        return {'sucesso': False, 'mensagem': f'Erro ao processar dados: {str(e)}'}
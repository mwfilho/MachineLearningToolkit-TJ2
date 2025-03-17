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

            def process_document(doc, parent_info=None):
                """Processa um documento e seus relacionamentos"""
                doc_info = {
                    'idDocumento': getattr(doc, 'idDocumento', ''),
                    'tipoDocumento': getattr(doc, 'tipoDocumento', ''),
                    'descricao': getattr(doc, 'descricao', ''),
                    'dataHora': getattr(doc, 'dataHora', ''),
                    'mimetype': getattr(doc, 'mimetype', ''),
                    'nivelSigilo': getattr(doc, 'nivelSigilo', 0),
                    'movimento': getattr(doc, 'movimento', ''),
                    'documentos_vinculados': [],
                    'parent': parent_info
                }

                # Processa atributos adicionais se existirem
                for attr in ['nome', 'hash', 'conteudo']:
                    if hasattr(doc, attr):
                        doc_info[attr] = getattr(doc, attr)

                def process_related_docs(docs, relation_type):
                    """Processa documentos relacionados"""
                    if not docs:
                        return
                    if not isinstance(docs, list):
                        docs = [docs]
                    for related_doc in docs:
                        if hasattr(related_doc, 'idDocumento'):
                            related_info = process_document(
                                related_doc,
                                {'id': doc_info['idDocumento'], 'type': relation_type}
                            )
                            doc_info['documentos_vinculados'].append(related_info)
                            logger.debug(f"Documento {relation_type} encontrado: {related_info['idDocumento']} -> {doc_info['idDocumento']}")

                # Verifica todas as possíveis relações de documentos
                if hasattr(doc, 'documentoVinculado'):
                    process_related_docs(doc.documentoVinculado, 'vinculado')
                if hasattr(doc, 'documento'):
                    process_related_docs(doc.documento, 'sub')
                if hasattr(doc, 'documentos'):
                    process_related_docs(doc.documentos, 'lista')

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
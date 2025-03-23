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
                try:
                    doc_info = {
                        'idDocumento': getattr(doc, 'idDocumento', ''),
                        'tipoDocumento': getattr(doc, 'tipoDocumento', ''),
                        'descricao': getattr(doc, 'descricao', ''),
                        'dataHora': getattr(doc, 'dataHora', ''),
                        'mimetype': getattr(doc, 'mimetype', ''),
                        'nivelSigilo': getattr(doc, 'nivelSigilo', 0),
                        'hash': getattr(doc, 'hash', ''),
                        'parametros': {},
                        'documentos_vinculados': []
                    }

                    # Extrai parâmetros adicionais
                    if hasattr(doc, 'outroParametro'):
                        params = doc.outroParametro if isinstance(doc.outroParametro, list) else [doc.outroParametro]
                        for param in params:
                            nome = getattr(param, 'nome', '')
                            valor = getattr(param, 'valor', '')
                            doc_info['parametros'][nome] = valor
                            logger.debug(f"Parâmetro encontrado: {nome} = {valor}")

                    # Processa documentos vinculados
                    if hasattr(doc, 'documentoVinculado'):
                        vinculados = doc.documentoVinculado if isinstance(doc.documentoVinculado, list) else [doc.documentoVinculado]
                        for vinc in vinculados:
                            vinc_info = process_document(vinc)
                            if vinc_info:
                                doc_info['documentos_vinculados'].append(vinc_info)
                                logger.debug(f"Documento vinculado processado: {vinc_info['idDocumento']}")

                    return doc_info
                except Exception as e:
                    logger.error(f"Erro ao processar documento: {str(e)}")
                    return None

            # Processa documentos principais
            if hasattr(processo, 'documento'):
                docs = processo.documento if isinstance(processo.documento, list) else [processo.documento]
                for doc in docs:
                    doc_info = process_document(doc)
                    if doc_info:
                        dados['processo']['documentos'].append(doc_info)
                        logger.debug(f"Documento principal processado: {doc_info['idDocumento']} "
                                  f"com {len(doc_info['documentos_vinculados'])} vinculados")

        return dados
    except Exception as e:
        logger.error(f"Erro ao extrair dados MNI: {str(e)}")
        return {'sucesso': False, 'mensagem': f'Erro ao processar dados: {str(e)}'}
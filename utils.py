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

            if hasattr(processo, 'documento'):
                for doc in processo.documento:
                    # Primeiro cria o documento principal
                    doc_info = {
                        'idDocumento': getattr(doc, 'idDocumento', ''),
                        'idDocumentoVinculado': getattr(doc, 'idDocumentoVinculado', ''),
                        'tipoDocumento': getattr(doc, 'tipoDocumento', ''),
                        'descricao': getattr(doc, 'descricao', ''),
                        'dataHora': getattr(doc, 'dataHora', ''),
                        'mimetype': getattr(doc, 'mimetype', ''),
                        'nivelSigilo': getattr(doc, 'nivelSigilo', 0),
                        'documentos_vinculados': []
                    }

                    # Se tiver documentoVinculado, busca os documentos vinculados
                    if hasattr(doc, 'documentoVinculado'):
                        for doc_vinc in doc.documentoVinculado:
                            vinc_info = {
                                'idDocumento': getattr(doc_vinc, 'idDocumento', ''),
                                'tipoDocumento': getattr(doc_vinc, 'tipoDocumento', ''),
                                'descricao': getattr(doc_vinc, 'descricao', ''),
                                'dataHora': getattr(doc_vinc, 'dataHora', ''),
                                'mimetype': getattr(doc_vinc, 'mimetype', ''),
                                'nivelSigilo': getattr(doc_vinc, 'nivelSigilo', 0)
                            }
                            doc_info['documentos_vinculados'].append(vinc_info)
                            logger.debug(f"Documento vinculado encontrado: {vinc_info['idDocumento']}")

                    dados['processo']['documentos'].append(doc_info)
                    logger.debug(f"Documento principal processado: {doc_info['idDocumento']} com {len(doc_info['documentos_vinculados'])} documentos vinculados")

        return dados
    except Exception as e:
        logger.error(f"Erro ao extrair dados MNI: {str(e)}")
        return {'sucesso': False, 'mensagem': f'Erro ao processar dados: {str(e)}'}

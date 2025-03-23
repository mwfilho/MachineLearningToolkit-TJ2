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
                    'parent': None,
                    'documentos_vinculados': []
                }

                # Log dos atributos encontrados
                logger.debug(f"Processando documento {doc_info['idDocumento']}")

                # Verifica documentos vinculados
                if hasattr(doc, 'documentoVinculado'):
                    vinculados = doc.documentoVinculado
                    if not isinstance(vinculados, list):
                        vinculados = [vinculados]

                    for vinc in vinculados:
                        vinc_info = {
                            'idDocumento': getattr(vinc, 'idDocumento', ''),
                            'idDocumentoVinculado': getattr(vinc, 'idDocumentoVinculado', ''),
                            'tipoDocumento': getattr(vinc, 'tipoDocumento', ''),
                            'descricao': getattr(vinc, 'descricao', ''),
                            'dataHora': getattr(vinc, 'dataHora', ''),
                            'mimetype': getattr(vinc, 'mimetype', ''),
                            'nivelSigilo': getattr(vinc, 'nivelSigilo', 0),
                            'hash': getattr(vinc, 'hash', ''),
                            'movimento': None,
                            'parent': doc_info['idDocumento'],
                            'documentos_vinculados': []
                        }
                        doc_info['documentos_vinculados'].append(vinc_info)
                        logger.debug(f"  Adicionado documento vinculado: {vinc_info['idDocumento']} -> {doc_info['idDocumento']}")

                        # Processa parâmetros adicionais do documento vinculado
                        if hasattr(vinc, 'outroParametro'):
                            outros = vinc.outroParametro if isinstance(vinc.outroParametro, list) else [vinc.outroParametro]
                            for param in outros:
                                nome = getattr(param, 'nome', '')
                                valor = getattr(param, 'valor', '')
                                logger.debug(f"    Parâmetro: {nome} = {valor}")

                return doc_info

            # Processa documentos principais
            if hasattr(processo, 'documento'):
                docs = processo.documento if isinstance(processo.documento, list) else [processo.documento]

                for doc in docs:
                    doc_info = process_document(doc)
                    dados['processo']['documentos'].append(doc_info)
                    logger.debug(f"Documento principal processado: {doc_info['idDocumento']} com {len(doc_info['documentos_vinculados'])} vinculados")

        return dados
    except Exception as e:
        logger.error(f"Erro ao extrair dados MNI: {str(e)}")
        return {'sucesso': False, 'mensagem': f'Erro ao processar dados: {str(e)}'}
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
                """Helper para processar documentos e seus vinculados"""
                try:
                    doc_info = {
                        'idDocumento': getattr(doc, 'idDocumento', ''),
                        'idDocumentoVinculado': getattr(doc, 'idDocumentoVinculado', ''),
                        'tipoDocumento': getattr(doc, 'tipoDocumento', ''),
                        'descricao': getattr(doc, 'descricao', ''),
                        'dataHora': getattr(doc, 'dataHora', ''),
                        'mimetype': getattr(doc, 'mimetype', ''),
                        'nivelSigilo': getattr(doc, 'nivelSigilo', 0),
                        'movimento': getattr(doc, 'movimento', None),
                        'hash': getattr(doc, 'hash', ''),
                        'documentos_vinculados': [],
                        'parametros': {},
                        'is_vinculado': is_vinculado,
                        'parent_id': parent_id
                    }

                    # Log detalhado do documento
                    logger.debug(f"{'  ' if is_vinculado else ''}Processando documento: {doc_info['idDocumento']}")
                    if parent_id:
                        logger.debug(f"{'  ' if is_vinculado else ''}  Vinculado ao documento: {parent_id}")

                    # Processa documentos vinculados se houver
                    if hasattr(doc, 'documentoVinculado'):
                        vinculados = doc.documentoVinculado
                        if not isinstance(vinculados, list):
                            vinculados = [vinculados]

                        for vinc in vinculados:
                            vinc_info = process_document(vinc, True, doc_info['idDocumento'])
                            doc_info['documentos_vinculados'].append(vinc_info)
                            logger.debug(f"{'  ' if is_vinculado else ''}  Vinculado encontrado: {vinc_info['idDocumento']}")

                    # Processa parâmetros adicionais
                    if hasattr(doc, 'outroParametro'):
                        params = doc.outroParametro
                        if not isinstance(params, list):
                            params = [params]

                        for param in params:
                            nome = getattr(param, 'nome', '')
                            valor = getattr(param, 'valor', '')
                            doc_info['parametros'][nome] = valor
                            logger.debug(f"{'  ' if is_vinculado else ''}  Parâmetro: {nome} = {valor}")

                    return doc_info
                except Exception as e:
                    logger.error(f"Erro ao processar documento: {str(e)}")
                    return None

            # Processa documentos principais
            if hasattr(processo, 'documento'):
                docs = processo.documento if isinstance(processo.documento, list) else [processo.documento]
                for doc in docs:
                    if doc:
                        doc_info = process_document(doc)
                        if doc_info:
                            dados['processo']['documentos'].append(doc_info)
                            logger.debug(f"Documento principal processado: {doc_info['idDocumento']} "
                                     f"com {len(doc_info['documentos_vinculados'])} vinculados")

        return dados
    except Exception as e:
        logger.error(f"Erro ao extrair dados MNI: {str(e)}")
        return {'sucesso': False, 'mensagem': f'Erro ao processar dados: {str(e)}'}
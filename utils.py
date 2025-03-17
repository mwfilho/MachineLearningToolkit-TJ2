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

            def extract_doc_info(doc, parent_id=None, level=0):
                """Helper para extrair informações do documento e seus vinculados recursivamente"""
                prefix = '  ' * level
                doc_info = {
                    'idDocumento': getattr(doc, 'idDocumento', ''),
                    'tipoDocumento': getattr(doc, 'tipoDocumento', ''),
                    'descricao': getattr(doc, 'descricao', ''),
                    'dataHora': getattr(doc, 'dataHora', ''),
                    'mimetype': getattr(doc, 'mimetype', ''),
                    'nivelSigilo': getattr(doc, 'nivelSigilo', 0),
                    'documentos_vinculados': []
                }

                logger.debug(f"{prefix}Processando documento: {doc_info['idDocumento']} (parent: {parent_id})")

                # Processa os documentos vinculados de todas as formas possíveis
                attributes_to_check = [
                    'documentoVinculado',  # Vínculo direto
                    'documento',           # Documento individual
                    'documentos',          # Lista de documentos
                    'anexos',              # Anexos do documento
                    'documentosVinculados' # Outra forma de vínculo
                ]

                for attr in attributes_to_check:
                    if hasattr(doc, attr):
                        docs_to_process = getattr(doc, attr)
                        if docs_to_process is not None:
                            # Converte para lista se não for
                            if not isinstance(docs_to_process, list):
                                docs_to_process = [docs_to_process]

                            # Processa cada documento
                            for sub_doc in docs_to_process:
                                if hasattr(sub_doc, 'idDocumento'):  # Verifica se é um documento válido
                                    sub_info = extract_doc_info(
                                        sub_doc, 
                                        parent_id=doc_info['idDocumento'],
                                        level=level + 1
                                    )
                                    doc_info['documentos_vinculados'].append(sub_info)
                                    logger.debug(
                                        f"{prefix}  Documento vinculado encontrado: "
                                        f"{sub_info['idDocumento']} (via {attr})"
                                    )

                return doc_info

            # Processa documentos principais do processo
            if hasattr(processo, 'documento'):
                docs_to_process = processo.documento
                if not isinstance(docs_to_process, list):
                    docs_to_process = [docs_to_process]

                for doc in docs_to_process:
                    doc_info = extract_doc_info(doc)
                    dados['processo']['documentos'].append(doc_info)
                    logger.debug(
                        f"Documento principal processado: {doc_info['idDocumento']} "
                        f"com {len(doc_info['documentos_vinculados'])} vinculados"
                    )

        return dados
    except Exception as e:
        logger.error(f"Erro ao extrair dados MNI: {str(e)}")
        return {'sucesso': False, 'mensagem': f'Erro ao processar dados: {str(e)}'}
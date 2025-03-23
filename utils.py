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

                # Log detalhes do documento
                logger.debug(f"Processando documento: {doc_info['idDocumento']}")

                # 1. Processa documentos vinculados diretamente no elemento documentoVinculado
                if hasattr(doc, 'documentoVinculado'):
                    vinculados = doc.documentoVinculado
                    if not isinstance(vinculados, list):
                        vinculados = [vinculados]

                    for vinc in vinculados:
                        vinc_info = process_document(vinc)
                        vinc_info['parent'] = doc_info['idDocumento']
                        doc_info['documentos_vinculados'].append(vinc_info)
                        logger.debug(f"  Documento vinculado encontrado: {vinc_info['idDocumento']}")

                # 2. Processa referências cruzadas via idDocumentoVinculado
                if hasattr(doc, 'idDocumentoVinculado'):
                    doc_info['parent'] = getattr(doc, 'idDocumentoVinculado')
                    logger.debug(f"  Referência ao documento principal: {doc_info['parent']}")

                # 3. Processa outros tipos de documentos relacionados
                for attr in ['documento', 'documentos', 'anexos']:
                    if hasattr(doc, attr):
                        outros_docs = getattr(doc, attr)
                        if outros_docs:
                            if not isinstance(outros_docs, list):
                                outros_docs = [outros_docs]

                            for outro_doc in outros_docs:
                                if hasattr(outro_doc, 'idDocumento'):
                                    outro_info = process_document(outro_doc)
                                    outro_info['parent'] = doc_info['idDocumento']
                                    doc_info['documentos_vinculados'].append(outro_info)
                                    logger.debug(f"  Outro documento via {attr}: {outro_info['idDocumento']}")

                return doc_info

            # Processa documentos principais
            if hasattr(processo, 'documento'):
                docs = processo.documento if isinstance(processo.documento, list) else [processo.documento]
                docs_processados = {}
                refs_pendentes = {}

                # Primeira passagem: processa todos os documentos
                for doc in docs:
                    doc_info = process_document(doc)
                    docs_processados[doc_info['idDocumento']] = doc_info
                    if doc_info['parent']:
                        if doc_info['parent'] not in refs_pendentes:
                            refs_pendentes[doc_info['parent']] = []
                        refs_pendentes[doc_info['parent']].append(doc_info)

                # Segunda passagem: organiza as referências
                for doc_id, doc_info in docs_processados.items():
                    if doc_id in refs_pendentes:
                        doc_info['documentos_vinculados'].extend(refs_pendentes[doc_id])

                    # Adiciona apenas documentos principais (sem parent) à lista final
                    if not doc_info['parent']:
                        dados['processo']['documentos'].append(doc_info)
                        logger.debug(f"Documento principal {doc_info['idDocumento']} "
                                   f"com {len(doc_info['documentos_vinculados'])} vinculados")

        return dados
    except Exception as e:
        logger.error(f"Erro ao extrair dados MNI: {str(e)}")
        return {'sucesso': False, 'mensagem': f'Erro ao processar dados: {str(e)}'}
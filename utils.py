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
                # Dicionários para armazenar documentos
                principais = []
                vinculados = {}

                def extract_doc_info(doc):
                    """Extrai informações básicas do documento"""
                    return {
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

                # Processa todos os documentos do processo
                docs = processo.documento if isinstance(processo.documento, list) else [processo.documento]
                for doc in docs:
                    # Extrai informações do documento atual
                    doc_info = extract_doc_info(doc)
                    id_doc = doc_info['idDocumento']
                    logger.debug(f"\nProcessando documento: {id_doc}")

                    # 1. Verifica se é um documento vinculado (tem idDocumentoVinculado)
                    if hasattr(doc, 'idDocumentoVinculado'):
                        id_principal = getattr(doc, 'idDocumentoVinculado')
                        if id_principal:
                            if id_principal not in vinculados:
                                vinculados[id_principal] = []
                            vinculados[id_principal].append(doc_info)
                            logger.debug(f"  É vinculado ao documento: {id_principal}")
                            continue

                    # 2. Verifica se tem documentos vinculados como elementos
                    if hasattr(doc, 'documentoVinculado'):
                        docs_vinc = doc.documentoVinculado
                        if not isinstance(docs_vinc, list):
                            docs_vinc = [docs_vinc]

                        for doc_vinc in docs_vinc:
                            vinc_info = extract_doc_info(doc_vinc)
                            doc_info['documentos_vinculados'].append(vinc_info)
                            logger.debug(f"  Tem documento vinculado: {vinc_info['idDocumento']}")

                    # Se chegou aqui, é um documento principal
                    principais.append(doc_info)
                    logger.debug("  É um documento principal")

                # Adiciona os documentos vinculados aos seus principais
                for doc_info in principais:
                    id_doc = doc_info['idDocumento']
                    if id_doc in vinculados:
                        doc_info['documentos_vinculados'].extend(vinculados[id_doc])
                        logger.debug(f"Vinculando {len(vinculados[id_doc])} documentos ao {id_doc}")

                # Adiciona os documentos principais ao resultado
                dados['processo']['documentos'] = principais
                logger.debug(f"\nTotal de documentos principais: {len(principais)}")
                logger.debug(f"Total de documentos vinculados: {sum(len(v) for v in vinculados.values())}")

        return dados
    except Exception as e:
        logger.error(f"Erro ao extrair dados MNI: {str(e)}")
        return {'sucesso': False, 'mensagem': f'Erro ao processar dados: {str(e)}'}
        
def extract_capa_processo(resposta):
    """Extrai apenas os dados da capa do processo, sem incluir os documentos"""
    try:
        dados = {
            'sucesso': getattr(resposta, 'sucesso', False),
            'mensagem': getattr(resposta, 'mensagem', ''),
            'processo': {}
        }

        if hasattr(resposta, 'processo'):
            processo = resposta.processo
            
            # Dados básicos do processo
            dados_processo = {
                'numero': getattr(processo, 'numero', ''),
                'classeProcessual': getattr(processo, 'classeProcessual', ''),
                'dataAjuizamento': getattr(processo, 'dataAjuizamento', ''),
                'valorCausa': getattr(processo, 'valorCausa', ''),
                'orgaoJulgador': getattr(getattr(processo, 'orgaoJulgador', {}), 'descricao', ''),
                'jurisdicao': getattr(getattr(processo, 'orgaoJulgador', {}), 'codigoOrgao', ''),
                'nivelSigilo': getattr(processo, 'nivelSigilo', 0),
                'intervencaoMP': getattr(processo, 'intervencaoMP', False),
                'movimentacoes': []
            }
            
            # Extrair assuntos do processo
            if hasattr(processo, 'assunto'):
                assuntos = processo.assunto if isinstance(processo.assunto, list) else [processo.assunto]
                dados_processo['assuntos'] = [
                    {
                        'codigo': getattr(assunto, 'codigoNacional', ''),
                        'descricao': getattr(assunto, 'descricao', ''),
                        'principal': getattr(assunto, 'principal', False)
                    } for assunto in assuntos
                ]
            else:
                dados_processo['assuntos'] = []
                
            # Extrair polos do processo
            if hasattr(processo, 'polo'):
                polos = processo.polo if isinstance(processo.polo, list) else [processo.polo]
                dados_processo['polos'] = []
                
                for polo in polos:
                    polo_info = {
                        'polo': getattr(polo, 'polo', ''),
                        'partes': []
                    }
                    
                    if hasattr(polo, 'parte'):
                        partes = polo.parte if isinstance(polo.parte, list) else [polo.parte]
                        
                        for parte in partes:
                            parte_info = {
                                'nome': getattr(parte, 'nome', ''),
                                'documento': getattr(parte, 'numeroDocumentoPrincipal', '')
                            }
                            
                            # Adicionar advogados se existirem
                            if hasattr(parte, 'advogado'):
                                advogados = parte.advogado if isinstance(parte.advogado, list) else [parte.advogado]
                                parte_info['advogados'] = [
                                    {
                                        'nome': getattr(adv, 'nome', ''),
                                        'numeroOAB': getattr(adv, 'numeroOAB', '')
                                    } for adv in advogados
                                ]
                            
                            polo_info['partes'].append(parte_info)
                    
                    dados_processo['polos'].append(polo_info)
            else:
                dados_processo['polos'] = []
                
            # Extrair movimentações processuais
            if hasattr(processo, 'movimento'):
                movs = processo.movimento if isinstance(processo.movimento, list) else [processo.movimento]
                
                for mov in movs:
                    mov_info = {
                        'dataHora': getattr(mov, 'dataHora', ''),
                        'codigoMovimento': getattr(mov, 'codigoNacional', ''),
                        'descricao': getattr(mov, 'descricao', ''),
                        'complemento': getattr(mov, 'complemento', '')
                    }
                    
                    dados_processo['movimentacoes'].append(mov_info)
            
            dados['processo'] = dados_processo

        return dados
    except Exception as e:
        logger.error(f"Erro ao extrair dados da capa do processo: {str(e)}")
        return {'sucesso': False, 'mensagem': f'Erro ao processar dados da capa: {str(e)}'}
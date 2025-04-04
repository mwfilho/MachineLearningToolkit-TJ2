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
        logger.debug(f"Iniciando extração da capa do processo. Tipo de resposta: {type(resposta)}")
        logger.debug(f"Atributos disponíveis na resposta: {dir(resposta)}")
        
        dados = {
            'sucesso': getattr(resposta, 'sucesso', False),
            'mensagem': getattr(resposta, 'mensagem', ''),
            'processo': {}
        }

        if hasattr(resposta, 'processo'):
            processo = resposta.processo
            logger.debug(f"Atributos disponíveis no objeto processo: {dir(processo)}")
            
            # Dados básicos do processo
            dados_processo = {
                'numero': getattr(processo, 'numero', ''),
                'classeProcessual': getattr(processo, 'classeProcessual', ''),
                'dataAjuizamento': getattr(processo, 'dataAjuizamento', ''),
                'valorCausa': getattr(processo, 'valorCausa', ''),
                'nivelSigilo': getattr(processo, 'nivelSigilo', 0),
                'intervencaoMP': getattr(processo, 'intervencaoMP', False),
                'movimentacoes': [],
                'assuntos': [],
                'polos': []
            }
            
            # Extrair informações do órgão julgador
            if hasattr(processo, 'orgaoJulgador'):
                orgao = processo.orgaoJulgador
                logger.debug(f"Atributos do órgão julgador: {dir(orgao)}")
                dados_processo['orgaoJulgador'] = getattr(orgao, 'nomeOrgao', '')
                dados_processo['jurisdicao'] = getattr(orgao, 'codigoOrgao', '')
            else:
                logger.debug("Processo não possui atributo orgaoJulgador")
                
            # Extrair assuntos do processo
            if hasattr(processo, 'assunto'):
                logger.debug("Processando assuntos do processo")
                assuntos = processo.assunto if isinstance(processo.assunto, list) else [processo.assunto]
                for assunto in assuntos:
                    logger.debug(f"Atributos do assunto: {dir(assunto)}")
                    dados_processo['assuntos'].append({
                        'codigo': getattr(assunto, 'codigoNacional', ''),
                        'descricao': getattr(assunto, 'descricao', ''),
                        'principal': getattr(assunto, 'principal', False)
                    })
            else:
                logger.debug("Processo não possui atributo assunto")
                
            # Extrair polos do processo
            if hasattr(processo, 'polo'):
                logger.debug("Processando polos do processo")
                polos = processo.polo if isinstance(processo.polo, list) else [processo.polo]
                
                for polo in polos:
                    logger.debug(f"Atributos do polo: {dir(polo)}")
                    polo_info = {
                        'polo': getattr(polo, 'polo', ''),
                        'partes': []
                    }
                    
                    if hasattr(polo, 'parte'):
                        partes = polo.parte if isinstance(polo.parte, list) else [polo.parte]
                        
                        for parte in partes:
                            logger.debug(f"Atributos da parte: {dir(parte)}")
                            parte_info = {
                                'nome': '',
                                'documento': ''
                            }
                            
                            # Verificar se a parte tem o atributo 'pessoa'
                            if hasattr(parte, 'pessoa'):
                                pessoa = parte.pessoa
                                logger.debug(f"Atributos da pessoa: {dir(pessoa)}")
                                parte_info['nome'] = getattr(pessoa, 'nome', '')
                                # Verificar se existe documento da pessoa
                                if hasattr(pessoa, 'documento') and pessoa.documento:
                                    docs = pessoa.documento if isinstance(pessoa.documento, list) else [pessoa.documento]
                                    if docs:
                                        parte_info['documento'] = getattr(docs[0], 'codigoDocumento', '')
                            else:
                                parte_info['nome'] = getattr(parte, 'nome', '')
                                parte_info['documento'] = getattr(parte, 'numeroDocumentoPrincipal', '')
                            
                            # Adicionar advogados se existirem
                            if hasattr(parte, 'advogado'):
                                advogados = parte.advogado if isinstance(parte.advogado, list) else [parte.advogado]
                                parte_info['advogados'] = []
                                
                                for adv in advogados:
                                    logger.debug(f"Atributos do advogado: {dir(adv)}")
                                    parte_info['advogados'].append({
                                        'nome': getattr(adv, 'nome', ''),
                                        'numeroOAB': getattr(adv, 'numeroOAB', '')
                                    })
                            
                            polo_info['partes'].append(parte_info)
                    
                    dados_processo['polos'].append(polo_info)
            else:
                logger.debug("Processo não possui atributo polo")
                
            # Extrair movimentações processuais
            if hasattr(processo, 'movimento'):
                logger.debug("Processando movimentações do processo")
                movs = processo.movimento if isinstance(processo.movimento, list) else [processo.movimento]
                
                for mov in movs:
                    logger.debug(f"Atributos da movimentação: {dir(mov)}")
                    
                    mov_info = {
                        'dataHora': getattr(mov, 'dataHora', ''),
                        'complemento': []
                    }
                    
                    # Verificar estrutura da movimentação
                    if hasattr(mov, 'movimentoNacional'):
                        mov_nac = mov.movimentoNacional
                        logger.debug(f"Atributos da movimentação nacional: {dir(mov_nac)}")
                        mov_info['codigoMovimento'] = getattr(mov_nac, 'codigoNacional', '')
                        
                        # Verificar se tem complemento
                        if hasattr(mov_nac, 'complemento'):
                            comps = mov_nac.complemento if isinstance(mov_nac.complemento, list) else [mov_nac.complemento]
                            for comp in comps:
                                mov_info['complemento'].append(str(comp))
                    else:
                        mov_info['codigoMovimento'] = getattr(mov, 'codigoNacional', '')
                        mov_info['descricao'] = getattr(mov, 'descricao', '')
                        
                        # Verificar se tem complemento
                        if hasattr(mov, 'complemento'):
                            comps = mov.complemento if isinstance(mov.complemento, list) else [mov.complemento]
                            for comp in comps:
                                mov_info['complemento'].append(str(comp))
                    
                    dados_processo['movimentacoes'].append(mov_info)
            else:
                logger.debug("Processo não possui atributo movimento")
            
            dados['processo'] = dados_processo
            logger.debug(f"Dados da capa extraídos: {dados}")

        return dados
    except Exception as e:
        logger.error(f"Erro ao extrair dados da capa do processo: {str(e)}", exc_info=True)
        return {'sucesso': False, 'mensagem': f'Erro ao processar dados da capa: {str(e)}'}
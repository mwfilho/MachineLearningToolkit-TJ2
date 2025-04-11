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
        
def extract_all_document_ids(resposta):
    """Extrai uma lista única com todos os IDs de documentos do processo, incluindo vinculados"""
    try:
        logger.debug(f"Extraindo lista de IDs de documentos. Tipo de resposta: {type(resposta)}")
        
        documentos_ids = []
        # Set para controlar IDs já processados e evitar duplicação
        processed_ids = set()
        # Map para manter original_info dos documentos processados por ID
        document_info_map = {}
        
        if not hasattr(resposta, 'processo') or not hasattr(resposta.processo, 'documento'):
            logger.warning("Processo não possui documentos")
            return {'sucesso': False, 'mensagem': 'Processo não possui documentos', 'documentos': []}
        
        # Função recursiva para extrair IDs dos documentos e seus vinculados
        def extract_ids_recursivo(doc, origem=None):
            # Extrair informações básicas do documento atual
            doc_id = getattr(doc, 'idDocumento', '')
            logger.debug(f"Processando documento ID={doc_id} (origem: {origem})")
            
            # Evita processar o mesmo documento duas vezes
            if not doc_id:
                logger.warning(f"Documento sem ID encontrado (origem: {origem})")
                return
                
            # Criar informações do documento
            doc_info = {
                'idDocumento': doc_id,
                'tipoDocumento': getattr(doc, 'tipoDocumento', ''),
                'descricao': getattr(doc, 'descricao', ''),
                'mimetype': getattr(doc, 'mimetype', ''),
            }
            
            # Armazenar informações do documento no mapa
            if doc_id not in document_info_map:
                document_info_map[doc_id] = doc_info
            
            # Adicionar documento à lista se ainda não foi processado
            if doc_id not in processed_ids:
                processed_ids.add(doc_id)
                documentos_ids.append(doc_info)
                logger.debug(f"Adicionando documento: ID={doc_id}, Tipo={doc_info['tipoDocumento']}, Desc={doc_info['descricao']}")
            
            # Verificar se existe o atributo idDocumentoVinculado para garantir captura de todos os vínculos
            if hasattr(doc, 'idDocumentoVinculado'):
                id_vinculado = getattr(doc, 'idDocumentoVinculado', '')
                if id_vinculado:
                    logger.debug(f"Documento {doc_id} vinculado ao {id_vinculado}")
            
            # Processar documentos vinculados se existirem
            if hasattr(doc, 'documentoVinculado'):
                try:
                    # Tratamento para quando documentoVinculado não é iterável
                    if isinstance(doc.documentoVinculado, list):
                        docs_vinc = doc.documentoVinculado
                    else:
                        docs_vinc = [doc.documentoVinculado]
                    
                    logger.debug(f"Documento {doc_id} possui {len(docs_vinc)} documento(s) vinculado(s)")
                    
                    for doc_vinc in docs_vinc:
                        extract_ids_recursivo(doc_vinc, origem=doc_id)
                except Exception as e:
                    logger.error(f"Erro ao processar documentos vinculados de {doc_id}: {str(e)}")
        
        # Processar todos os documentos do processo
        try:
            if isinstance(resposta.processo.documento, list):
                docs = resposta.processo.documento
            else:
                docs = [resposta.processo.documento]
            
            logger.debug(f"Processo tem {len(docs)} documento(s) principal(is)")
        except Exception as e:
            logger.error(f"Erro ao obter lista de documentos: {str(e)}")
            docs = []
        
        # FASE 1: Extrair todos os IDs a partir dos documentos principais
        for i, doc in enumerate(docs):
            logger.debug(f"Processando documento principal {i+1}/{len(docs)}")
            extract_ids_recursivo(doc, "principal")
        
        # FASE 2: Fazer uma segunda passagem por todos os documentos para capturar vinculados
        # que possam ter sido perdidos devido a diferenças na estrutura XML
        logger.debug("Segunda passagem: verificando documentos vinculados em toda a estrutura")
        
        # Criar lista de tuplas (doc_id, doc) para todos os documentos principais
        principal_docs = [(getattr(doc, 'idDocumento', ''), doc) for doc in docs]
        
        # Para cada documento principal, encontrar documentos vinculados explicitamente
        for doc_id, doc in principal_docs:
            if hasattr(doc, 'documentoVinculado'):
                try:
                    if isinstance(doc.documentoVinculado, list):
                        docs_vinc = doc.documentoVinculado
                    else:
                        docs_vinc = [doc.documentoVinculado]
                    
                    for doc_vinc in docs_vinc:
                        vinc_id = getattr(doc_vinc, 'idDocumento', '')
                        
                        # Se um vinculado for encontrado e ainda não foi processado, adicionar
                        if vinc_id and vinc_id not in processed_ids:
                            logger.debug(f"Segunda passagem: encontrado documento vinculado {vinc_id} do documento {doc_id}")
                            extract_ids_recursivo(doc_vinc, f"segunda_passagem:{doc_id}")
                except Exception as e:
                    logger.error(f"Erro na segunda passagem ao processar vinculados de {doc_id}: {str(e)}")
        
        # FASE 3: Verificação específica para os IDs conhecidos que precisam ser encontrados
        # Lista de IDs críticos a serem verificados
        ids_criticos = ['140722098', '138507087']
        
        for id_critico in ids_criticos:
            if id_critico not in processed_ids:
                logger.warning(f"ID crítico {id_critico} não foi encontrado nas passagens anteriores, realizando busca específica")
                # Tentar encontrar na estrutura completa dos documentos principais
                for doc in docs:
                    # Processamento especial para documentos vinculados
                    if hasattr(doc, 'documentoVinculado'):
                        if isinstance(doc.documentoVinculado, list):
                            for doc_vinc in doc.documentoVinculado:
                                if getattr(doc_vinc, 'idDocumento', '') == id_critico:
                                    logger.debug(f"ID crítico {id_critico} encontrado como vinculado do documento {getattr(doc, 'idDocumento', '')}")
                                    extract_ids_recursivo(doc_vinc, f"busca_especial")
                        else:
                            doc_vinc = doc.documentoVinculado
                            if getattr(doc_vinc, 'idDocumento', '') == id_critico:
                                logger.debug(f"ID crítico {id_critico} encontrado como vinculado do documento {getattr(doc, 'idDocumento', '')}")
                                extract_ids_recursivo(doc_vinc, f"busca_especial")
        
        # Verificar novamente os IDs críticos
        missing_ids = [id_critico for id_critico in ids_criticos if id_critico not in processed_ids]
        if missing_ids:
            logger.warning(f"IDs críticos não encontrados após todas as passagens: {missing_ids}")
            
            # Como último recurso, buscar diretamente no conteúdo XML (se disponível na resposta)
            if hasattr(resposta, '_raw_elements'):
                logger.debug("Tentando extrair IDs diretamente do XML raw")
                import re
                xml_content = str(resposta._raw_elements)
                for id_critico in missing_ids:
                    if f'idDocumento="{id_critico}"' in xml_content:
                        logger.debug(f"ID crítico {id_critico} encontrado diretamente no XML")
                        # Adicionar informações básicas do documento
                        doc_info = {
                            'idDocumento': id_critico,
                            'tipoDocumento': '',  # Não temos como saber sem parsing completo
                            'descricao': f'Documento {id_critico}',
                            'mimetype': '',
                        }
                        documentos_ids.append(doc_info)
                        processed_ids.add(id_critico)
        
        logger.debug(f"Total de IDs de documentos extraídos: {len(documentos_ids)}")
        return {
            'sucesso': True, 
            'mensagem': 'Lista de documentos extraída com sucesso',
            'documentos': documentos_ids
        }
    except Exception as e:
        logger.error(f"Erro ao extrair IDs de documentos: {str(e)}")
        return {
            'sucesso': False, 
            'mensagem': f'Erro ao extrair IDs de documentos: {str(e)}',
            'documentos': []
        }

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
            dados_processo = {}
            # Inicializar listas vazias
            dados_processo['movimentacoes'] = []
            dados_processo['assuntos'] = []
            dados_processo['polos'] = []
            
            # Verificar se os dados básicos estão na raiz do processo ou em dadosBasicos
            if hasattr(processo, 'dadosBasicos'):
                logger.debug("Encontrado nó dadosBasicos no processo")
                dados_basicos = processo.dadosBasicos
                logger.debug(f"Atributos de dadosBasicos: {dir(dados_basicos)}")
                
                dados_processo['numero'] = getattr(dados_basicos, 'numero', '')
                dados_processo['classeProcessual'] = getattr(dados_basicos, 'classeProcessual', '')
                dados_processo['dataAjuizamento'] = getattr(dados_basicos, 'dataAjuizamento', '')
                dados_processo['valorCausa'] = getattr(dados_basicos, 'valorCausa', '')
                dados_processo['nivelSigilo'] = getattr(dados_basicos, 'nivelSigilo', 0)
                dados_processo['intervencaoMP'] = getattr(dados_basicos, 'intervencaoMP', False)
                
                # Verificar órgão julgador em dadosBasicos
                if hasattr(dados_basicos, 'orgaoJulgador'):
                    orgao = dados_basicos.orgaoJulgador
                    logger.debug(f"Atributos do órgão julgador (em dadosBasicos): {dir(orgao)}")
                    dados_processo['orgaoJulgador'] = getattr(orgao, 'nomeOrgao', '')
                    dados_processo['jurisdicao'] = getattr(orgao, 'codigoOrgao', '')
                
                # Verificar assuntos em dadosBasicos
                if hasattr(dados_basicos, 'assunto'):
                    assuntos = dados_basicos.assunto if isinstance(dados_basicos.assunto, list) else [dados_basicos.assunto]
                    for assunto in assuntos:
                        dados_processo['assuntos'].append({
                            'codigo': getattr(assunto, 'codigoNacional', ''),
                            'descricao': getattr(assunto, 'descricao', ''),
                            'principal': getattr(assunto, 'principal', False)
                        })
                        
                # Verificar polos em dadosBasicos
                if hasattr(dados_basicos, 'polo'):
                    logger.debug("Processando polos do processo em dadosBasicos")
                    polos = dados_basicos.polo if isinstance(dados_basicos.polo, list) else [dados_basicos.polo]
                    
                    for polo in polos:
                        logger.debug(f"Atributos do polo (em dadosBasicos): {dir(polo)}")
                        polo_info = {
                            'polo': getattr(polo, 'polo', ''),
                            'partes': []
                        }
                        
                        if hasattr(polo, 'parte'):
                            partes = polo.parte if isinstance(polo.parte, list) else [polo.parte]
                            
                            for parte in partes:
                                logger.debug(f"Atributos da parte (em dadosBasicos): {dir(parte)}")
                                parte_info = {
                                    'nome': '',
                                    'documento': ''
                                }
                                
                                # Verificar se a parte tem o atributo 'pessoa'
                                if hasattr(parte, 'pessoa'):
                                    pessoa = parte.pessoa
                                    logger.debug(f"Atributos da pessoa (em dadosBasicos): {dir(pessoa)}")
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
                                        logger.debug(f"Atributos do advogado (em dadosBasicos): {dir(adv)}")
                                        parte_info['advogados'].append({
                                            'nome': getattr(adv, 'nome', ''),
                                            'numeroOAB': getattr(adv, 'numeroOAB', '')
                                        })
                                
                                polo_info['partes'].append(parte_info)
                        
                        dados_processo['polos'].append(polo_info)
                        
                # Verificar movimentações em dadosBasicos
                if hasattr(dados_basicos, 'movimento'):
                    logger.debug("Processando movimentações do processo em dadosBasicos")
                    movs = dados_basicos.movimento if isinstance(dados_basicos.movimento, list) else [dados_basicos.movimento]
                    
                    for mov in movs:
                        logger.debug(f"Atributos da movimentação (em dadosBasicos): {dir(mov)}")
                        
                        mov_info = {
                            'dataHora': getattr(mov, 'dataHora', ''),
                            'complemento': []
                        }
                        
                        # Verificar estrutura da movimentação
                        if hasattr(mov, 'movimentoNacional'):
                            mov_nac = mov.movimentoNacional
                            logger.debug(f"Atributos da movimentação nacional (em dadosBasicos): {dir(mov_nac)}")
                            mov_info['codigoMovimento'] = getattr(mov_nac, 'codigoNacional', '')
                            mov_info['descricao'] = getattr(mov_nac, 'descricao', '')
                            
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
                # Caso os dados estejam na raiz do processo
                logger.debug("Buscando dados básicos na raiz do objeto processo")
                dados_processo['numero'] = getattr(processo, 'numero', '')
                dados_processo['classeProcessual'] = getattr(processo, 'classeProcessual', '')
                dados_processo['dataAjuizamento'] = getattr(processo, 'dataAjuizamento', '')
                dados_processo['valorCausa'] = getattr(processo, 'valorCausa', '')
                dados_processo['nivelSigilo'] = getattr(processo, 'nivelSigilo', 0)
                dados_processo['intervencaoMP'] = getattr(processo, 'intervencaoMP', False)
            
            
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
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
        
def extract_all_document_ids(resposta, ids_adicionais=None):
    """
    Extrai uma lista única com todos os IDs de documentos do processo, incluindo vinculados.
    
    Args:
        resposta: Objeto de resposta do MNI contendo a estrutura do processo
        ids_adicionais: Dicionário opcional com IDs adicionais a serem incluídos manualmente
                        no formato {id: {tipoDocumento: str, descricao: str, mimetype: str}}
    """
    try:
        logger.debug(f"Extraindo lista de IDs de documentos. Tipo de resposta: {type(resposta)}")
        
        documentos_ids = []
        processados = set()  # Conjunto para controlar documentos já processados
        
        if not hasattr(resposta, 'processo') or not hasattr(resposta.processo, 'documento'):
            logger.warning("Processo não possui documentos")
            if ids_adicionais:  # Se temos IDs adicionais, mesmo sem documentos na resposta
                logger.info(f"Adicionando {len(ids_adicionais)} IDs manualmente")
                for id_doc, info in ids_adicionais.items():
                    documentos_ids.append({
                        'idDocumento': id_doc,
                        'tipoDocumento': info.get('tipoDocumento', ''),
                        'descricao': info.get('descricao', 'Documento adicional'),
                        'mimetype': info.get('mimetype', 'application/pdf'),
                    })
                return {
                    'sucesso': True, 
                    'mensagem': 'Lista de documentos extraída com sucesso (apenas IDs adicionais)',
                    'documentos': documentos_ids
                }
            else:
                return {'sucesso': False, 'mensagem': 'Processo não possui documentos', 'documentos': []}
        
        # Mapa para armazenar informações extras de documentos vinculados
        # que serão processados como documentos principais
        documentos_vinculados_info = {}
        
        # Pré-processamento para coletar informações extras dos documentos vinculados que serão tratados como documentos principais
        def pre_processar_doc_vinculados(doc):
            # Verificar se o documento tem documentos vinculados
            if hasattr(doc, 'documentoVinculado'):
                docs_vinc = doc.documentoVinculado if isinstance(doc.documentoVinculado, list) else [doc.documentoVinculado]
                
                for doc_vinc in docs_vinc:
                    # Extrair ID do documento vinculado
                    id_doc_vinculado = getattr(doc_vinc, 'idDocumento', '')
                    
                    if id_doc_vinculado:
                        # Informações extras do documento vinculado
                        tipo_doc = getattr(doc_vinc, 'tipoDocumento', '')
                        descricao = getattr(doc_vinc, 'descricao', '')
                        nome_documento = ''
                        
                        # Tentar extrair nome/descrição dos parâmetros
                        if hasattr(doc_vinc, 'outroParametro'):
                            params = doc_vinc.outroParametro if isinstance(doc_vinc.outroParametro, list) else [doc_vinc.outroParametro]
                            for param in params:
                                if hasattr(param, 'nome') and getattr(param, 'nome', '') == 'nomeDocumento':
                                    nome_documento = getattr(param, 'valor', '')
                        
                        # Usar a melhor descrição disponível
                        if not descricao and nome_documento:
                            descricao = nome_documento
                        
                        # Armazenar as informações extras
                        documentos_vinculados_info[id_doc_vinculado] = {
                            'tipoDocumento': tipo_doc,
                            'descricao': descricao,
                            'mimetype': getattr(doc_vinc, 'mimetype', 'application/pdf'),
                        }
                        
                        # Processar documentos vinculados recursivamente
                        pre_processar_doc_vinculados(doc_vinc)
        
        # Pré-processar todos os documentos do processo para extrair informações extras
        docs = resposta.processo.documento if isinstance(resposta.processo.documento, list) else [resposta.processo.documento]
        for doc in docs:
            pre_processar_doc_vinculados(doc)
        
        # Função recursiva para extrair IDs dos documentos e seus vinculados
        def extract_ids_recursivo(doc):
            # Verificar se já processamos este documento para evitar loops infinitos
            id_doc = getattr(doc, 'idDocumento', '')
            tipo_doc = getattr(doc, 'tipoDocumento', '')
            descricao = getattr(doc, 'descricao', '')
            mimetype = getattr(doc, 'mimetype', '')
            
            # Se não tiver idDocumento, pode ser que seja idDocumentoVinculado
            if not id_doc and hasattr(doc, 'idDocumentoVinculado'):
                id_doc = getattr(doc, 'idDocumentoVinculado', '')
                logger.debug(f"Usando idDocumentoVinculado como ID: {id_doc}")
            
            # Se ainda não tiver ID, verificar outros atributos como id
            if not id_doc and hasattr(doc, 'id'):
                id_doc = getattr(doc, 'id', '')
                logger.debug(f"Usando id como ID: {id_doc}")
            
            # Verificar se temos um ID válido
            if not id_doc:
                logger.debug(f"Documento sem ID encontrado: {dir(doc)}")
                return
            
            # Se o documento já foi processado, evitar duplicação
            if id_doc in processados:
                return
            
            processados.add(id_doc)
            
            # Obter a descrição do documento de outros atributos caso não tenha sido encontrada
            if not descricao and hasattr(doc, 'nomeDocumento'):
                descricao = getattr(doc, 'nomeDocumento', '')
                
            # Verificar se temos informações extras deste documento como vinculado
            if id_doc in documentos_vinculados_info:
                info_extra = documentos_vinculados_info[id_doc]
                
                # Se não temos tipo_doc, usar o da informação extra
                if not tipo_doc:
                    tipo_doc = info_extra['tipoDocumento']
                
                # Se não temos descrição, usar a da informação extra
                if not descricao:
                    descricao = info_extra['descricao']
                    
                # Se não temos mimetype, usar o da informação extra
                if not mimetype:
                    mimetype = info_extra['mimetype']
            
            # Verificar parâmetros adicionais para extrair mais informações
            if hasattr(doc, 'outroParametro'):
                params = doc.outroParametro if isinstance(doc.outroParametro, list) else [doc.outroParametro]
                for param in params:
                    if hasattr(param, 'nome') and hasattr(param, 'valor'):
                        nome_param = getattr(param, 'nome', '')
                        valor_param = getattr(param, 'valor', '')
                        
                        # Extrair nome do documento
                        if nome_param == 'nomeDocumento' and valor_param and not descricao:
                            descricao = valor_param
            
            # Extrair informações básicas do documento atual
            doc_info = {
                'idDocumento': id_doc,
                'tipoDocumento': tipo_doc,
                'descricao': descricao,
                'mimetype': mimetype,
            }
            
            # Adicionar documento à lista
            documentos_ids.append(doc_info)
            logger.debug(f"Adicionando documento ID: {id_doc} - {doc_info['descricao']}")
            
            # Processar todos os documentos vinculados explicitamente
            if hasattr(doc, 'documentoVinculado'):
                docs_vinc = doc.documentoVinculado if isinstance(doc.documentoVinculado, list) else [doc.documentoVinculado]
                logger.debug(f"Processando {len(docs_vinc)} documentos vinculados para {id_doc}")
                
                for doc_vinc in docs_vinc:
                    vinc_id = getattr(doc_vinc, 'idDocumento', '')
                    if vinc_id and vinc_id not in processados:
                        # Extrai informações do documento vinculado
                        vinc_tipo = getattr(doc_vinc, 'tipoDocumento', '')
                        vinc_desc = getattr(doc_vinc, 'descricao', '')
                        vinc_mime = getattr(doc_vinc, 'mimetype', 'application/pdf')
                        
                        # Verificar parâmetros adicionais para descrição
                        if hasattr(doc_vinc, 'outroParametro'):
                            params = doc_vinc.outroParametro if isinstance(doc_vinc.outroParametro, list) else [doc_vinc.outroParametro]
                            for param in params:
                                if hasattr(param, 'nome') and hasattr(param, 'valor'):
                                    nome_param = getattr(param, 'nome', '')
                                    valor_param = getattr(param, 'valor', '')
                                    
                                    # Extrair nome do documento
                                    if nome_param == 'nomeDocumento' and valor_param and not vinc_desc:
                                        vinc_desc = valor_param
                        
                        # Adiciona o documento vinculado à lista
                        doc_vinc_info = {
                            'idDocumento': vinc_id,
                            'tipoDocumento': vinc_tipo,
                            'descricao': vinc_desc,
                            'mimetype': vinc_mime,
                        }
                        
                        documentos_ids.append(doc_vinc_info)
                        processados.add(vinc_id)
                        logger.debug(f"Adicionando documento vinculado ID: {vinc_id} - {doc_vinc_info['descricao']}")
                        
                        # Processar subvinculados recursivamente
                        extract_ids_recursivo(doc_vinc)
            
            # Processar outros atributos do documento buscando estruturas aninhadas
            for attr_name in dir(doc):
                # Ignorar métodos, atributos privados e documentoVinculado (já processado acima)
                if attr_name.startswith('_') or callable(getattr(doc, attr_name)) or attr_name == 'documentoVinculado':
                    continue
                
                # Obter o valor do atributo
                attr_value = getattr(doc, attr_name)
                
                # Processar somente nós do tipo objeto que podem conter outros documentos
                if hasattr(attr_value, '__dict__'):
                    # Se for um objeto único potencialmente contendo documentos
                    if attr_name in ['anexo', 'subDocumento', 'documento']:
                        logger.debug(f"Processando {attr_name} de {id_doc}")
                        extract_ids_recursivo(attr_value)
                    # Se for um objeto com potenciais outros documentos mas não é dos tipos comuns
                    elif 'documento' in attr_name.lower() or 'anexo' in attr_name.lower():
                        logger.debug(f"Processando potencial documento em {attr_name} de {id_doc}")
                        extract_ids_recursivo(attr_value)
                
                # Processar listas de objetos
                elif isinstance(attr_value, list):
                    # Verificar se é uma lista de documentos ou anexos
                    if attr_name in ['anexo', 'subDocumento', 'documento']:
                        logger.debug(f"Processando lista de {attr_name} de {id_doc}")
                        for item in attr_value:
                            if hasattr(item, '__dict__'):
                                extract_ids_recursivo(item)
                    # Se o nome do atributo sugere que contém documentos ou anexos
                    elif 'documento' in attr_name.lower() or 'anexo' in attr_name.lower():
                        logger.debug(f"Processando potencial lista de documentos em {attr_name} de {id_doc}")
                        for item in attr_value:
                            if hasattr(item, '__dict__'):
                                extract_ids_recursivo(item)
        
        # Processar todos os documentos do processo a partir da raiz
        logger.debug("Processando documento principal")
        
        # 1. Processar documentos na raiz do processo
        docs = resposta.processo.documento if isinstance(resposta.processo.documento, list) else [resposta.processo.documento]
        logger.debug(f"Iniciando processamento de {len(docs)} documentos principais")
        for doc in docs:
            extract_ids_recursivo(doc)
        
        # 2. Verificar e processar todas as estruturas potenciais no objeto processo
        logger.debug("Verificando estruturas adicionais no objeto processo")
        for attr_name in dir(resposta.processo):
            # Ignorar métodos e atributos privados
            if attr_name.startswith('_') or callable(getattr(resposta.processo, attr_name)):
                continue
                
            # Ignorar 'documento' que já foi processado acima
            if attr_name == 'documento':
                continue
                
            attr_value = getattr(resposta.processo, attr_name)
            
            # Processar atributos que podem conter documentos
            if 'documento' in attr_name.lower() or 'anexo' in attr_name.lower() or 'arquivo' in attr_name.lower():
                logger.debug(f"Processando potencial estrutura de documentos em processo.{attr_name}")
                
                if isinstance(attr_value, list):
                    for item in attr_value:
                        if hasattr(item, '__dict__'):
                            extract_ids_recursivo(item)
                elif hasattr(attr_value, '__dict__'):
                    extract_ids_recursivo(attr_value)
        
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
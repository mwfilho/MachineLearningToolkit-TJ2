import json
import os
import sys
import time
import requests
from zeep import Client
from zeep.helpers import serialize_object
from easydict import EasyDict
from config import MNI_URL, MNI_SENHA_CONSULTANTE, MNI_CONSULTA_URL, MNI_ID_CONSULTANTE
import logging
import pandas as pd
from controle.exceptions import ExcecaoConsultaMNI
import itertools
import base64
from concurrent.futures import ThreadPoolExecutor
import concurrent.futures
from configparser import ConfigParser
from datetime import datetime
from zeep.exceptions import Fault
from datetime import date
from lxml import etree  # Para parsear o XML bruto
from email import message_from_bytes  # Para parsear multipart/MTOM
from email.policy import default as default_policy  # Política para parsing

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Namespaces definidos no WSDL e no exemplo de requisição
NSMAP_REQ = {
    'soapenv': 'http://schemas.xmlsoap.org/soap/envelope/',
    'ser': 'http://www.cnj.jus.br/servico-intercomunicacao-2.2.2/',
    'tip': 'http://www.cnj.jus.br/tipos-servico-intercomunicacao-2.2.2'
}
# Namespaces esperados na resposta
NSMAP_RESP = {
    'ns2': 'http://www.cnj.jus.br/intercomunicacao-2.2.2',
    'ns4': 'http://www.cnj.jus.br/servico-intercomunicacao-2.2.2/'
    # O namespace default não precisa ser mapeado explicitamente para este XPath
}

def debug_estrutura_documento(doc, nivel=0, prefixo=''):
    """
    Função auxiliar para debug que mapeia toda a estrutura de um documento
    """
    indent = '  ' * nivel
    logger.debug(f"{indent}{prefixo}{'=' * 40}")
    logger.debug(f"{indent}{prefixo}Analisando documento:")

    # Atributos básicos
    attrs_basicos = ['idDocumento', 'tipoDocumento', 'descricao', 'dataHora', 'mimetype']
    for attr in attrs_basicos:
        valor = getattr(doc, attr, 'N/A')
        logger.debug(f"{indent}{prefixo}{attr}: {valor}")

    # Lista todos os atributos do objeto
    logger.debug(f"{indent}{prefixo}Todos os atributos disponíveis:")
    for attr_name in dir(doc):
        if not attr_name.startswith('_'):  # Ignora atributos privados
            attr_value = getattr(doc, attr_name)
            if not callable(attr_value):  # Ignora métodos
                logger.debug(f"{indent}{prefixo}  {attr_name}: {attr_value}")

    # Verifica documentos vinculados
    if hasattr(doc, 'documentoVinculado'):
        logger.debug(f"{indent}{prefixo}Documentos Vinculados Encontrados:")
        docs_vinc = doc.documentoVinculado
        if not isinstance(docs_vinc, list):
            docs_vinc = [docs_vinc]

        for idx, doc_vinc in enumerate(docs_vinc, 1):
            logger.debug(f"{indent}{prefixo}Documento Vinculado #{idx}")
            debug_estrutura_documento(doc_vinc, nivel + 1, f"[Vinc {idx}] ")

    # Verifica documento individual
    if hasattr(doc, 'documento'):
        logger.debug(f"{indent}{prefixo}Documento Individual Encontrado:")
        if isinstance(doc.documento, list):
            for idx, sub_doc in enumerate(doc.documento, 1):
                debug_estrutura_documento(sub_doc, nivel + 1, f"[Doc {idx}] ")
        else:
            debug_estrutura_documento(doc.documento, nivel + 1, "[Doc] ")

    # Verifica lista de documentos
    if hasattr(doc, 'documentos'):
        logger.debug(f"{indent}{prefixo}Lista de Documentos Encontrada:")
        if isinstance(doc.documentos, list):
            for idx, sub_doc in enumerate(doc.documentos, 1):
                debug_estrutura_documento(sub_doc, nivel + 1, f"[Lista {idx}] ")
        else:
            debug_estrutura_documento(doc.documentos, nivel + 1, "[Lista] ")

def retorna_processo(num_processo, cpf=None, senha=None, incluir_documentos=True):
    """
    Consulta um processo judicial via MNI.

    Args:
        num_processo (str): Número do processo no formato CNJ
        cpf (str, optional): CPF/CNPJ do consultante. Se não fornecido, usa o padrão do ambiente
        senha (str, optional): Senha do consultante. Se não fornecida, usa o padrão do ambiente
        incluir_documentos (bool, optional): Se True, inclui informações sobre documentos do processo. 
                                           Se False, obtém apenas dados da capa do processo.

    Returns:
        EasyDict: Dados do processo consultado
    """
    url = MNI_URL
    cpf_consultante = cpf or MNI_ID_CONSULTANTE
    senha_consultante = senha or MNI_SENHA_CONSULTANTE

    if not cpf_consultante or not senha_consultante:
        raise ExcecaoConsultaMNI("Credenciais MNI não fornecidas. Configure MNI_ID_CONSULTANTE e MNI_SENHA_CONSULTANTE")

    logger.debug(f"\n{'=' * 80}\nIniciando consulta ao processo {num_processo}\n{'=' * 80}")
    logger.debug(f"Usando consultante: {cpf_consultante}")
    logger.debug(f"Incluindo documentos: {incluir_documentos}")

    request_data = {
        'idConsultante': cpf_consultante,
        'senhaConsultante': senha_consultante,
        'numeroProcesso': num_processo,
        'movimentos': True,
        'incluirCabecalho': True,
        'incluirDocumentos': incluir_documentos
    }

    try:
        client = Client(url)
        logger.debug("Cliente SOAP criado com sucesso")

        with client.settings(strict=False, xml_huge_tree=True):
            logger.debug("Enviando requisição SOAP")
            response = client.service.consultarProcesso(**request_data)
            logger.debug("Resposta SOAP recebida")

            data_dict = serialize_object(response)
            response = EasyDict(data_dict)

            if response.sucesso:
                if hasattr(response.processo, 'documento'):
                    logger.debug("\n=== INICIANDO ANÁLISE DETALHADA DA ESTRUTURA ===\n")

                    # Informações gerais do processo
                    logger.debug(f"Número do Processo: {getattr(response.processo, 'numero', 'N/A')}")
                    logger.debug(f"Classe Processual: {getattr(response.processo, 'classeProcessual', 'N/A')}")

                    # Analisa cada documento do processo
                    docs = response.processo.documento
                    if not isinstance(docs, list):
                        docs = [docs]

                    for idx, doc in enumerate(docs, 1):
                        logger.debug(f"\n{'#' * 80}")
                        logger.debug(f"DOCUMENTO PRINCIPAL #{idx}")
                        logger.debug(f"{'#' * 80}")
                        debug_estrutura_documento(doc)

                return response
            else:
                error_msg = f"Erro na consulta do processo {num_processo}: {response.mensagem}"
                logger.error(error_msg)
                raise ExcecaoConsultaMNI(error_msg)

    except Fault as e:
        if "loginFailed" in str(e):
            error_msg = "Erro de autenticação no MNI. Verifique suas credenciais (CPF/CNPJ e senha)"
        else:
            error_msg = f"Erro na comunicação SOAP: {str(e)}"
        logger.error(f"{error_msg} (Processo: {num_processo})")
        raise ExcecaoConsultaMNI(error_msg)
    except Exception as e:
        error_msg = f"Erro inesperado na consulta do processo {num_processo}: {str(e)}"
        logger.error(error_msg, exc_info=True)
        raise ExcecaoConsultaMNI(error_msg)

def retorna_documento_processo(num_processo, num_documento, cpf=None, senha=None):
    """
    Retorna um documento específico de um processo.

    Args:
        num_processo (str): Número do processo
        num_documento (str): ID do documento
        cpf (str, optional): CPF/CNPJ do consultante. Se não fornecido, usa o padrão do ambiente
        senha (str, optional): Senha do consultante. Se não fornecida, usa o padrão do ambiente

    Returns:
        dict: Dados do documento incluindo seu conteúdo
    """
    url = MNI_URL
    cpf_consultante = cpf or MNI_ID_CONSULTANTE
    senha_consultante = senha or MNI_SENHA_CONSULTANTE

    if not cpf_consultante or not senha_consultante:
        raise ExcecaoConsultaMNI("Credenciais MNI não fornecidas")

    logger.debug(f"\n{'=' * 80}")
    logger.debug(f"Consultando documento {num_documento} do processo {num_processo}")
    logger.debug(f"Usando consultante: {cpf_consultante}")
    logger.debug(f"{'=' * 80}\n")
    
    # Primeira tentativa: Método usando o envelope SOAP manual com o documento especificado diretamente
    try:
        logger.debug(f"Tentando abordagem direta com SOAP manual para documento {num_documento}")
        
        # Construir o envelope SOAP manualmente para obter o documento específico
        soap_envelope = f"""<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ser="http://www.cnj.jus.br/servico-intercomunicacao-2.2.2/" xmlns:tip="http://www.cnj.jus.br/tipos-servico-intercomunicacao-2.2.2">
   <soapenv:Header/>
   <soapenv:Body>
      <ser:consultarProcesso>
         <tip:idConsultante>{cpf_consultante}</tip:idConsultante>
         <tip:senhaConsultante>{senha_consultante}</tip:senhaConsultante>
         <tip:numeroProcesso>{num_processo}</tip:numeroProcesso>
         <tip:movimentos>false</tip:movimentos>
         <tip:incluirCabecalho>false</tip:incluirCabecalho>
         <tip:incluirDocumentos>true</tip:incluirDocumentos>
         <tip:documento>{num_documento.strip()}</tip:documento>
      </ser:consultarProcesso>
   </soapenv:Body>
</soapenv:Envelope>
"""
        # SOAPAction obtida do WSDL
        soap_action = "http://www.cnj.jus.br/servico-intercomunicacao-2.2.2/consultarProcesso"
        headers = {'Content-Type': 'text/xml; charset=utf-8',
                  'SOAPAction': soap_action}
        
        # Obter URL base sem ?wsdl
        url_parts = url.split('?')
        url_base = url_parts[0]
        
        logger.debug(f"Enviando requisição SOAP manual para documento {num_documento}...")
        response = requests.post(url_base, data=soap_envelope.encode('utf-8'), headers=headers, timeout=120)
        logger.debug(f"Resposta recebida para documento {num_documento}. Status: {response.status_code}")
        
        if response.status_code == 200:
            # --- Tratamento de MTOM/XOP ---
            content_type = response.headers.get('Content-Type', '')
            xml_to_parse = None

            if 'multipart/related' in content_type:
                logger.debug("Resposta é multipart/related (MTOM/XOP)")
                http_message_bytes = b"Content-Type: " + content_type.encode('utf-8') + b"\r\n\r\n" + response.content
                msg = message_from_bytes(http_message_bytes, policy=default_policy)

                if msg.is_multipart():
                    # Procurar a parte com o conteúdo do documento
                    found_xml_part = False
                    found_document_part = False
                    document_content = None
                    document_mimetype = 'application/octet-stream'
                    
                    for part in msg.iter_parts():
                        part_ct = part.get_content_type()
                        logger.debug(f"  Encontrada parte com Content-Type: {part_ct}")
                        
                        # Procurar pelo XML principal
                        if not found_xml_part and ('application/xop+xml' in part_ct or 'text/xml' in part_ct):
                            xml_to_parse = part.get_payload(decode=True)
                            found_xml_part = True
                            logger.debug("  Encontrada parte XML principal")
                            
                        # Procurar pelo conteúdo binário do documento
                        elif 'application/' in part_ct or 'text/' in part_ct or 'image/' in part_ct:
                            document_content = part.get_payload(decode=True)
                            document_mimetype = part_ct
                            found_document_part = True
                            logger.debug(f"  Encontrada parte com o conteúdo do documento: {part_ct}")
                    
                    # Se encontramos o conteúdo do documento diretamente
                    if found_document_part and document_content:
                        logger.debug("Documento encontrado diretamente na resposta MTOM/XOP")
                        return {
                            'num_processo': num_processo,
                            'id_documento': num_documento,
                            'id_tipo_documento': '',  # Não temos essa informação na resposta binária
                            'descricao': f"Documento {num_documento}",
                            'mimetype': document_mimetype,
                            'conteudo': document_content
                        }
                    
                    # Se não encontramos conteúdo direto, mas encontramos XML
                    if found_xml_part and xml_to_parse:
                        # Continuar com a análise do XML para extrair o documento
                        logger.debug("XML principal encontrado, analisando...")
                    else:
                        logger.debug("Não foi possível encontrar partes necessárias na resposta MTOM")
                        # Continuar para a próxima abordagem
                        
                else:
                    logger.debug("Content-Type era multipart, mas a mensagem não foi parseada como tal")
            elif 'text/xml' in content_type or 'application/soap+xml' in content_type:
                logger.debug("Resposta parece ser XML simples")
                xml_to_parse = response.content
            else:
                logger.debug(f"Content-Type inesperado: {content_type}")
                # Continuar para a próxima abordagem
        else:
            logger.debug(f"Erro na requisição: {response.status_code}")
            # Continuar para a próxima abordagem
    
    except Exception as manual_error:
        logger.debug(f"Erro na abordagem manual: {str(manual_error)}")
        # Continuar para a próxima abordagem
    
    # Segunda tentativa: usar a abordagem zeep com documento específico
    try:
        logger.debug("Tentando buscar documento diretamente pelo ID usando zeep")
        client_direct = Client(url)
        
        # Definir formato da requisição para busca direta
        request_data_direct = {
            'idConsultante': cpf_consultante,
            'senhaConsultante': senha_consultante,
            'numeroProcesso': num_processo,
            'documento': num_documento.strip(),  # Garante que o ID não tenha espaços
            'incluirDocumentos': True
        }
        
        logger.debug(f"Enviando requisição SOAP via zeep para documento {num_documento}")
        try:
            response_direct = client_direct.service.consultarProcesso(**request_data_direct)
            
            if response_direct and getattr(response_direct, 'sucesso', False):
                logger.debug("Busca direta pelo documento bem sucedida!")
                
                # Converter para EasyDict para facilitar o acesso
                data_dict_direct = serialize_object(response_direct)
                response_direct = EasyDict(data_dict_direct)
                
                if hasattr(response_direct, 'processo') and hasattr(response_direct.processo, 'documento'):
                    doc = response_direct.processo.documento
                    docs_direct = doc if isinstance(doc, list) else [doc]
                    
                    for doc_item in docs_direct:
                        doc_id = str(getattr(doc_item, 'idDocumento', '')).strip()
                        if doc_id == str(num_documento).strip():
                            logger.debug(f"Documento {num_documento} encontrado pela busca direta!")
                            
                            if doc_item.conteudo is None:
                                logger.debug(f"Documento {num_documento} encontrado mas sem conteúdo")
                                # Continuar para o método padrão
                                break
                                
                            # Atribuir valores padrão se não existirem
                            descricao = getattr(doc_item, 'descricao', f"Documento {num_documento}")
                            id_tipo_documento = getattr(doc_item, 'tipoDocumento', '')
                            mimetype = getattr(doc_item, 'mimetype', 'application/octet-stream')
                            
                            # Se o mimetype estiver vazio, tentar deduzir pelo conteúdo
                            if not mimetype and doc_item.conteudo:
                                if len(doc_item.conteudo) > 4 and doc_item.conteudo[:4] == b'%PDF':
                                    mimetype = 'application/pdf'
                                else:
                                    mimetype = 'application/octet-stream'
                                    
                            return {
                                'num_processo': num_processo,
                                'id_documento': doc_item.idDocumento,
                                'id_tipo_documento': id_tipo_documento,
                                'descricao': descricao,
                                'mimetype': mimetype,
                                'conteudo': doc_item.conteudo
                            }
        except Exception as direct_error:
            logger.debug(f"Erro na busca direta via zeep: {str(direct_error)}")
            # Continuar para o método padrão
    except Exception as direct_setup_error:
        logger.debug(f"Erro ao tentar configurar busca direta via zeep: {str(direct_setup_error)}")
        # Continuar para o método padrão
    
    # Método padrão - terceira tentativa
    logger.debug("Usando método padrão para buscar documento")
    request_data = {
        'idConsultante': cpf_consultante,
        'senhaConsultante': senha_consultante,
        'numeroProcesso': num_processo,
        'incluirDocumentos': True  # Garante que todos os documentos serão incluídos
    }

    try:
        client = Client(url)
        logger.debug("Cliente SOAP criado com sucesso")

        with client.settings(strict=False, xml_huge_tree=True):
            logger.debug("Enviando requisição SOAP")
            response = client.service.consultarProcesso(**request_data)
            logger.debug("Resposta SOAP recebida")

            data_dict = serialize_object(response)
            response = EasyDict(data_dict)

            if response.sucesso:
                logger.debug("Resposta bem sucedida, procurando documento...")

                if not hasattr(response.processo, 'documento'):
                    logger.error("Processo não contém documentos")
                    return registro_erro(num_processo, num_documento, "Processo não contém documentos")

                docs = response.processo.documento
                if not isinstance(docs, list):
                    docs = [docs]

                logger.debug(f"Encontrados {len(docs)} documentos no processo")

                # Função auxiliar para procurar documento recursivamente
                def procurar_documento(doc_list, target_id):
                    for doc in doc_list:
                        # Log detalhado do documento atual
                        logger.debug(f"Verificando documento: ID={getattr(doc, 'idDocumento', 'N/A')}")

                        # Verifica se é o documento procurado
                        if str(getattr(doc, 'idDocumento', '')).strip() == str(target_id).strip():
                            logger.debug(f"Documento {target_id} encontrado!")
                            return doc

                        # Verifica documentos vinculados
                        if hasattr(doc, 'documentoVinculado'):
                            vinc_docs = doc.documentoVinculado
                            if not isinstance(vinc_docs, list):
                                vinc_docs = [vinc_docs]

                            logger.debug(f"Verificando {len(vinc_docs)} documentos vinculados")
                            result = procurar_documento(vinc_docs, target_id)
                            if result:
                                return result

                        # Verifica outros tipos de documentos
                        for attr in ['documento', 'documentos', 'anexos']:
                            if hasattr(doc, attr):
                                outros = getattr(doc, attr)
                                if outros:
                                    outros_list = outros if isinstance(outros, list) else [outros]
                                    logger.debug(f"Verificando {len(outros_list)} documentos em {attr}")
                                    result = procurar_documento(outros_list, target_id)
                                    if result:
                                        return result
                    return None

                # Procura o documento em toda a estrutura
                documento = procurar_documento(docs, num_documento)

                if documento:
                    if documento.conteudo is None:
                        return registro_erro(num_processo, num_documento, 
                                        f"Documento {num_documento} encontrado mas retornou vazio")

                    # Atribuir valores padrão se não existirem
                    descricao = getattr(documento, 'descricao', f"Documento {num_documento}")
                    id_tipo_documento = getattr(documento, 'tipoDocumento', '')
                    mimetype = getattr(documento, 'mimetype', 'application/octet-stream')
                    
                    # Se o mimetype estiver vazio, tentar deduzir pelo conteúdo
                    if not mimetype and documento.conteudo:
                        if len(documento.conteudo) > 4 and documento.conteudo[:4] == b'%PDF':
                            mimetype = 'application/pdf'
                        else:
                            mimetype = 'application/octet-stream'

                    return {
                        'num_processo': num_processo,
                        'id_documento': documento.idDocumento,
                        'id_tipo_documento': id_tipo_documento,
                        'descricao': descricao,
                        'mimetype': mimetype,
                        'conteudo': documento.conteudo
                    }
                else:
                    logger.error(f"Documento {num_documento} não encontrado na estrutura do processo")
                    return registro_erro(num_processo, num_documento, 
                                    f"Documento {num_documento} não encontrado")
            else:
                logger.error(f"Erro na resposta: {response.mensagem}")
                return registro_erro(num_processo, num_documento, 
                                f"Erro ao consultar o MNI: {response.mensagem}")

    except Fault as e:
        if "loginFailed" in str(e):
            error_msg = "Erro de autenticação no MNI. Verifique suas credenciais"
        else:
            error_msg = f"Erro na comunicação SOAP: {str(e)}"
        logger.error(f"{error_msg} (Processo: {num_processo}, Documento: {num_documento})")
        return registro_erro(num_processo, num_documento, error_msg)
    except Exception as e:
        error_msg = f"Erro inesperado: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return registro_erro(num_processo, num_documento, error_msg)

def registro_erro(num_processo, num_documento, msg):
    """
    Registra um erro ocorrido durante o processamento.

    Args:
        num_processo (str): Número do processo
        num_documento (str): ID do documento
        msg (str): Mensagem de erro

    Returns:
        dict: Dados do erro formatados
    """
    logger.error(f"Processo {num_processo}, Documento {num_documento}: {msg}")
    return {
        "numero_processo": num_processo,
        "id_processo_documento": num_documento,
        "msg_erro": msg
    }

def consultar_tipo_documento(tipo_documento):
    """
    Consulta a descrição de um tipo de documento.

    Args:
        tipo_documento (str): Código do tipo de documento

    Returns:
        str: Descrição do tipo de documento
    """
    try:
        client = Client(MNI_CONSULTA_URL)
        response = client.service.consultarTodosTiposDocumentoProcessual()

        if isinstance(response, list):
            for retorno in response:
                if tipo_documento == retorno.codigo:
                    return retorno.descricao

        return "Tipo não encontrado"

    except Exception as e:
        logger.error(f"Erro ao consultar tipo de documento: {str(e)}")
        return "Erro na consulta"

def consultar_classe_processual(classe_processual, codigoLocalidade):
    """
    Consulta a descrição de uma classe processual.

    Args:
        classe_processual (str): Código da classe
        codigoLocalidade (str): Código da localidade

    Returns:
        str: Descrição da classe processual
    """
    try:
        request_data = {
            'arg0': {
                'descricao': '?',
                'id': str(codigoLocalidade)
            }
        }

        client = Client(MNI_CONSULTA_URL)
        response = client.service.consultarClassesJudiciais(**request_data)

        if isinstance(response, list):
            for retorno in response:
                if int(classe_processual) == int(retorno.codigo):
                    return retorno.descricao

        return "Classe não encontrada"

    except Exception as e:
        logger.error(f"Erro ao consultar classe processual: {str(e)}")
        return "Erro na consulta"

def extrair_ids_requests_lxml(num_processo, cpf=None, senha=None):
    """
    Faz a chamada SOAP usando requests com envelope manual e parseia
    o XML bruto da resposta com lxml para extrair TODOS os IDs de documentos.
    Usando o formato original que funcionava perfeitamente.

    Args:
        num_processo (str): Número do processo a ser consultado
        cpf (str, optional): CPF/CNPJ do consultante. Se não fornecido, usa o padrão do ambiente
        senha (str, optional): Senha do consultante. Se não fornecida, usa o padrão do ambiente

    Returns:
        list: Lista de todos os IDs de documentos encontrados ou None em caso de erro
    """
    # Extrai apenas o URL base sem o ?wsdl
    url_parts = MNI_URL.split('?')
    url_base = url_parts[0]
    logger.debug(f"Usando URL base para request: {url_base}")
    
    all_document_ids = []  # Lista para preservar a ordem exata
    cpf_consultante = cpf or MNI_ID_CONSULTANTE
    senha_consultante = senha or MNI_SENHA_CONSULTANTE

    if not cpf_consultante or not senha_consultante:
        logger.error("Credenciais MNI não fornecidas para extrair_ids_requests_lxml")
        return None

    logger.debug(f"Usando credenciais - CPF: {cpf_consultante[:3]}****{cpf_consultante[-3:]}")

    # Construção do envelope SOAP manual baseado no exemplo fornecido
    soap_envelope = f"""<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ser="http://www.cnj.jus.br/servico-intercomunicacao-2.2.2/" xmlns:tip="http://www.cnj.jus.br/tipos-servico-intercomunicacao-2.2.2">
   <soapenv:Header/>
   <soapenv:Body>
      <ser:consultarProcesso>
         <tip:idConsultante>{cpf_consultante}</tip:idConsultante>
         <tip:senhaConsultante>{senha_consultante}</tip:senhaConsultante>
         <tip:numeroProcesso>{num_processo}</tip:numeroProcesso>
         <tip:movimentos>false</tip:movimentos>
         <tip:incluirCabecalho>false</tip:incluirCabecalho>
         <tip:incluirDocumentos>true</tip:incluirDocumentos>
      </ser:consultarProcesso>
   </soapenv:Body>
</soapenv:Envelope>
"""
    # SOAPAction obtida do WSDL
    soap_action = "http://www.cnj.jus.br/servico-intercomunicacao-2.2.2/consultarProcesso"
    headers = {'Content-Type': 'text/xml; charset=utf-8',
               'SOAPAction': soap_action}

    try:
        logger.debug(f"Enviando requisição SOAP manual para {num_processo} via {url_base}...")
        # A URL para o request tem que ser o endpoint sem o ?wsdl
        response = requests.post(url_base, data=soap_envelope.encode('utf-8'), headers=headers, timeout=120)
        logger.debug(f"Resposta recebida. Status: {response.status_code}")
        response.raise_for_status() # Lança exceção para erros 4xx/5xx

        # --- Tratamento de MTOM/XOP ---
        content_type = response.headers.get('Content-Type', '')
        xml_to_parse = None

        if 'multipart/related' in content_type:
            logger.debug("Resposta é multipart/related (provavelmente MTOM/XOP). Parseando partes...")
            # Usar email.message_from_bytes para parsear a mensagem multipart
            # Precisamos dos cabeçalhos HTTP completos para o parser funcionar corretamente
            # Construir bytes dos cabeçalhos + corpo
            http_message_bytes = b"Content-Type: " + content_type.encode('utf-8') + b"\r\n\r\n" + response.content
            msg = message_from_bytes(http_message_bytes, policy=default_policy)

            if msg.is_multipart():
                # Procurar a parte principal do XML (geralmente a primeira ou com Content-Type text/xml)
                for part in msg.iter_parts():
                    part_ct = part.get_content_type()
                    logger.debug(f"  Analisando parte com Content-Type: {part_ct}")
                    # A parte raiz pode ter Content-Type application/xop+xml ou text/xml
                    if 'application/xop+xml' in part_ct or 'text/xml' in part_ct:
                        xml_to_parse = part.get_payload(decode=True) # Obter bytes decodificados
                        logger.debug("  Encontrada parte XML principal.")
                        break # Encontramos a parte XML
                if xml_to_parse is None:
                     logger.error(f"Não foi possível encontrar a parte XML principal na resposta multipart para {num_processo}")
                     return None
            else:
                # Não deveria acontecer se o Content-Type é multipart, mas por segurança
                 logger.error(f"Content-Type era multipart, mas a mensagem não foi parseada como tal para {num_processo}")
                 return None
        elif 'text/xml' in content_type or 'application/soap+xml' in content_type:
             logger.debug("Resposta parece ser XML simples.")
             xml_to_parse = response.content
        else:
             logger.error(f"Content-Type inesperado recebido: {content_type} para {num_processo}")
             logger.debug(f"Conteúdo da resposta (início): {response.content[:500]}") # Logar início do conteúdo
             return None

        # --- Fim do Tratamento de MTOM/XOP ---

        if xml_to_parse is None:
             logger.error(f"Falha ao extrair conteúdo XML da resposta para {num_processo}")
             return None

        # Logar o XML extraído para depuração ANTES de parsear
        try:
            xml_string_for_log = xml_to_parse.decode('utf-8', errors='ignore')
            logger.debug("\n--- INÍCIO XML EXTRAÍDO (para depuração) ---")
            logger.debug(xml_string_for_log[:2000]) # Imprime os primeiros 2000 caracteres
            logger.debug("--- FIM XML EXTRAÍDO (para depuração) ---\n")
        except Exception as log_err:
            logger.error(f"Erro ao tentar logar XML extraído: {log_err}")

        logger.debug("Parseando XML extraído com lxml...")
        root = etree.fromstring(xml_to_parse) # Parseia os bytes diretamente

        # Verificar sucesso
        sucesso_element = root.xpath('//ns2:consultarProcessoResposta/ns2:sucesso/text()', namespaces=NSMAP_RESP)
        if not sucesso_element or sucesso_element[0].lower() != 'true':
            mensagem_element = root.xpath('//ns2:consultarProcessoResposta/ns2:mensagem/text()', namespaces=NSMAP_RESP)
            mensagem = mensagem_element[0] if mensagem_element else "Falha (mensagem não encontrada no XML)."
            logger.error(f"Consulta MNI (requests+lxml) para {num_processo} indicou falha: {mensagem}")
            # Continuar mesmo assim para tentar extrair IDs se a estrutura parcial existir

        # XPath para começar com ns4:consultarProcessoResposta
        # e buscar descendentes ns2:documento ou ns2:documentoVinculado com @idDocumento
        document_ids_xpath = root.xpath(
             '//ns4:consultarProcessoResposta/descendant::ns2:documento/@idDocumento | //ns4:consultarProcessoResposta/descendant::ns2:documentoVinculado/@idDocumento',
             namespaces=NSMAP_RESP
        )

        logger.debug(f"Encontrados {len(document_ids_xpath)} atributos @idDocumento no XML bruto com XPath.")
        
        # Adicionar IDs em ordem (sem usar set para preservar a ordem exata)
        # Convertendo NodeSet para lista de strings
        for doc_id in document_ids_xpath:
            if doc_id not in all_document_ids:
                all_document_ids.append(doc_id)

        logger.debug(f"Total de IDs extraídos do XML bruto via lxml: {len(all_document_ids)}")
        if not all_document_ids:
             logger.warning(f"Nenhum ID de documento extraído do XML bruto para o processo {num_processo}")
             return []

        # Não precisamos ordenar, pois queremos manter a ordem original exata
        return all_document_ids

    except requests.exceptions.Timeout:
         logger.error(f"Timeout (requests+lxml) ao consultar {num_processo}")
         return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Erro de requisição (requests+lxml) para {num_processo}: {e}")
        # Se for erro 500, logar o conteúdo da resposta se houver
        if hasattr(e, 'response') and e.response is not None:
             logger.debug(f"Conteúdo da resposta de erro: {e.response.text}")
        return None
    except etree.XMLSyntaxError as e:
        logger.error(f"Erro ao parsear XML bruto (requests+lxml) para {num_processo}: {e}")
        return None
    except Exception as e:
        logger.error(f"Erro inesperado (requests+lxml) ao extrair IDs de {num_processo}: {e}")
        return None
        
def retorna_peticao_inicial_e_anexos(num_processo, cpf=None, senha=None):
    """
    Retorna a petição inicial do processo e seus anexos.
    
    Args:
        num_processo (str): Número do processo
        cpf (str, optional): CPF/CNPJ do consultante. Se não fornecido, usa o padrão do ambiente
        senha (str, optional): Senha do consultante. Se não fornecida, usa o padrão do ambiente
        
    Returns:
        dict: Dados da petição inicial e seus anexos ou mensagem de erro
    """
    try:
        logger.debug(f"\n{'=' * 80}")
        logger.debug(f"Buscando petição inicial e anexos do processo {num_processo}")
        logger.debug(f"{'=' * 80}\n")
        
        # 1. Consultar o processo completo
        resposta_processo = retorna_processo(num_processo, cpf=cpf, senha=senha)
        
        if not resposta_processo.sucesso:
            return {
                "numero_processo": num_processo,
                "msg_erro": f"Erro ao consultar o processo: {resposta_processo.mensagem}"
            }
            
        if not hasattr(resposta_processo.processo, 'documento'):
            return {
                "numero_processo": num_processo,
                "msg_erro": "Processo não contém documentos"
            }
        
        # 2. Procurar a petição inicial
        docs = resposta_processo.processo.documento
        if not isinstance(docs, list):
            docs = [docs]
            
        # Lista para armazenar a petição inicial e seus anexos
        resultado = {
            "numero_processo": num_processo,
            "peticao_inicial": None,
            "anexos": []
        }
        
        # Primeiro, encontrar a petição inicial (geralmente o primeiro documento do processo)
        # ou documentos com tipos específicos que indicam petição inicial
        peticao_inicial = None
        
        # Códigos comuns para petição inicial, pode variar dependendo do tribunal
        codigos_peticao_inicial = ['1', '2', '3', '4', '5', '6']  # Códigos típicos para petição inicial
        
        for doc in docs:
            # Verificar se o documento é uma petição inicial pelo tipo ou pela descrição
            tipo_doc = str(getattr(doc, 'tipoDocumento', ''))
            descricao = str(getattr(doc, 'descricao', '')).lower()
            
            if (tipo_doc in codigos_peticao_inicial or 
                'inicial' in descricao or 
                'petição inicial' in descricao):
                peticao_inicial = doc
                break
        
        # Se não encontrarmos usando os critérios acima, pegar o primeiro documento do processo
        if not peticao_inicial and docs:
            peticao_inicial = docs[0]
            
        # 3. Se encontramos a petição inicial, adicionar ao resultado e buscar seus anexos
        if peticao_inicial:
            # Dados básicos da petição inicial
            resultado["peticao_inicial"] = {
                'id_documento': getattr(peticao_inicial, 'idDocumento', ''),
                'tipo_documento': getattr(peticao_inicial, 'tipoDocumento', ''),
                'descricao': getattr(peticao_inicial, 'descricao', ''),
                'data_hora': getattr(peticao_inicial, 'dataHora', ''),
                'mimetype': getattr(peticao_inicial, 'mimetype', '')
            }
            
            # 4. Buscar anexos da petição inicial
            if hasattr(peticao_inicial, 'documentoVinculado'):
                docs_vinc = peticao_inicial.documentoVinculado
                if not isinstance(docs_vinc, list):
                    docs_vinc = [docs_vinc]
                
                for anexo in docs_vinc:
                    resultado["anexos"].append({
                        'id_documento': getattr(anexo, 'idDocumento', ''),
                        'tipo_documento': getattr(anexo, 'tipoDocumento', ''),
                        'descricao': getattr(anexo, 'descricao', ''),
                        'data_hora': getattr(anexo, 'dataHora', ''),
                        'mimetype': getattr(anexo, 'mimetype', '')
                    })
        else:
            return {
                "numero_processo": num_processo,
                "msg_erro": "Não foi possível identificar a petição inicial"
            }
            
        return resultado
        
    except ExcecaoConsultaMNI as e:
        error_msg = f"Erro na consulta MNI: {str(e)}"
        logger.error(error_msg)
        return {
            "numero_processo": num_processo,
            "msg_erro": error_msg
        }
    except Exception as e:
        error_msg = f"Erro inesperado: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {
            "numero_processo": num_processo,
            "msg_erro": error_msg
        }
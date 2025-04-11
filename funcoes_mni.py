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
from rate_limiter import mni_rate_limiter

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

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
    
    # Verificar limite de taxa para este CPF consultante
    if not mni_rate_limiter.can_make_request(cpf_consultante):
        wait_time = mni_rate_limiter.get_wait_time(cpf_consultante)
        error_msg = f"Limite de requisições excedido para o consultante {cpf_consultante}. Aguarde {int(wait_time)} segundos antes de tentar novamente."
        logger.warning(error_msg)
        raise ExcecaoConsultaMNI(error_msg)

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
    
    # Verificar limite de taxa para este CPF consultante
    if not mni_rate_limiter.can_make_request(cpf_consultante):
        wait_time = mni_rate_limiter.get_wait_time(cpf_consultante)
        error_msg = f"Limite de requisições excedido para o consultante {cpf_consultante}. Aguarde {int(wait_time)} segundos antes de tentar novamente."
        logger.warning(error_msg)
        return registro_erro(num_processo, num_documento, error_msg)

    request_data = {
        'idConsultante': cpf_consultante,
        'senhaConsultante': senha_consultante,
        'numeroProcesso': num_processo,
        'documento': num_documento,
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
                        if str(getattr(doc, 'idDocumento', '')) == str(target_id):
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

                    return {
                        'num_processo': num_processo,
                        'id_documento': documento.idDocumento,
                        'id_tipo_documento': documento.tipoDocumento,
                        'mimetype': documento.mimetype,
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
        
        cpf_consultante = cpf or MNI_ID_CONSULTANTE
        
        # Verificar limite de taxa para este CPF consultante para esta operação específica
        # (embora internamente a função retorna_processo já verifique o rate limit novamente)
        if not mni_rate_limiter.can_make_request(cpf_consultante):
            wait_time = mni_rate_limiter.get_wait_time(cpf_consultante)
            error_msg = f"Limite de requisições excedido para o consultante {cpf_consultante}. Aguarde {int(wait_time)} segundos antes de tentar novamente."
            logger.warning(error_msg)
            return {
                "numero_processo": num_processo,
                "msg_erro": error_msg
            }
            
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
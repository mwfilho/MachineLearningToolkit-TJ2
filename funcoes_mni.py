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

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def retorna_processo(num_processo):
    """
    Consulta um processo judicial via MNI.

    Args:
        num_processo (str): Número do processo no formato CNJ

    Returns:
        EasyDict: Dados do processo consultado
    """
    url = MNI_URL

    request_data = {
        'idConsultante': MNI_ID_CONSULTANTE,
        'senhaConsultante': MNI_SENHA_CONSULTANTE,
        'numeroProcesso': num_processo,
        'movimentos': True,
        'incluirCabecalho': True,
        'incluirDocumentos': True
    }

    try:
        client = Client(url)
        logger.debug(f"Consultando processo: {num_processo}")

        with client.settings(strict=False, xml_huge_tree=True):
            response = client.service.consultarProcesso(**request_data)
            data_dict = serialize_object(response)
            response = EasyDict(data_dict)

        if response.sucesso:
            if hasattr(response.processo, 'documento'):
                logger.debug(f"Processo encontrado. Número de documentos: {len(response.processo.documento)}")
                for doc in response.processo.documento:
                    logger.debug(f"Documento encontrado: ID={getattr(doc, 'idDocumento', 'N/A')}, "
                               f"Tipo={getattr(doc, 'tipoDocumento', 'N/A')}, "
                               f"Nome={getattr(doc, 'nome', 'N/A')}")
            return response
        else:
            logger.error(f"Erro na consulta do processo {num_processo}: {response.mensagem}")
            raise ExcecaoConsultaMNI(response.mensagem)

    except Fault as e:
        logger.error(f"Erro SOAP na consulta do processo {num_processo}: {str(e)}")
        raise ExcecaoConsultaMNI(f"Erro na comunicação SOAP: {str(e)}")
    except Exception as e:
        logger.error(f"Erro inesperado na consulta do processo {num_processo}: {str(e)}")
        raise ExcecaoConsultaMNI(f"Erro inesperado: {str(e)}")

def retorna_documento_processo(num_processo, num_documento):
    """
    Retorna um documento específico de um processo.
    
    Args:
        num_processo (str): Número do processo
        num_documento (str): ID do documento
        
    Returns:
        dict: Dados do documento incluindo seu conteúdo
    """
    url = MNI_URL
    
    request_data = {
        'idConsultante': MNI_ID_CONSULTANTE,
        'senhaConsultante': MNI_SENHA_CONSULTANTE,
        'numeroProcesso': num_processo,
        'documento': num_documento
    }

    try:
        client = Client(url)
        
        with client.settings(strict=False, xml_huge_tree=True):
            response = client.service.consultarProcesso(**request_data)
            data_dict = serialize_object(response)
            response = EasyDict(data_dict)
            
        if response.sucesso:
            for documento in response.processo.documento:
                if int(documento.idDocumento) == int(num_documento):
                    if documento.conteudo is None:
                        return registro_erro(num_processo, num_documento, 
                                          f"Documento {num_documento} retornou vazio")
                                          
                    return {
                        'num_processo': num_processo,
                        'id_documento': documento.idDocumento,
                        'id_tipo_documento': documento.tipoDocumento,
                        'mimetype': documento.mimetype,
                        'conteudo': documento.conteudo
                    }
                    
            return registro_erro(num_processo, num_documento, 
                               f"Documento {num_documento} não encontrado")
        else:
            return registro_erro(num_processo, num_documento, 
                               f"Erro ao consultar o MNI: {response.mensagem}")
                               
    except Exception as e:
        logger.error(f"Erro ao consultar documento {num_documento}: {str(e)}")
        return registro_erro(num_processo, num_documento, str(e))

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
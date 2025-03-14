import json
import os
import sys
import time
import requests
from zeep import Client
from zeep.helpers import serialize_object
from easydict import EasyDict
from config import MNI_URL, MNI_SENHA_CONSULTANTE, MNI_CONSULTA_URL, MNI_ID_CONSULTANTE
from controle.logger import Logs
import pandas as pd
import controle.exceptions as exceptions
import itertools

import base64
from concurrent.futures import ThreadPoolExecutor
import concurrent.futures
from configparser import ConfigParser
from datetime import datetime

from zeep.exceptions import Fault

from datetime import date

logs = Logs(filename=f'logs/log-{date.today().strftime("%Y-%m-%d")}.log')


def retorna_processo(num_processo):

    # Defina sua URL do WSDL
    url = MNI_URL

    # Defina os parâmetros de solicitação
    request_data = {
        'idConsultante': MNI_ID_CONSULTANTE,
        'senhaConsultante': MNI_SENHA_CONSULTANTE,
        'numeroProcesso': num_processo,  # ou outro número do processo
        # Caso necessário, descomente as opções abaixo:
        'movimentos': True,  
        # 'incluirCabecalho': True,  
        'incluirDocumentos': True,  
        # 'documento': num_documento  # Se você precisar incluir um documento específico
    }

    # Criação do cliente Zeep
    client = Client(url)

    # Realizando a consulta dentro de um bloco try-except
    response = None
    try:
        with client.settings(strict=False, xml_huge_tree=True):
            # Realiza a chamada ao método SOAP "consultarProcesso"
            response = client.service.consultarProcesso(**request_data)
            
            # Serializa a resposta para um formato de dicionário
            data_dict = serialize_object(response)  # Caso a função serialize_object esteja disponível em seu código.
            
            # Converte para um EasyDict para manipulação mais fácil
            response = EasyDict(data_dict)
        
        # Verifica se a consulta foi bem-sucedida
        if response.sucesso:
            return response
        else:
            print(f"Erro na consulta: {response.mensagem}")

    except Fault as e:
        print(f"Erro na requisição SOAP: {e}")
    except Exception as e:
        print(f"Erro inesperado: {e}")


def retorna_documento_processo(num_processo, num_documento):


   """
      Função que retorna os dados do Acórdao relacionado ao processo, gerando toda estrutura que será posteriormente utilizada para a carga no elastic. Apenas a Ementa não é extraída aqui por estrategia de desempenho,
      deixando para após depois que todos os documentos do bloco tenham sido recuperados, extrair a ementa passando uma lista de textos.

      :param num_processo: Número de processo a ser consultado.
      :param num_documento: Número do documento que será retornado na consulta SOAP para montagem da estrutura de dados.
      :return: Estrutura de dados que posteriormente será utilizada para a carga, com a pendência de extração da Ementa no próximo passo.
      :author: Matheus Costa Barbosa - Analista de Sistemas - TJ/CE
   """
   # URL do serviço SOAP
   url = MNI_URL
   
   # Criação do objeto de solicitação
   request_data = {
      'idConsultante': MNI_ID_CONSULTANTE,
      'senhaConsultante': MNI_SENHA_CONSULTANTE,
      'numeroProcesso': num_processo,
      # 'movimentos': 'true',
      # 'incluirCabecalho': 'true',
      # 'incluirDocumentos': 'true',
      'documento': num_documento
   }

   # Criar uma instância do cliente Zeep
   client = Client(url)
   response=None

   with client.settings(strict=False, xml_huge_tree=True):
            response = client.service.consultarProcesso(**request_data)
            data_dict = serialize_object(response)
            response = EasyDict(data_dict)
    
   if response.sucesso:
      
      for documento in response.processo.documento:
         if int(documento.idDocumento) == int(num_documento):
               if documento.conteudo is None:
                  return registro_erro(num_processo, num_documento, f"Processo {num_processo} Documento {num_documento} documento retornou vazio")
               doc = None
               try:
                  doc = documento.conteudo.decode('utf-8')
               except:
                  doc = documento.conteudo

               return  {
                              'num_processo': num_processo, #.replace(".", "").replace("-", ""),  
                              'id_documento': documento.idDocumento,
                              'id_tipo_documento': documento.tipoDocumento,
                              'mimetype': documento.mimetype,
                              'conteudo': documento.conteudo 
                           }  
      return registro_erro(num_processo, num_documento, f"Processo {num_processo} Documento {num_documento} iddocumento não encontrado")
   else:
      return registro_erro(num_processo, num_documento, f"Processo {num_processo} Documento {num_documento} erro ao consultar o MNI:{response.mensagem}")


################################# FUNÇÕES DE APOIO #################################################################
def registro_erro(num_processo, num_documento, msg):
   return {"numero_processo": num_processo, 
           "id_processo_documento": num_documento, 
           "msg_erro": msg}

def consultar_tipo_documento(tipo_documento):
   """
    Função que retorna o tipo de documento de acordo com o código de tipo do MNI

    :param tipo_documento: Código do tipo de documento.
    :return: Descrição do tipo de documento
    :author: Matheus Costa Barbosa - Analista de Sistemas - TJ/CE
    """
   # URL do serviço SOAP
   url = MNI_CONSULTA_URL

   # Criar uma instância do cliente Zeep
   client = Client(url)

   # Chamar o método do serviço SOAP
   response = client.service.consultarTodosTiposDocumentoProcessual()

   #retornos = response['return']
   # Verificar se há apenas um retorno ou vários retornos
   if isinstance(response, list):
      for retorno in response:
         if tipo_documento == retorno.codigo:
            return retorno.descricao

def consultar_classe_processual(classe_processual, codigoLocalidade):
   """
    Função que retorna a classe processual relacionada ao processo. 
    Necessário passar o código da Localidade (jurisdição) para de acordo com ele, buscar o código da classe processual.

    :param classe_processual: Código da classe processual.
    :param codigoLocalidade: Código da localidade do Processo. (jurisdição)
    :return: Descrição da classe processual.
    :author: Matheus Costa Barbosa - Analista de Sistemas - TJ/CE
    """

   # URL do serviço SOAP
   url = MNI_CONSULTA_URL

   # Construir o objeto de entrada da consulta
   request_data = {
      'arg0': {
         'descricao': '?',
         'id': str(codigoLocalidade)
      }
   }
   # Criar uma instância do cliente Zeep
   client = Client(url)

   # Chamar o método do serviço SOAP
   response = client.service.consultarClassesJudiciais(**request_data)

   # Verificar se há apenas um retorno ou vários retornos
   if isinstance(response, list):
      for retorno in response:
         if int(classe_processual) == int(retorno.codigo):
            return retorno.descricao

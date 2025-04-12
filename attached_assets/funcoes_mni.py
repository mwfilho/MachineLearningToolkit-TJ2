import json
import os
import sys
import time
import requests
from zeep import Client, Settings
import requests
from lxml import etree # Para parsear o XML bruto
from email import message_from_bytes # Para parsear multipart/MTOM
from email.policy import default as default_policy # Política para parsing
from zeep import Client # Mantido apenas para retorna_documento_processo
from zeep.helpers import serialize_object # Mantido para retorna_documento_processo
from easydict import EasyDict # Mantido para retorna_documento_processo
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

# Removido: from zeep.exceptions import Fault
import controle.exceptions as exceptions
import itertools
import base64
from concurrent.futures import ThreadPoolExecutor
import concurrent.futures
from configparser import ConfigParser
from datetime import datetime
from datetime import date

logs = Logs(filename=f'logs/log-{date.today().strftime("%Y-%m-%d")}.log')

# Namespaces definidos no WSDL e no exemplo de requisição
NSMAP_REQ = {
    'soapenv': 'http://schemas.xmlsoap.org/soap/envelope/',
    'ser': 'http://www.cnj.jus.br/servico-intercomunicacao-2.2.2/',
    'tip': 'http://www.cnj.jus.br/tipos-servico-intercomunicacao-2.2.2'
}
# Namespaces esperados na resposta (CORRIGIDO com ns2 e ns4)
NSMAP_RESP = {
    'ns2': 'http://www.cnj.jus.br/intercomunicacao-2.2.2',
    'ns4': 'http://www.cnj.jus.br/servico-intercomunicacao-2.2.2/'
    # O namespace default não precisa ser mapeado explicitamente para este XPath
}


def extrair_ids_requests_lxml(num_processo):
    """
    Faz a chamada SOAP usando requests com envelope manual e parseia
    o XML bruto da resposta com lxml para extrair TODOS os IDs de documentos.

    :param num_processo: Número do processo a ser consultado.
    :return: Lista de todos os IDs de documentos encontrados ou None em caso de erro.
    :author: Cline (adaptado por IA)
    """
    url = MNI_URL
    all_document_ids = set()

    # Construção do envelope SOAP manual baseado no exemplo fornecido
    soap_envelope = f"""<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ser="http://www.cnj.jus.br/servico-intercomunicacao-2.2.2/" xmlns:tip="http://www.cnj.jus.br/tipos-servico-intercomunicacao-2.2.2">
   <soapenv:Header/>
   <soapenv:Body>
      <ser:consultarProcesso>
         <tip:idConsultante>{MNI_ID_CONSULTANTE}</tip:idConsultante>
         <tip:senhaConsultante>{MNI_SENHA_CONSULTANTE}</tip:senhaConsultante>
         <tip:numeroProcesso>{num_processo}</tip:numeroProcesso>
         <tip:movimentos>false</tip:movimentos>
         <tip:incluirCabecalho>false</tip:incluirCabecalho>
         <tip:incluirDocumentos>true</tip:incluirDocumentos>
         <!-- <tip:dataReferencia>?</tip:dataReferencia> -->
         <!-- <tip:documento>?</tip:documento> -->
      </ser:consultarProcesso>
   </soapenv:Body>
</soapenv:Envelope>
"""
    # SOAPAction obtida do WSDL
    soap_action = "http://www.cnj.jus.br/servico-intercomunicacao-2.2.2/consultarProcesso"
    headers = {'Content-Type': 'text/xml; charset=utf-8',
               'SOAPAction': soap_action}

    try:
        print(f"Enviando requisição SOAP manual para {num_processo}...")
        response = requests.post(url, data=soap_envelope.encode('utf-8'), headers=headers, timeout=120)
        print(f"Resposta recebida. Status: {response.status_code}")
        response.raise_for_status() # Lança exceção para erros 4xx/5xx

        # --- Tratamento de MTOM/XOP ---
        content_type = response.headers.get('Content-Type', '')
        xml_to_parse = None

        if 'multipart/related' in content_type:
            print("Resposta é multipart/related (provavelmente MTOM/XOP). Parseando partes...")
            # Usar email.message_from_bytes para parsear a mensagem multipart
            # Precisamos dos cabeçalhos HTTP completos para o parser funcionar corretamente
            # Construir bytes dos cabeçalhos + corpo
            http_message_bytes = b"Content-Type: " + content_type.encode('utf-8') + b"\r\n\r\n" + response.content
            msg = message_from_bytes(http_message_bytes, policy=default_policy)

            if msg.is_multipart():
                # Procurar a parte principal do XML (geralmente a primeira ou com Content-Type text/xml)
                for part in msg.iter_parts():
                    part_ct = part.get_content_type()
                    print(f"  Analisando parte com Content-Type: {part_ct}")
                    # A parte raiz pode ter Content-Type application/xop+xml ou text/xml
                    if 'application/xop+xml' in part_ct or 'text/xml' in part_ct:
                        xml_to_parse = part.get_payload(decode=True) # Obter bytes decodificados
                        print("  Encontrada parte XML principal.")
                        break # Encontramos a parte XML
                if xml_to_parse is None:
                     logs.record(f"Não foi possível encontrar a parte XML principal na resposta multipart para {num_processo}", type='error', colorize=True)
                     return None
            else:
                # Não deveria acontecer se o Content-Type é multipart, mas por segurança
                 logs.record(f"Content-Type era multipart, mas a mensagem não foi parseada como tal para {num_processo}", type='error', colorize=True)
                 return None
        elif 'text/xml' in content_type or 'application/soap+xml' in content_type:
             print("Resposta parece ser XML simples.")
             xml_to_parse = response.content
        else:
             logs.record(f"Content-Type inesperado recebido: {content_type} para {num_processo}", type='error', colorize=True)
             logs.record(f"Conteúdo da resposta (início): {response.content[:500]}", type='debug') # Logar início do conteúdo
             return None

        # --- Fim do Tratamento de MTOM/XOP ---

        if xml_to_parse is None:
             logs.record(f"Falha ao extrair conteúdo XML da resposta para {num_processo}", type='error', colorize=True)
             return None

        # Logar o XML extraído para depuração ANTES de parsear
        try:
            xml_string_for_log = xml_to_parse.decode('utf-8', errors='ignore')
            print("\n--- INÍCIO XML EXTRAÍDO (para depuração) ---")
            print(xml_string_for_log[:2000]) # Imprime os primeiros 2000 caracteres
            print("--- FIM XML EXTRAÍDO (para depuração) ---\n")
            # Opcional: Salvar em arquivo para análise completa
            # with open(f"debug_extracted_{num_processo}.xml", "w", encoding='utf-8') as f_debug:
            #     f_debug.write(xml_string_for_log)
        except Exception as log_err:
            print(f"Erro ao tentar logar XML extraído: {log_err}")


        print("Parseando XML extraído com lxml...")
        root = etree.fromstring(xml_to_parse) # Parseia os bytes diretamente

        # Verificar sucesso (continua igual)
        sucesso_element = root.xpath('//ns2:consultarProcessoResposta/ns2:sucesso/text()', namespaces=NSMAP_RESP)
        if not sucesso_element or sucesso_element[0].lower() != 'true':
            mensagem_element = root.xpath('//ns2:consultarProcessoResposta/ns2:mensagem/text()', namespaces=NSMAP_RESP)
            mensagem = mensagem_element[0] if mensagem_element else "Falha (mensagem não encontrada no XML)."
            logs.record(f"Consulta MNI (requests+lxml) para {num_processo} indicou falha: {mensagem}", type='error', colorize=True)
            # Continuar mesmo assim para tentar extrair IDs se a estrutura parcial existir

        # XPath CORRIGIDO para começar com ns4:consultarProcessoResposta
        # e buscar descendentes ns2:documento ou ns2:documentoVinculado com @idDocumento
        document_ids_xpath = root.xpath(
             '//ns4:consultarProcessoResposta/descendant::ns2:documento/@idDocumento | //ns4:consultarProcessoResposta/descendant::ns2:documentoVinculado/@idDocumento',
             namespaces=NSMAP_RESP
        )

        print(f"Encontrados {len(document_ids_xpath)} atributos @idDocumento no XML bruto com XPath corrigido.")
        all_document_ids.update(document_ids_xpath) # Adiciona todos os IDs encontrados ao set

        print(f"Total de IDs únicos extraídos do XML bruto via lxml: {len(all_document_ids)}")
        if not all_document_ids:
             logs.record(f"Nenhum ID de documento extraído do XML bruto para o processo {num_processo}", type='warning', colorize=True)
             return []

        return sorted(list(all_document_ids))

    except requests.exceptions.Timeout:
         logs.record(f"Timeout (requests+lxml) ao consultar {num_processo}", type='error', colorize=True)
         return None
    except requests.exceptions.RequestException as e:
        logs.record(f"Erro de requisição (requests+lxml) para {num_processo}: {e}", type='error', colorize=True)
        # Se for erro 500, logar o conteúdo da resposta se houver
        if hasattr(e, 'response') and e.response is not None:
             logs.record(f"Conteúdo da resposta de erro: {e.response.text}", type='debug')
        return None
    except etree.XMLSyntaxError as e:
        logs.record(f"Erro ao parsear XML bruto (requests+lxml) para {num_processo}: {e}", type='error', colorize=True)
        # with open(f"error_raw_{num_processo}.xml", "wb") as f:
        #     f.write(raw_xml_content)
        return None
    except Exception as e:
        logs.record(f"Erro inesperado (requests+lxml) ao extrair IDs de {num_processo}: {e}", type='error', colorize=True)
        return None


# Função mantida como está, pois busca documentos individuais pelo ID e usa Zeep
def retorna_documento_processo(num_processo, num_documento):
    """
    Faz a chamada SOAP usando Zeep e navega na estrutura do objeto de resposta
    para extrair TODOS os IDs de documentos (principais e vinculados).

    :param num_processo: Número do processo a ser consultado.
    :return: Lista de todos os IDs de documentos encontrados ou None em caso de erro.
    :author: Cline (adaptado por IA)
    """
    url = MNI_URL
    all_document_ids = set()

    # Defina os parâmetros de solicitação para Zeep
    request_data = {
        'idConsultante': MNI_ID_CONSULTANTE,
        'senhaConsultante': MNI_SENHA_CONSULTANTE,
        'numeroProcesso': num_processo,
        'incluirDocumentos': True, # Crucial para obter a estrutura completa
        # 'movimentos': False, # Opcional: pode simplificar a resposta
        # 'incluirCabecalho': False # Opcional: pode simplificar a resposta
    }

    try:
        print(f"Consultando estrutura do processo {num_processo} via Zeep...")
        client = Client(url)
        with client.settings(strict=False, xml_huge_tree=True):
            # Realiza a chamada ao método SOAP "consultarProcesso"
            response = client.service.consultarProcesso(**request_data)

        # Verifica se a consulta foi bem-sucedida diretamente no objeto Zeep
        if not response or not response.sucesso:
            mensagem = response.mensagem if response and hasattr(response, 'mensagem') else "Resposta inválida ou falha na consulta."
            logs.record(f"Consulta MNI (Zeep) para {num_processo} falhou: {mensagem}", type='error', colorize=True)
            return None

        print("Resposta Zeep recebida. Navegando na estrutura do objeto...")
        # Navega na estrutura do objeto Zeep para encontrar os documentos
        if hasattr(response, 'processo') and hasattr(response.processo, 'documento'):
            documentos_principais = response.processo.documento
            # Garante que seja uma lista, mesmo se houver apenas um documento
            if not isinstance(documentos_principais, list):
                documentos_principais = [documentos_principais] if documentos_principais else []

            print(f"Encontrados {len(documentos_principais)} objeto(s) de documento principal.")

            for doc in documentos_principais:
                if hasattr(doc, 'idDocumento') and doc.idDocumento:
                    all_document_ids.add(doc.idDocumento)
                    # print(f"  ID Principal: {doc.idDocumento}")

                    # Verifica e processa documentos vinculados DENTRO deste doc
                    if hasattr(doc, 'documentoVinculado') and doc.documentoVinculado:
                        documentos_vinculados = doc.documentoVinculado
                        # Garante que seja uma lista
                        if not isinstance(documentos_vinculados, list):
                            documentos_vinculados = [documentos_vinculados]

                        # print(f"    Encontrados {len(documentos_vinculados)} objeto(s) de documento vinculado.")
                        for vinc in documentos_vinculados:
                             if hasattr(vinc, 'idDocumento') and vinc.idDocumento:
                                all_document_ids.add(vinc.idDocumento)
                                # print(f"      ID Vinculado: {vinc.idDocumento}")
                else:
                     logs.record(f"Objeto de documento principal sem idDocumento encontrado no processo {num_processo}", type='warning', colorize=True)

        else:
            logs.record(f"Estrutura 'processo.documento' não encontrada na resposta Zeep para {num_processo}", type='warning', colorize=True)


        print(f"Total de IDs únicos extraídos via navegação Zeep: {len(all_document_ids)}")
        if not all_document_ids:
             logs.record(f"Nenhum ID de documento extraído para o processo {num_processo}", type='warning', colorize=True)
             return [] # Retorna lista vazia se nenhum ID foi encontrado

        return sorted(list(all_document_ids)) # Retorna lista ordenada

    except Fault as e:
        # Erro específico do SOAP
        logs.record(f"Erro SOAP (Zeep) ao consultar {num_processo}: {e.message} | Code: {e.code}", type='error', colorize=True)
        return None
    except requests.exceptions.RequestException as e:
        # Erro de conexão/HTTP que Zeep pode encapsular
        logs.record(f"Erro de requisição (Zeep) para {num_processo}: {e}", type='error', colorize=True)
        return None
    except Exception as e:
        # Outros erros inesperados
        logs.record(f"Erro inesperado (Zeep) ao extrair IDs de {num_processo}: {e}", type='error', colorize=True)
        return None


# Função mantida como está, pois busca documentos individuais pelo ID
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

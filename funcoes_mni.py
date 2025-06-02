import os
import json
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
from datetime import datetime, date

logger = logging.getLogger(__name__)


def retorna_processo(numero_processo, cpf=None, senha=None, cache=True, timeout=60):
    """
    Retorna o dicionário bruto do processo MNI (consultarProcesso).
    Usa Zeep para chamada SOAP e parse via serialize_object ou xmltodict.
    Parâmetros:
      - numero_processo: str, número no formato 'NNNNNNN-NN.AAAA.8.XX.YYYY'
      - cpf: opcional, CPF do consultante. Se None, pega de MNI_ID_CONSULTANTE.
      - senha: opcional, Senha do consultante. Se None, pega de MNI_SENHA_CONSULTANTE.
      - cache: bool, se usar cache local (pandas/HDF5). Se True, tenta ler de cache antes de chamar MNI.
      - timeout: int, timeout em segundos para a chamada SOAP.
    Retorna: dicionário Python com todos os campos brutos do processo.
    """
    if not cpf:
        cpf = MNI_ID_CONSULTANTE
    if not senha:
        senha = MNI_SENHA_CONSULTANTE

    # Parte de cache com pandas/HDF
    try:
        cache_file = f'cache_{numero_processo.replace("/", "_")}.h5'
        if cache and os.path.exists(cache_file):
            df = pd.read_hdf(cache_file, key='processo')
            logger.debug(f"Carregando processo {numero_processo} do cache")
            # Converter DataFrame para dict aninhado
            return df.to_dict(orient='records')[0]
    except Exception as e:
        logger.debug(f"Falha ao ler cache: {e}")

    # Monta o client Zeep para o WSDL
    try:
        client = Client(wsdl=MNI_URL)
    except Exception as e:
        logger.exception("Falha ao criar cliente Zeep")
        raise ExcecaoConsultaMNI("Erro ao inicializar cliente SOAP")

    try:
        resposta = client.service.consultarProcesso(
            idConsultante=cpf,
            senhaConsultante=senha,
            numeroProcesso=numero_processo,
            movimentos=True,
            incluirCabecalho=True,
            incluirDocumentos=False
        )
    except Exception as e:
        logger.exception("Falha ao chamar consultarProcesso")
        raise ExcecaoConsultaMNI(f"Erro na chamada SOAP: {e}")

    # Converte o objeto Zeep para dict
    try:
        dados_brutos = serialize_object(resposta)
    except Exception as e:
        # Fallback: parse via xmltodict
        try:
            import xmltodict
            xml_envelope = client.wsdl.transport._last_received["envelope"]
            dados_brutos = xmltodict.parse(xml_envelope)
        except Exception as ex:
            logger.exception("Falha ao parsear resposta SOAP via xmltodict")
            raise ExcecaoConsultaMNI(f"Erro de parsing SOAP: {ex}")

    # Se cache ativo, salva versão em HDF
    if cache:
        try:
            df = pd.DataFrame([dados_brutos])
            df.to_hdf(cache_file, key='processo', mode='w')
        except Exception:
            logger.debug("Falha ao gravar cache local")

    return dados_brutos


def retorna_documento_processo(num_processo, id_doc, cpf=None, senha=None):
    """
    Faz a chamada SOAP consultarTeorComunicacao para obter o binário de um documento.
    Parâmetros:
      - num_processo: str, número do processo
      - id_doc: str, ID do documento
      - cpf, senha: credenciais MNI
    Retorna: bytes do PDF/documento, ou b'' em caso de erro.
    """
    if not cpf:
        cpf = MNI_ID_CONSULTANTE
    if not senha:
        senha = MNI_SENHA_CONSULTANTE

    try:
        client = Client(wsdl=MNI_CONSULTA_URL)
        resposta = client.service.consultarTeorComunicacao(
            numeroProcesso=num_processo,
            idComunicacao=id_doc,
            idConsultante=cpf,
            senhaConsultante=senha
        )
    except Exception as e:
        logger.exception("Falha ao chamar consultarTeorComunicacao")
        raise ExcecaoConsultaMNI(f"Erro na chamada SOAP de documento: {e}")

    try:
        # A resposta pode vir como MTOM. Se for, precisa converter para bytes corretamente.
        if hasattr(resposta, 'content'):
            return resposta.content
        # Caso Zeep devolva objeto binário
        return resposta
    except Exception:
        # fallback genérico
        return b""


def retorna_peticao_inicial_e_anexos(num_processo, cpf=None, senha=None):
    """
    Faz a chamada SOAP consultarPeticaoInicialComAnexos e retorna o resultado como dict.
    Parâmetros:
      - num_processo: str, número do processo
      - cpf, senha: credenciais MNI
    Retorna: dict com petição inicial + anexos (metadados).
    """
    if not cpf:
        cpf = MNI_ID_CONSULTANTE
    if not senha:
        senha = MNI_SENHA_CONSULTANTE

    try:
        client = Client(wsdl=MNI_URL)
        resposta = client.service.consultarPeticaoInicialComAnexos(
            numeroProcesso=num_processo,
            idConsultante=cpf,
            senhaConsultante=senha
        )
    except Exception as e:
        logger.exception("Falha ao chamar consultarPeticaoInicialComAnexos")
        raise ExcecaoConsultaMNI(f"Erro na chamada SOAP de petição: {e}")

    try:
        return serialize_object(resposta)
    except Exception as e:
        # Se serialize falhar, converte via xmltodict
        try:
            import xmltodict
            xml_data = client.wsdl.transport._last_received["envelope"]
            return xmltodict.parse(xml_data)
        except Exception:
            return {}


def retorna_lista_ids_documentos(num_processo, cpf=None, senha=None):
    """
    Retorna uma lista de IDs de documentos associados ao processo,
    sem baixar o conteúdo de cada um (apenas metadados).
    """
    dados_brutos = retorna_processo(num_processo, cpf, senha)
    # Supondo que extract_all_document_ids saiba iterar sobre dados_brutos
    from utils import extract_all_document_ids
    ids = extract_all_document_ids(dados_brutos)
    return ids


def retorna_capa_processo(num_processo, cpf=None, senha=None):
    """
    Retorna o binário da capa do processo (base64 ou binário) e retorna bytes.
    Usa extract_capa_processo para converter do dict bruto.
    """
    dados_brutos = retorna_processo(num_processo, cpf, senha)
    from utils import extract_capa_processo
    capa_bytes = extract_capa_processo(dados_brutos)
    return capa_bytes


def extract_mni_data(dados_brutos):
    """
    Transforma o dicionário bruto do MNI em JSON mais limpo, com:
      - numero
      - classe
      - assunto
      - valor_causa
      - partes: [{'tipo':..., 'nome':...}, ...]
      - movimentacoes: [{'data':..., 'desc':..., 'grau': ...}, ...]
    """
    try:
        root = EasyDict(dados_brutos)
        proc = root['processoDto']
    except Exception as e:
        raise ExcecaoConsultaMNI(f"Erro ao extrair dados do MNI: {e}")

    # Campos básicos
    numero = getattr(proc, 'numeroProcesso', '')
    classe = getattr(proc, 'classe', '')
    assunto = getattr(proc, 'assunto', '')
    valor_causa = getattr(proc, 'valorCausa', '')

    # Partes
    partes_raw = getattr(proc, 'partes', {}).get('parte', [])
    partes = []
    if isinstance(partes_raw, EasyDict):
        partes_raw = [partes_raw]
    for p in partes_raw:
        partes.append({
            'tipo': getattr(p, 'tipoParte', ''),
            'nome': getattr(p, 'nomeParte', '')
        })

    # Movimentações
    movs_raw = getattr(proc, 'movimentacoes', {}).get('movimentacao', [])
    movimentacoes = []
    if isinstance(movs_raw, EasyDict):
        movs_raw = [movs_raw]
    for m in movs_raw:
        desc = getattr(m, 'descricaoMovimento', '')
        grau = '-'
        texto = desc.lower()
        if 'sentença' in texto or 'sentenca' in texto:
            grau = '1º grau'
        elif 'acórdão' in texto or 'acordao' in texto:
            grau = '2º grau'
        movimentacoes.append({
            'data': getattr(m, 'dataMovimento', ''),
            'desc': desc,
            'grau': grau
        })

    return {
        'numero': numero,
        'classe': classe,
        'assunto': assunto,
        'valor_causa': valor_causa,
        'partes': partes,
        'movimentacoes': movimentacoes
    }


def debug_estrutura_documento(doc, nivel=0, prefixo=''):
    """
    Função auxiliar para debug que mapeia toda a estrutura de um documento
    """
    indent = '  ' * nivel
    logger.debug(f"{indent}{prefixo}{'=' * 40}")
    logger.debug(f"{indent}{prefixo}Analisando documento:")
    attrs_basicos = ['idDocumento', 'tipoDocumento', 'descricao', 'dataHora', 'mimetype']
    for attr in attrs_basicos:
        valor = getattr(doc, attr, 'N/A')
        logger.debug(f"{indent}{prefixo}{attr}: {valor}")

    # Percorre campos adicionais (exemplo):
    for field_name, field_value in doc.__dict__.items():
        if field_name not in attrs_basicos:
            logger.debug(f"{indent}{prefixo}{field_name}: {field_value}")

    # Se o documento tiver anexos, por ex.:
    anexos = getattr(doc, 'anexos', None)
    if anexos:
        logger.debug(f"{indent}{prefixo}--- ANEXOS ---")
        for sub in anexos:
            debug_estrutura_documento(sub, nivel=nivel+1, prefixo=prefixo + '  ')


def listar_movimentacoes(num_processo, cpf=None, senha=None):
    """
    Retorna apenas as movimentações mais recentes do processo (ex.: top 5).
    """
    dados_brutos = retorna_processo(num_processo, cpf, senha)
    resultado = extract_mni_data(dados_brutos)
    # Retorna apenas as 5 últimas movimentações
    return resultado.get('movimentacoes', [])[:5]


def obter_valor_causa(num_processo, cpf=None, senha=None):
    """
    Retorna apenas o valor da causa do processo.
    """
    dados_brutos = retorna_processo(num_processo, cpf, senha)
    resultado = extract_mni_data(dados_brutos)
    return resultado.get('valor_causa', '')


def obter_lista_partes(num_processo, cpf=None, senha=None):
    """
    Retorna apenas a lista de nomes das partes envolvidas.
    """
    dados_brutos = retorna_processo(num_processo, cpf, senha)
    resultado = extract_mni_data(dados_brutos)
    return resultado.get('partes', [])


def extrair_peticao_inicial_e_anexos_aprofundado(num_processo, cpf=None, senha=None):
    """
    Versão detalhada para identificar petição inicial e anexos (baseada no trecho fornecido).
    Retorna dict com chave 'peticao_inicial' e 'anexos'.
    """
    if not cpf:
        cpf = MNI_ID_CONSULTANTE
    if not senha:
        senha = MNI_SENHA_CONSULTANTE

    try:
        # 1. Chamar retorna_processo para obter o dicionário bruto do processo
        dados_brutos = retorna_processo(num_processo, cpf, senha)

        # 2. Obter lista de documentos brutos (geralmente em dados_brutos['processoDto']['documentos'])
        docs = []
        proc = EasyDict(dados_brutos).get('processoDto', {})
        docs_raw = proc.get('documentos', {}).get('documento', [])
        if isinstance(docs_raw, EasyDict):
            docs_raw = [docs_raw]
        for doc in docs_raw:
            docs.append(doc)

        resultado = {
            "numero_processo": num_processo,
            "peticao_inicial": {},
            "anexos": []
        }

        # 3. Encontrar a petição inicial com base em códigos ou palavras-chave
        peticao_inicial = None
        codigos_peticao_inicial = ['1', '2', '3', '4', '5', '6']

        for doc in docs:
            tipo_doc = str(getattr(doc, 'tipoDocumento', ''))
            descricao = str(getattr(doc, 'descricao', '')).lower()
            if (tipo_doc in codigos_peticao_inicial
                    or 'inicial' in descricao
                    or 'petição inicial' in descricao):
                peticao_inicial = doc
                break

        if not peticao_inicial and docs:
            peticao_inicial = docs[0]

        if peticao_inicial:
            resultado["peticao_inicial"] = {
                'id_documento': getattr(peticao_inicial, 'idDocumento', ''),
                'tipo_documento': getattr(peticao_inicial, 'tipoDocumento', ''),
                'descricao': getattr(peticao_inicial, 'descricao', ''),
                'data_hora': getattr(peticao_inicial, 'dataHora', ''),
                'mimetype': getattr(peticao_inicial, 'mimetype', '')
            }

            # 4. Buscar anexos vinculados à petição inicial
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

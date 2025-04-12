import base64
from concurrent.futures import ThreadPoolExecutor
import concurrent.futures
from configparser import ConfigParser
from datetime import datetime
import json
import os
import time
import requests
# Removido: from zeep import Client
from config import MNI_CONSULTA_URL, MNI_ID_CONSULTANTE, MNI_SENHA_CONSULTANTE, MNI_URL
from controle.logger import Logs

# Importa a função de extração de IDs via requests/lxml e a função de busca individual
from funcoes_mni import extrair_ids_requests_lxml, retorna_documento_processo
import pandas as pd
import controle.exceptions as exceptions
import re
# Removido: import xml.etree.ElementTree as ET (lxml é usado em funcoes_mni)

from datetime import date

logs = Logs(filename=f'logs/log-{date.today().strftime("%Y-%m-%d")}.log')

# Conjunto para rastrear IDs de documentos já processados e evitar duplicações
# (Ainda útil para garantir que não tentemos baixar o mesmo doc duas vezes se houver erro)
documentos_processados_com_sucesso = set()


# Dicionário de mapeamento de mimetype para extensão de arquivo
mime_to_extension = {
    'application/pdf': '.pdf',
    'image/jpeg': '.jpg',
    'image/png': '.png',
    'application/zip': '.zip',
    'text/plain': '.txt',
    'application/msword': '.doc',
    'application/vnd.ms-excel': '.xls',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': '.docx',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': '.xlsx',
    'text/html': '.html',
    # Adicione mais tipos MIME conforme necessário
}

# Função simplificada para baixar e salvar um documento
def baixar_e_salvar_documento(num_processo, id_documento):
    """
    Busca os dados de um documento pelo ID e salva o conteúdo em arquivo.

    :param num_processo: Número do processo.
    :param id_documento: ID do documento a ser baixado.
    :return: True se sucesso, False se erro.
    """
    print(f"\nProcessando ID: {id_documento}")
    
    # Evita reprocessar se já deu certo
    if id_documento in documentos_processados_com_sucesso:
        print(f"  Documento {id_documento} já processado com sucesso anteriormente. Pulando.")
        return True

    try:
        # Retornar dados do Documento - inclusive bytes do arquivo
        print(f"  Buscando conteúdo do documento: {id_documento}")
        resposta_doc = retorna_documento_processo(num_processo, id_documento)

        # Verificar se a resposta contém a chave 'msg_erro'
        if 'msg_erro' in resposta_doc:
            logs.record(f"Erro ao buscar documento {id_documento}: {resposta_doc['msg_erro']}",
                      type='error', colorize=True)
            return False # Indica falha

        # Obtém a extensão com base no mimetype
        # Usar .get com valor padrão para evitar KeyError se mimetype não existir
        extensao = mime_to_extension.get(resposta_doc.get('mimetype', ''), '.bin') # Default para .bin

        # Verifica se o conteúdo existe e não é None
        if 'conteudo' not in resposta_doc or resposta_doc['conteudo'] is None:
            logs.record(f"Conteúdo nulo ou ausente para documento {id_documento}", type='warning', colorize=True)
            # Considerar se isso deve retornar False ou True dependendo do caso de uso
            return False # Falha se o conteúdo é esperado

        # Salva o arquivo do documento
        arquivo_path = f'{id_documento}{extensao}'
        print(f"  Salvando documento: {arquivo_path}")
        with open(arquivo_path, 'wb') as f:
            f.write(resposta_doc['conteudo'])
        print(f"  Documento salvo com sucesso: {arquivo_path}")
        documentos_processados_com_sucesso.add(id_documento) # Adiciona ao set de sucesso
        return True # Indica sucesso

    except exceptions.ExcecaoConsultaMNI as e:
        # Captura exceções específicas do MNI se definidas
        logs.record(f"Exceção MNI ao processar documento {id_documento}: {str(e)}",
                    type='error', colorize=True)
        return False
    except Exception as e:
        logs.record(f"Erro inesperado ao processar documento {id_documento}: {str(e)}",
                    type='error', colorize=True)
        print(f"  EXCEÇÃO ao processar {id_documento}: {str(e)}")
        return False


# --- Fluxo Principal ---
try:
    num_processo = '3000066-83.2025.8.06.0203'
    # num_processo = 'OUTRO_NUMERO_AQUI' # Para testar outros processos

    print(f"Iniciando processamento para o processo: {num_processo}")

    # 1. Extrair TODOS os IDs de documentos usando requests + lxml
    lista_completa_ids = extrair_ids_requests_lxml(num_processo)

    if lista_completa_ids is None:
        # A função extrair_ids_requests_lxml já loga o erro
        print(f"Falha ao obter a lista de IDs para o processo {num_processo}. Encerrando.")
    elif not lista_completa_ids:
        print(f"Nenhum ID de documento encontrado para o processo {num_processo}. Encerrando.")
    else:
        print(f"\nLista completa de IDs obtida ({len(lista_completa_ids)} IDs). Iniciando download...")
        print(f"IDs a processar: {lista_completa_ids}")

        documentos_com_erro = []

        # 2. Iterar sobre a lista completa e baixar cada documento individualmente
        for doc_id in lista_completa_ids:
            sucesso = baixar_e_salvar_documento(num_processo, doc_id)
            if not sucesso:
                documentos_com_erro.append(doc_id)

        # 3. Resumo Final
        print("\n\n==== RESUMO FINAL DO PROCESSAMENTO ====")
        print(f"Processo: {num_processo}")
        total_esperado = len(lista_completa_ids)
        total_sucesso = len(documentos_processados_com_sucesso)
        total_erro = len(documentos_com_erro) # Erros já são únicos aqui

        print(f"Total de IDs encontrados na estrutura: {total_esperado}")
        print(f"Total de documentos baixados com sucesso: {total_sucesso}")
        print(f"Total de documentos com erro no download: {total_erro}")

        if total_erro > 0:
            print(f"IDs com erro: {sorted(documentos_com_erro)}")

        if total_sucesso == total_esperado and total_esperado > 0:
            print("Todos os documentos esperados foram processados com sucesso!")
        elif total_esperado > 0:
            print("Atenção: Alguns documentos não puderam ser processados. Verifique os logs e a lista de erros.")
        else:
             print("Nenhum documento encontrado ou processado.")


except Exception as e:
    # Captura qualquer outra exceção não prevista no fluxo principal
    logs.record(f"Erro fatal no script: {str(e)}", type='critical', colorize=True)
    print(f"Erro fatal no script: {str(e)}")

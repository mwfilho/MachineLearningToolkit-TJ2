import base64
from concurrent.futures import ThreadPoolExecutor
import concurrent.futures
from configparser import ConfigParser
from datetime import datetime
import json
import os
import time
import requests
from zeep import Client
from config import MNI_CONSULTA_URL, MNI_ID_CONSULTANTE, MNI_SENHA_CONSULTANTE, MNI_URL
from controle.logger import Logs

from funcoes_mni import retorna_documento_processo, retorna_processo
import pandas as pd
import controle.exceptions as exceptions
import re

from datetime import date

logs = Logs(filename=f'logs/log-{date.today().strftime("%Y-%m-%d")}.log')


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

try:  
    num_processo = '0020682-74.2019.8.06.0128'  
    # num_documento = '59898405'      

    # Consultar Dados do Processo      
    resposta = retorna_processo(num_processo)
    # Listagem dos documentos do processo
    for doc in resposta.processo.documento:
        print(doc.idDocumento)
        # # Retorno
        # {
        #     'num_processo': '',  
        #     'id_documento': '',
        #     'id_tipo_documento': '',
        #     'conteudo': b'' 
        # }  

        # Retornar dados do Documento - inclusive bytes do arquivo
        resposta = retorna_documento_processo(num_processo, doc.idDocumento)   
    
        # Imprimindo a chave conteudo só para verificar o tipo e testar o funcionamento
        # print(type(resposta['conteudo']))
        
        # Pode salvar o arquivo ou simplesmente manipular os bytes para enviar
        # Obtém a extensão com base no mimetype
        extensao = mime_to_extension.get(resposta['mimetype'], '.bin') 
        with open(f'{doc.idDocumento}.{extensao}', 'wb') as f:
            f.write(resposta['conteudo'])

    
except exceptions.ExcecaoConsultaMNI as e:
    logs.record(f"Exceção ExcecaoConsultaMNI capturada: {str(e)}", type='error', colorize=True)   
except Exception as e:          
    logs.record(f"Exceção capturada: {str(e)}", type='info', colorize=True)
    

import base64
from concurrent.futures import ThreadPoolExecutor
import concurrent.futures
from configparser import ConfigParser
from datetime import datetime, date
import json
import os
import time
import requests
from zeep import Client
from config import MNI_CONSULTA_URL, MNI_ID_CONSULTANTE, MNI_SENHA_CONSULTANTE, MNI_URL
import logging
from funcoes_mni import retorna_documento_processo, retorna_processo
import pandas as pd
from controle.exceptions import ExcecaoConsultaMNI
import re

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Dictionary mapping mimetypes to file extensions
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
}

def process_document(num_processo, doc_id):
    """
    Process a single document from a judicial process.

    Args:
        num_processo (str): Process number
        doc_id (str): Document ID

    Returns:
        dict: Document data including content and metadata
    """
    try:
        resposta = retorna_documento_processo(num_processo, doc_id)

        if 'msg_erro' in resposta:
            logger.error(f"Error processing document {doc_id}: {resposta['msg_erro']}")
            return None

        extensao = mime_to_extension.get(resposta['mimetype'], '.bin')

        return {
            'id': doc_id,
            'content': resposta['conteudo'],
            'mimetype': resposta['mimetype'],
            'extension': extensao
        }

    except ExcecaoConsultaMNI as e:
        logger.error(f"MNI Exception while processing document {doc_id}: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error while processing document {doc_id}: {str(e)}")
        return None

def validate_process_number(num_processo):
    """
    Validate process number format.

    Args:
        num_processo (str): Process number to validate

    Returns:
        bool: True if valid, False otherwise
    """
    pattern = r'^\d{7}-\d{2}\.\d{4}\.\d{1}\.\d{2}\.\d{4}$'
    return bool(re.match(pattern, num_processo))

def format_process_number(num_processo):
    """
    Format process number to CNJ standard.

    Args:
        num_processo (str): Process number to format

    Returns:
        str: Formatted process number
    """
    nums = re.sub(r'\D', '', num_processo)

    if len(nums) != 20:
        raise ValueError("Process number must have 20 digits")

    return f"{nums[:7]}-{nums[7:9]}.{nums[9:13]}.{nums[13]}.{nums[14:16]}.{nums[16:]}"
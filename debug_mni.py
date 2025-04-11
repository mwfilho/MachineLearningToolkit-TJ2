import logging
import sys
import requests
import json
from zeep import Client
from zeep.exceptions import Fault
from zeep.transports import Transport
from zeep.helpers import serialize_object
from config import MNI_URL, MNI_ID_CONSULTANTE, MNI_SENHA_CONSULTANTE
import xml.etree.ElementTree as ET
from requests.exceptions import RequestException

# Configurar logging detalhado
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

# Desabilitar logs muito verbosos do Zeep
logging.getLogger('zeep').setLevel(logging.INFO)
logging.getLogger('zeep.transports').setLevel(logging.INFO)

# Criar logger específico para o diagnóstico
logger = logging.getLogger("debug_mni")
logger.setLevel(logging.DEBUG)

def verificar_conectividade_url(url):
    """Verifica se a URL está acessível"""
    logger.info(f"Verificando conectividade com: {url}")
    try:
        # Extrair a base da URL para verificação
        base_url = url.split('?')[0]
        response = requests.get(base_url, timeout=10)
        status = response.status_code
        logger.info(f"Status da conexão: {status}")
        return status, "Conectividade OK" if 200 <= status < 400 else f"Erro: Status {status}"
    except RequestException as e:
        logger.error(f"Erro de conectividade: {str(e)}")
        return None, f"Erro de conectividade: {str(e)}"

def testar_autenticacao():
    """Testa apenas a autenticação no serviço MNI"""
    url = MNI_URL
    cpf_consultante = MNI_ID_CONSULTANTE
    senha_consultante = MNI_SENHA_CONSULTANTE

    logger.info(f"Testando autenticação MNI")
    logger.info(f"URL: {url}")
    logger.info(f"CPF/CNPJ: {cpf_consultante}")
    logger.info(f"Senha: {'*' * len(senha_consultante)}")  # Não exibir a senha real

    # Verificar conectividade primeiro
    status, msg = verificar_conectividade_url(url)
    if status is None or status >= 400:
        logger.error(f"Não foi possível conectar ao serviço MNI: {msg}")
        return False

    try:
        # Configurar transporte com timeout e outros ajustes
        session = requests.Session()
        session.timeout = 30  # Timeout maior
        transport = Transport(session=session)
        
        # Criar cliente SOAP com transporte configurado
        logger.info("Criando cliente SOAP...")
        client = Client(url, transport=transport)
        logger.info("Cliente SOAP criado com sucesso")

        # Verificar se o serviço tem o método esperado
        service_methods = [method for method in dir(client.service) if not method.startswith('_')]
        logger.info(f"Métodos disponíveis no serviço: {service_methods}")
        
        if 'consultarProcesso' not in service_methods:
            logger.error("Erro: O método 'consultarProcesso' não está disponível no serviço SOAP!")
            return False

        # Preparar dados mínimos para testar autenticação
        request_data = {
            'idConsultante': cpf_consultante,
            'senhaConsultante': senha_consultante,
            # Adicionar um número de processo válido
            'numeroProcesso': '3000066-83.2025.8.06.0203',  # Usar o mesmo processo do erro
            'incluirDocumentos': False,
            'movimentos': False,
            'incluirCabecalho': False
        }

        # Tentar fazer a consulta com as configurações ajustadas
        logger.info("Enviando requisição de autenticação...")
        with client.settings(strict=False, xml_huge_tree=True):
            try:
                response = client.service.consultarProcesso(**request_data)
                logger.info(f"Resposta recebida: {response}")
                logger.info("Autenticação bem-sucedida!")
                return True
            except Fault as soap_fault:
                logger.error(f"Erro SOAP durante a consulta: {str(soap_fault)}")
                
                # Verificar se é um erro específico de autenticação
                error_str = str(soap_fault)
                if "loginFailed" in error_str or "postAuthenticate" in error_str:
                    # Verificar se é um caso específico de senha bloqueada
                    if "bloqueada" in error_str.lower() or "bloqueado" in error_str.lower():
                        logger.error("ERRO DE AUTENTICAÇÃO: Senha bloqueada")
                        logger.error("A conta no MNI parece estar bloqueada. Entre em contato com o suporte do TJCE.")
                    else:
                        logger.error("ERRO DE AUTENTICAÇÃO: Credenciais inválidas ou serviço com problemas")
                    
                    logger.error("=== DETALHES DO ERRO ===")
                    logger.error(f"Código de erro: {getattr(soap_fault, 'code', 'N/A')}")
                    logger.error(f"Detalhes: {getattr(soap_fault, 'detail', 'N/A')}")
                    logger.error(f"Mensagem: {getattr(soap_fault, 'message', 'N/A')}")
                    
                    # Extrair mais informações do erro
                    if hasattr(soap_fault, 'detail') and soap_fault.detail is not None:
                        try:
                            detail_dict = serialize_object(soap_fault.detail)
                            logger.error(f"Detalhes serializados: {json.dumps(detail_dict, indent=2)}")
                            
                            # Tentar extrair mensagem específica relacionada ao bloqueio da senha
                            if isinstance(detail_dict, dict) and 'mensagem' in detail_dict:
                                msg = detail_dict['mensagem']
                                if isinstance(msg, str) and ('bloqueada' in msg.lower() or 'bloqueado' in msg.lower()):
                                    logger.error(f"CONFIRMADO: Senha bloqueada: {msg}")
                        except Exception as parse_err:
                            logger.error(f"Erro ao analisar detalhes do erro: {str(parse_err)}")
                return False
    
    except Fault as e:
        logger.error(f"Erro SOAP na inicialização: {str(e)}")
        return False
    
    except Exception as e:
        logger.error(f"Erro inesperado: {str(e)}", exc_info=True)
        return False

def testar_processo_alternativo():
    """Testa a consulta com um processo alternativo"""
    logger.info("Tentando consultar um processo alternativo...")
    url = MNI_URL
    cpf_consultante = MNI_ID_CONSULTANTE
    senha_consultante = MNI_SENHA_CONSULTANTE
    
    # Lista de processos para tentar
    processos_teste = [
        '0800490-75.2021.8.06.0000',  # Processo alternativo 1
        '0070337-91.2008.8.06.0001',  # Processo alternativo 2
        '0158533-64.2013.8.06.0001'   # Processo alternativo 3
    ]
    
    try:
        client = Client(url)
        
        for processo in processos_teste:
            logger.info(f"Tentando processo: {processo}")
            
            request_data = {
                'idConsultante': cpf_consultante,
                'senhaConsultante': senha_consultante,
                'numeroProcesso': processo,
                'incluirDocumentos': False
            }
            
            try:
                with client.settings(strict=False, xml_huge_tree=True):
                    response = client.service.consultarProcesso(**request_data)
                
                logger.info(f"Consulta bem-sucedida para processo {processo}!")
                return True
            except Exception as e:
                logger.error(f"Erro ao consultar processo {processo}: {str(e)}")
        
        return False
    except Exception as e:
        logger.error(f"Erro ao inicializar cliente SOAP: {str(e)}")
        return False

if __name__ == "__main__":
    logger.info("=== INICIANDO DIAGNÓSTICO MNI ===")
    logger.info("1. Testando autenticação básica...")
    sucesso = testar_autenticacao()
    
    if not sucesso:
        logger.info("2. Testando com processos alternativos...")
        sucesso_alt = testar_processo_alternativo()
        if sucesso_alt:
            logger.info("Consulta bem-sucedida com processo alternativo!")
    
    logger.info(f"=== DIAGNÓSTICO FINALIZADO: {'SUCESSO' if sucesso else 'FALHA'} ===")
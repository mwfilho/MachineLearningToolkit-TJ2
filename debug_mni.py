import logging
import sys
from zeep import Client
from zeep.exceptions import Fault
from zeep.helpers import serialize_object
from config import MNI_URL, MNI_ID_CONSULTANTE, MNI_SENHA_CONSULTANTE

# Configurar logging detalhado
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

# Habilitar logs específicos do Zeep para mensagens SOAP
logging.getLogger('zeep').setLevel(logging.DEBUG)
logging.getLogger('zeep.transports').setLevel(logging.DEBUG)

logger = logging.getLogger("debug_mni")

def testar_autenticacao():
    """Testa apenas a autenticação no serviço MNI"""
    url = MNI_URL
    cpf_consultante = MNI_ID_CONSULTANTE
    senha_consultante = MNI_SENHA_CONSULTANTE

    logger.info(f"Testando autenticação MNI")
    logger.info(f"URL: {url}")
    logger.info(f"CPF/CNPJ: {cpf_consultante}")
    logger.info(f"Senha: {'*' * len(senha_consultante)}")  # Não exibir a senha real

    try:
        # Criar cliente SOAP
        logger.info("Criando cliente SOAP...")
        client = Client(url)
        logger.info("Cliente SOAP criado com sucesso")

        # Preparar dados mínimos para testar autenticação
        request_data = {
            'idConsultante': cpf_consultante,
            'senhaConsultante': senha_consultante,
            # Adicionar um número de processo válido qualquer,
            # apenas para testar a autenticação
            'numeroProcesso': '0800490-75.2021.8.06.0000',
            'incluirDocumentos': False,
            'movimentos': False,
            'incluirCabecalho': False
        }

        # Tentar fazer a consulta com as configurações ajustadas
        logger.info("Enviando requisição de autenticação...")
        with client.settings(strict=False, xml_huge_tree=True):
            response = client.service.consultarProcesso(**request_data)
            
        logger.info(f"Resposta recebida: {response}")
        logger.info("Autenticação bem-sucedida!")
        return True
    
    except Fault as e:
        logger.error(f"Erro SOAP: {str(e)}")
        # Verificar se é um erro específico de autenticação
        if "loginFailed" in str(e) or "postAuthenticate" in str(e):
            logger.error("ERRO DE AUTENTICAÇÃO: Credenciais inválidas ou serviço com problemas")
            logger.error("Detalhes completos do erro:")
            logger.error(e)
        return False
    
    except Exception as e:
        logger.error(f"Erro inesperado: {str(e)}", exc_info=True)
        return False

if __name__ == "__main__":
    logger.info("=== INICIANDO DIAGNÓSTICO MNI ===")
    sucesso = testar_autenticacao()
    logger.info(f"=== DIAGNÓSTICO FINALIZADO: {'SUCESSO' if sucesso else 'FALHA'} ===")
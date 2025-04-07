import os
import logging
import tempfile
from funcoes_mni import retorna_processo, retorna_documento_processo
from utils import extract_mni_data
from PyPDF2 import PdfReader, PdfWriter, PdfMerger
import concurrent.futures
import routes.api as api  # Importar as funções da API
import time

# Configurar logging
logging.basicConfig(level=logging.DEBUG, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Definir o processo a testar
def test_process(num_processo):
    logger.info(f"Testando download completo para o processo: {num_processo}")
    start_time = time.time()
    
    try:
        # Simular chamada da API
        # Usar credenciais do ambiente
        cpf = os.environ.get('MNI_ID_CONSULTANTE')
        senha = os.environ.get('MNI_SENHA_CONSULTANTE')
        
        if not cpf or not senha:
            logger.error("Credenciais MNI não configuradas no ambiente.")
            return False
            
        # 1. Obter lista de documentos do processo
        logger.info("Consultando documentos do processo...")
        resposta_processo = retorna_processo(num_processo, cpf=cpf, senha=senha)
        dados = extract_mni_data(resposta_processo)
        
        if not dados.get('documentos') or len(dados.get('documentos', [])) == 0:
            logger.error("Processo não tem documentos ou não foram encontrados")
            docs_originais = dados.get('processo', {}).get('documentos', [])
            logger.debug(f"Documentos no formato original: {len(docs_originais)}")
            logger.debug(f"Documentos no formato API: {len(dados.get('documentos', []))}")
            return False
            
        # 2. Criar diretório temporário
        temp_dir = tempfile.mkdtemp()
        logger.info(f"Diretório temporário criado: {temp_dir}")
        
        # 3. Verificar quantidade de documentos
        documentos = dados['documentos']
        total_docs = len(documentos)
        logger.info(f"Encontrados {total_docs} documentos no processo")
        
        # 4. Testar download de três documentos aleatórios (ou todos, se menos que 3)
        if total_docs > 0:
            sample_size = min(3, total_docs)
            sample_indices = [0, total_docs//2, total_docs-1][:sample_size]
            sample_docs = [documentos[i] for i in sample_indices]
            
            logger.info(f"Testando download de {sample_size} documentos de amostra")
            
            success_count = 0
            for i, doc in enumerate(sample_docs):
                doc_id = doc['id']
                logger.info(f"Documento {i+1}/{sample_size}: ID {doc_id}")
                
                try:
                    resposta = retorna_documento_processo(num_processo, doc_id, cpf=cpf, senha=senha)
                    
                    if 'msg_erro' in resposta:
                        logger.error(f"Erro ao obter documento {doc_id}: {resposta['msg_erro']}")
                        continue
                        
                    mimetype = resposta.get('mimetype', '')
                    conteudo = resposta.get('conteudo', b'')
                    
                    if not conteudo:
                        logger.error(f"Documento {doc_id} sem conteúdo")
                        continue
                        
                    # Salvando o conteúdo para verificar
                    extensao = api.core.mime_to_extension.get(mimetype, '.bin')
                    arquivo_temp = os.path.join(temp_dir, f"doc_{doc_id}{extensao}")
                    
                    with open(arquivo_temp, 'wb') as f:
                        f.write(conteudo)
                        
                    success_count += 1
                    logger.info(f"Documento {doc_id} baixado com sucesso: {len(conteudo)} bytes")
                    
                except Exception as e:
                    logger.error(f"Erro ao processar documento {doc_id}: {str(e)}")
            
            success_rate = (success_count / sample_size) * 100
            logger.info(f"Taxa de sucesso: {success_rate:.1f}%")
            
            if success_count == 0:
                logger.error("Falha total no download de documentos")
                return False
            else:
                logger.info(f"Download parcial concluído com sucesso para o processo {num_processo}")
                return success_count > 0
        else:
            logger.error("Nenhum documento encontrado para o processo")
            return False
            
    except Exception as e:
        logger.error(f"Erro no teste do processo {num_processo}: {str(e)}", exc_info=True)
        return False
    finally:
        tempo_total = time.time() - start_time
        logger.info(f"Tempo total de execução: {tempo_total:.2f}s")

if __name__ == "__main__":
    # Lista de processos a testar
    processos = [
        "0020682-74.2019.8.06.0128",  # Processo do arquivo core.py que funciona
        # Adicione abaixo o número de um processo que está dando erro no download completo
    ]
    
    # Verificar se foi fornecido um segundo processo via argumento de linha de comando
    import sys
    if len(sys.argv) > 1:
        processos.append(sys.argv[1])
    else:
        print("Para testar um segundo processo, execute: python test_pdf_download.py NUMERO_DO_PROCESSO")
    
    # Testar cada processo
    for processo in processos:
        logger.info("=" * 80)
        logger.info(f"TESTANDO PROCESSO: {processo}")
        logger.info("=" * 80)
        
        success = test_process(processo)
        
        logger.info("=" * 40)
        logger.info(f"RESULTADO: {'SUCESSO' if success else 'FALHA'}")
        logger.info("=" * 40)
        logger.info("\n")
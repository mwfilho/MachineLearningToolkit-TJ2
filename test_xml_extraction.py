#!/usr/bin/env python3
import logging
import sys
from easydict import EasyDict
from utils import extract_all_document_ids

# Configurar logging
logging.basicConfig(level=logging.DEBUG, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                   stream=sys.stdout)
logger = logging.getLogger("test_extraction")

def build_mock_response():
    """
    Constrói uma resposta simulada com base no XML de exemplo fornecido.
    Simplificado para focar nos documentos problemáticos.
    """
    # Simulando estrutura semelhante à resposta MNI
    resposta = EasyDict()
    resposta.sucesso = True
    resposta.mensagem = "Processo consultado com sucesso"
    
    # Criar processo
    resposta.processo = EasyDict()
    
    # Criar documentos principais
    doc1 = EasyDict()
    doc1.idDocumento = "140722096"
    doc1.tipoDocumento = "57"
    doc1.dataHora = "20250318115603"
    doc1.mimetype = "text/html"
    doc1.nivelSigilo = "0"
    doc1.movimento = "110702979"
    doc1.hash = "f8bc42011569b0bf4dda07e274310813"
    doc1.descricao = "Petição"
    
    # Criar documento vinculado específico (ID 140722098)
    doc_vinc1 = EasyDict()
    doc_vinc1.idDocumento = "140722098"
    doc_vinc1.idDocumentoVinculado = "140722096"
    doc_vinc1.tipoDocumento = "57"
    doc_vinc1.dataHora = "20250318115604"
    doc_vinc1.mimetype = "application/pdf"
    doc_vinc1.nivelSigilo = "0"
    doc_vinc1.hash = "79a7aa16ae8a37fd033f1ca93a3efde6"
    doc_vinc1.descricao = "Pedido de Habilitação - CE - MARIA ELIENE FREIRE BRAGA"
    
    # Adicionar documentos vinculados ao documento principal
    doc1.documentoVinculado = [doc_vinc1]
    
    # Criar segundo documento principal
    doc2 = EasyDict()
    doc2.idDocumento = "138507083"
    doc2.tipoDocumento = "58"
    doc2.dataHora = "20250312162616"
    doc2.mimetype = "text/html"
    doc2.nivelSigilo = "0"
    doc2.hash = "be5cca17462c6f089b87dac077824df8"
    doc2.descricao = "Petição Inicial"
    
    # Criar documento vinculado específico (ID 138507087)
    doc_vinc2 = EasyDict()
    doc_vinc2.idDocumento = "138507087"
    doc_vinc2.idDocumentoVinculado = "138507083"
    doc_vinc2.tipoDocumento = "4050007"
    doc_vinc2.dataHora = "20250312162616"
    doc_vinc2.mimetype = "application/pdf"
    doc_vinc2.nivelSigilo = "0"
    doc_vinc2.hash = "85db6b7b1d949b6d7c2d02445153bcde"
    doc_vinc2.descricao = "PROCURAÇÃO AD JUDICIA"
    
    # Adicionar documentos vinculados ao documento principal
    doc2.documentoVinculado = [doc_vinc2]
    
    # Adicionar documentos ao processo
    resposta.processo.documento = [doc1, doc2]
    
    return resposta

def test_extract_ids():
    """
    Testa a função extract_all_document_ids para garantir que todos os IDs sejam extraídos,
    especialmente os IDs 140722098 e 138507087.
    """
    logger.info("Iniciando teste de extração de IDs de documentos")
    
    # Criar resposta simulada
    resposta = build_mock_response()
    
    # Extrair IDs
    resultado = extract_all_document_ids(resposta)
    
    # Verificar se a extração foi bem-sucedida
    if not resultado['sucesso']:
        logger.error(f"Erro na extração: {resultado['mensagem']}")
        return False
    
    # Verificar quantidade de IDs extraídos
    logger.info(f"Total de IDs extraídos: {len(resultado['documentos'])}")
    
    # Verificar IDs específicos
    ids_extraidos = [doc['idDocumento'] for doc in resultado['documentos']]
    
    # Conferir se os IDs específicos foram extraídos
    ids_verificar = ["140722096", "140722098", "138507083", "138507087"]
    for id_doc in ids_verificar:
        if id_doc in ids_extraidos:
            logger.info(f"ID {id_doc} foi encontrado corretamente")
        else:
            logger.error(f"ID {id_doc} NÃO foi encontrado!")
            return False
    
    # Listar todos os IDs extraídos
    logger.info("Lista de todos os IDs extraídos:")
    for doc in resultado['documentos']:
        logger.info(f"ID: {doc['idDocumento']}, Tipo: {doc['tipoDocumento']}, Descrição: {doc['descricao']}")
    
    logger.info("Teste concluído com sucesso! Todos os IDs foram extraídos corretamente.")
    return True

if __name__ == "__main__":
    if test_extract_ids():
        print("\n✅ TESTE BEM-SUCEDIDO: Todos os IDs foram extraídos corretamente, incluindo 140722098 e 138507087!")
    else:
        print("\n❌ TESTE FALHOU: Nem todos os IDs foram extraídos corretamente!")
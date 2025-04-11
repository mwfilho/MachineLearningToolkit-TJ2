#!/usr/bin/env python3
import logging
import sys
import json
from easydict import EasyDict
from utils import extract_all_document_ids

# Configurar logging
logging.basicConfig(level=logging.DEBUG, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                   stream=sys.stdout)
logger = logging.getLogger("test_extraction")

def create_realistic_mock_data():
    """
    Cria um mock mais realista baseado no XML real fornecido.
    """
    # Estrutura básica da resposta
    resposta = EasyDict()
    resposta.sucesso = True
    resposta.mensagem = "Processo consultado com sucesso"
    resposta.processo = EasyDict()
    
    # Documento 1 - Petição com documentos vinculados (inclui 140722098)
    doc1 = EasyDict({
        "idDocumento": "140722096",
        "tipoDocumento": "57",
        "dataHora": "20250318115603",
        "mimetype": "text/html",
        "nivelSigilo": "0",
        "movimento": "110702979",
        "hash": "f8bc42011569b0bf4dda07e274310813",
        "descricao": "Petição"
    })
    
    # Documentos vinculados do doc1
    doc1_vinc1 = EasyDict({
        "idDocumento": "140722098",  # ID específico que precisamos garantir que seja extraído
        "idDocumentoVinculado": "140722096",
        "tipoDocumento": "57",
        "dataHora": "20250318115604",
        "mimetype": "application/pdf",
        "nivelSigilo": "0",
        "hash": "79a7aa16ae8a37fd033f1ca93a3efde6",
        "descricao": "Pedido de Habilitação - CE - MARIA ELIENE FREIRE BRAGA"
    })
    
    doc1_vinc2 = EasyDict({
        "idDocumento": "140722103",
        "idDocumentoVinculado": "140722096",
        "tipoDocumento": "4050007",
        "dataHora": "20250318115604",
        "mimetype": "application/pdf",
        "nivelSigilo": "0",
        "hash": "ea254720a681045145b0d42a5dff5ca7",
        "descricao": "KIT PROCURAÇÃO DAYCOVAL ATUALIZADO - 01-12"
    })
    
    doc1_vinc3 = EasyDict({
        "idDocumento": "140722105",
        "idDocumentoVinculado": "140722096",
        "tipoDocumento": "4050007",
        "dataHora": "20250318115604",
        "mimetype": "application/pdf",
        "nivelSigilo": "0",
        "hash": "89b66f7a1e3bdbde9cf8c54b8b212743",
        "descricao": "KIT PROCURAÇÃO DAYCOVAL ATUALIZADO - 13-22"
    })
    
    doc1_vinc4 = EasyDict({
        "idDocumento": "140722107",
        "idDocumentoVinculado": "140722096",
        "tipoDocumento": "4050007",
        "dataHora": "20250318115604",
        "mimetype": "application/pdf",
        "nivelSigilo": "0",
        "hash": "ca3739b917d25efc81c84f01bfdbfcc1",
        "descricao": "KIT PROCURAÇÃO DAYCOVAL ATUALIZADO - 23-29"
    })
    
    # Associar vinculados ao doc1
    doc1.documentoVinculado = [doc1_vinc1, doc1_vinc2, doc1_vinc3, doc1_vinc4]
    
    # Documento 2 - Decisão (sem vinculados)
    doc2 = EasyDict({
        "idDocumento": "140690432",
        "tipoDocumento": "4050020",
        "dataHora": "20250318115227",
        "mimetype": "text/html",
        "nivelSigilo": "0",
        "movimento": "110702379",
        "hash": "947267e7d0b4fd9f3259bef797a0e833",
        "descricao": "Decisão"
    })
    
    # Documento 3 - Petição Inicial com documentos vinculados (inclui 138507087)
    doc3 = EasyDict({
        "idDocumento": "138507083",
        "tipoDocumento": "58",
        "dataHora": "20250312162616",
        "mimetype": "text/html",
        "nivelSigilo": "0",
        "hash": "be5cca17462c6f089b87dac077824df8",
        "descricao": "Petição Inicial"
    })
    
    # Documentos vinculados do doc3
    doc3_vinc1 = EasyDict({
        "idDocumento": "138507087",  # ID específico que precisamos garantir que seja extraído
        "idDocumentoVinculado": "138507083",
        "tipoDocumento": "4050007",
        "dataHora": "20250312162616",
        "mimetype": "application/pdf",
        "nivelSigilo": "0",
        "hash": "85db6b7b1d949b6d7c2d02445153bcde",
        "descricao": "PROCURAÇÃO AD JUDICIA"
    })
    
    doc3_vinc2 = EasyDict({
        "idDocumento": "138507089",
        "idDocumentoVinculado": "138507083",
        "tipoDocumento": "4050011",
        "dataHora": "20250312162616",
        "mimetype": "application/pdf",
        "nivelSigilo": "0",
        "hash": "75d58f490355d767782902b806c8911f",
        "descricao": "DECLARAÇÃO HIPOSSUFICIÊNCIA"
    })
    
    # Associar vinculados ao doc3
    doc3.documentoVinculado = [doc3_vinc1, doc3_vinc2]
    
    # Adicionar todos os documentos ao processo
    resposta.processo.documento = [doc1, doc2, doc3]
    
    return resposta

def test_extract_with_realistic_data():
    """
    Testa a função extract_all_document_ids com dados mais realistas.
    """
    logger.info("=== INICIANDO TESTE COM DADOS REALISTAS ===")
    
    # Criar o mock de dados realista
    resposta = create_realistic_mock_data()
    
    # Extrair os IDs
    resultado = extract_all_document_ids(resposta)
    
    # Verificar se a extração foi bem-sucedida
    if not resultado['sucesso']:
        logger.error(f"FALHA: Erro na extração: {resultado['mensagem']}")
        return False
    
    # Obter lista de IDs extraídos
    ids_extraidos = [doc['idDocumento'] for doc in resultado['documentos']]
    
    # IDs que precisamos verificar especificamente
    ids_criticos = ['140722098', '138507087']
    
    # Verificar se os IDs críticos foram extraídos
    missing_ids = []
    for id_doc in ids_criticos:
        if id_doc not in ids_extraidos:
            missing_ids.append(id_doc)
            logger.error(f"FALHA: ID crítico {id_doc} NÃO foi encontrado!")
    
    if missing_ids:
        logger.error(f"IDs ausentes: {missing_ids}")
        return False
    
    # Listar todos os IDs encontrados para referência
    logger.info(f"Total de IDs extraídos: {len(ids_extraidos)}")
    logger.info("IDs extraídos:")
    for doc in resultado['documentos']:
        logger.info(f"ID: {doc['idDocumento']}, Tipo: {doc['tipoDocumento']}, Descrição: {doc['descricao']}")
    
    # Verificar se os IDs críticos estão na lista
    for id_doc in ids_criticos:
        logger.info(f"ID crítico {id_doc} foi encontrado corretamente!")
    
    logger.info("=== TESTE CONCLUÍDO COM SUCESSO ===")
    return True

if __name__ == "__main__":
    if test_extract_with_realistic_data():
        print("\n✓ TESTE REALISTA PASSOU: Todos os IDs críticos foram extraídos corretamente!")
    else:
        print("\n✗ TESTE REALISTA FALHOU: Nem todos os IDs críticos foram extraídos!")
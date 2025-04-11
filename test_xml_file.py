#!/usr/bin/env python3
import logging
import sys
import os
import re
import tempfile
import xml.etree.ElementTree as ET
from easydict import EasyDict
from utils import extract_all_document_ids
from zeep.helpers import serialize_object

# Configurar logging
logging.basicConfig(level=logging.DEBUG, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                   stream=sys.stdout)
logger = logging.getLogger("test_xml")

def manual_extract_data(xml_string):
    """
    Extrai dados diretamente do XML usando regex quando o parsing normal falha.
    """
    logger.info("Usando extração manual via regex para o XML")
    
    # Extrair dados básicos
    resposta = EasyDict()
    resposta.sucesso = True
    resposta.mensagem = "Processo consultado com sucesso (extraído via regex)"
    resposta.processo = EasyDict()
    
    # Extrair todos os documentos e seus atributos usando regex
    docs = []
    
    # Procurar todos os documentos principais
    doc_matches = re.finditer(r'<(?:ns\d+:)?documento[^>]+idDocumento="([^"]+)"[^>]+tipoDocumento="([^"]+)"[^>]+descricao="([^"]+)"[^>]+mimetype="([^"]+)"', xml_string)
    
    for match in doc_matches:
        doc_id, doc_tipo, doc_desc, doc_mime = match.groups()
        doc = EasyDict()
        doc.idDocumento = doc_id
        doc.tipoDocumento = doc_tipo
        doc.descricao = doc_desc
        doc.mimetype = doc_mime
        
        # Buscar documentos vinculados a este documento principal
        vinc_docs = []
        vinc_pattern = r'<(?:ns\d+:)?documentoVinculado[^>]+idDocumento="([^"]+)"[^>]+idDocumentoVinculado="' + re.escape(doc_id) + r'"[^>]+tipoDocumento="([^"]+)"[^>]+descricao="([^"]+)"[^>]+mimetype="([^"]+)"'
        vinc_matches = re.finditer(vinc_pattern, xml_string)
        
        for vinc_match in vinc_matches:
            vinc_id, vinc_tipo, vinc_desc, vinc_mime = vinc_match.groups()
            vinc = EasyDict()
            vinc.idDocumento = vinc_id
            vinc.idDocumentoVinculado = doc_id
            vinc.tipoDocumento = vinc_tipo
            vinc.descricao = vinc_desc
            vinc.mimetype = vinc_mime
            vinc_docs.append(vinc)
        
        # Adicionar documentos vinculados ao documento principal
        if vinc_docs:
            doc.documentoVinculado = vinc_docs
        
        docs.append(doc)
    
    # Se encontrou documentos, adicionar à resposta
    if docs:
        resposta.processo.documento = docs
        logger.info(f"Extração manual encontrou {len(docs)} documentos principais")
        for doc in docs:
            logger.info(f"  Documento: {doc.idDocumento} ({doc.descricao})")
            if hasattr(doc, 'documentoVinculado'):
                for vinc in doc.documentoVinculado:
                    logger.info(f"    Vinculado: {vinc.idDocumento} ({vinc.descricao})")
    else:
        logger.warning("Nenhum documento encontrado via extração manual")
    
    return resposta

def parse_xml_to_easydict(xml_string):
    """
    Converte XML para uma estrutura EasyDict para simular o comportamento do Zeep.
    Esta é uma versão simplificada para testes - o Zeep faz manipulações mais complexas.
    """
    # Uma abordagem mais agressiva para remover namespaces
    # Primeiro vamos remover todas as declarações de namespace
    xml_string_clean = re.sub(r'\sxmlns(:[^=]*)?="[^"]*"', '', xml_string)
    
    # Remover todos os prefixos de tag
    xml_string_clean = re.sub(r'</[a-zA-Z0-9]+:', '</', xml_string_clean)
    xml_string_clean = re.sub(r'<([a-zA-Z0-9]+):', '<', xml_string_clean)
    
    # Remover todas as referências a namespaces
    simplified_xml = re.sub(r'<([^>]*)ns\d+:', '<\\1', xml_string_clean)
    
    # Analisar o XML em uma estrutura ElementTree
    try:
        # Uma abordagem alternativa é simplesmente extrair os dados relevantes usando regex
        root = ET.fromstring(simplified_xml)
    except ET.ParseError as e:
        logger.error(f"Erro ao analisar XML: {e}")
        logger.debug(f"XML problemático: {simplified_xml[:200]}...")
        # Vamos usar regex para extrair diretamente os IDs que precisamos
        return manual_extract_data(xml_string)
    
    # Encontrar o corpo da resposta (consultarProcessoResposta)
    response_node = None
    for elem in root.iter():
        if elem.tag.endswith('consultarProcessoResposta'):
            response_node = elem
            break
    
    if response_node is None:
        logger.error("Não foi possível encontrar o nó de resposta no XML")
        return None
    
    # Criar objeto EasyDict para a resposta
    resposta = EasyDict()
    
    # Preencher campos básicos
    for child in response_node:
        if child.tag == 'sucesso':
            resposta.sucesso = (child.text.lower() == 'true')
        elif child.tag == 'mensagem':
            resposta.mensagem = child.text
        elif child.tag == 'processo':
            processo = EasyDict()
            resposta.processo = processo
            
            # Processar documentos
            docs = []
            for elem in child.iter():
                if elem.tag == 'documento':
                    doc = EasyDict()
                    
                    # Processar atributos do documento
                    for attr_name, attr_value in elem.attrib.items():
                        doc[attr_name] = attr_value
                    
                    # Processar documentos vinculados
                    vincs = []
                    for vinc_elem in elem.findall('./documentoVinculado'):
                        vinc = EasyDict()
                        
                        # Processar atributos do documento vinculado
                        for v_attr_name, v_attr_value in vinc_elem.attrib.items():
                            vinc[v_attr_name] = v_attr_value
                        
                        vincs.append(vinc)
                    
                    if vincs:
                        doc.documentoVinculado = vincs
                    
                    docs.append(doc)
            
            if docs:
                processo.documento = docs
    
    return resposta

def test_with_xml_content(xml_content):
    """
    Testa a função extract_all_document_ids usando conteúdo XML fornecido.
    """
    logger.info("=== INICIANDO TESTE COM XML REAL ===")
    
    # Converter XML para EasyDict
    resposta = parse_xml_to_easydict(xml_content)
    
    if resposta is None:
        logger.error("Não foi possível analisar o XML")
        return False
    
    # Verificar se o parser encontrou documentos
    if not hasattr(resposta, 'processo') or not hasattr(resposta.processo, 'documento'):
        logger.error("XML não contém a estrutura esperada de documentos")
        return False
    
    # Contar número de documentos principais
    num_docs = len(resposta.processo.documento) if isinstance(resposta.processo.documento, list) else 1
    logger.info(f"Documentos principais encontrados no XML: {num_docs}")
    
    # Extrair IDs usando nossa função melhorada
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
    logger.info("IDs críticos extraídos:")
    for id_doc in ids_criticos:
        doc_info = next((doc for doc in resultado['documentos'] if doc['idDocumento'] == id_doc), None)
        if doc_info:
            logger.info(f"ID: {doc_info['idDocumento']}, Tipo: {doc_info['tipoDocumento']}, Descrição: {doc_info['descricao']}")
    
    logger.info("=== TESTE COM XML REAL CONCLUÍDO COM SUCESSO ===")
    return True

def create_test_xml_file():
    """
    Cria um arquivo XML de teste com base no exemplo fornecido.
    """
    xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
   <soap:Body>
      <ns4:consultarProcessoResposta xmlns="http://www.cnj.jus.br/tipos-servico-intercomunicacao-2.2.2" xmlns:ns2="http://www.cnj.jus.br/intercomunicacao-2.2.2" xmlns:ns3="http://www.cnj.jus.br/mni/cda" xmlns:ns4="http://www.cnj.jus.br/servico-intercomunicacao-2.2.2/">
         <sucesso>true</sucesso>
         <mensagem>Processo consultado com sucesso</mensagem>
         <processo>
            <ns2:documento idDocumento="140722096" tipoDocumento="57" dataHora="20250318115603" mimetype="text/html" nivelSigilo="0" movimento="110702979" hash="f8bc42011569b0bf4dda07e274310813" descricao="Petição">
               <ns2:documentoVinculado idDocumento="140722098" idDocumentoVinculado="140722096" tipoDocumento="57" dataHora="20250318115604" mimetype="application/pdf" nivelSigilo="0" hash="79a7aa16ae8a37fd033f1ca93a3efde6" descricao="Pedido de Habilitação - CE - MARIA ELIENE FREIRE BRAGA">
               </ns2:documentoVinculado>
               <ns2:documentoVinculado idDocumento="140722103" idDocumentoVinculado="140722096" tipoDocumento="4050007" dataHora="20250318115604" mimetype="application/pdf" nivelSigilo="0" hash="ea254720a681045145b0d42a5dff5ca7" descricao="KIT PROCURAÇÃO DAYCOVAL ATUALIZADO - 01-12">
               </ns2:documentoVinculado>
               <ns2:documentoVinculado idDocumento="140722105" idDocumentoVinculado="140722096" tipoDocumento="4050007" dataHora="20250318115604" mimetype="application/pdf" nivelSigilo="0" hash="89b66f7a1e3bdbde9cf8c54b8b212743" descricao="KIT PROCURAÇÃO DAYCOVAL ATUALIZADO - 13-22">
               </ns2:documentoVinculado>
               <ns2:documentoVinculado idDocumento="140722107" idDocumentoVinculado="140722096" tipoDocumento="4050007" dataHora="20250318115604" mimetype="application/pdf" nivelSigilo="0" hash="ca3739b917d25efc81c84f01bfdbfcc1" descricao="KIT PROCURAÇÃO DAYCOVAL ATUALIZADO - 23-29">
               </ns2:documentoVinculado>
            </ns2:documento>
            <ns2:documento idDocumento="140690432" tipoDocumento="4050020" dataHora="20250318115227" mimetype="text/html" nivelSigilo="0" movimento="110702379" hash="947267e7d0b4fd9f3259bef797a0e833" descricao="Decisão">
            </ns2:documento>
            <ns2:documento idDocumento="138507083" tipoDocumento="58" dataHora="20250312162616" mimetype="text/html" nivelSigilo="0" hash="be5cca17462c6f089b87dac077824df8" descricao="Petição Inicial">
               <ns2:documentoVinculado idDocumento="138507087" idDocumentoVinculado="138507083" tipoDocumento="4050007" dataHora="20250312162616" mimetype="application/pdf" nivelSigilo="0" hash="85db6b7b1d949b6d7c2d02445153bcde" descricao="PROCURAÇÃO AD JUDICIA">
               </ns2:documentoVinculado>
               <ns2:documentoVinculado idDocumento="138507089" idDocumentoVinculado="138507083" tipoDocumento="4050011" dataHora="20250312162616" mimetype="application/pdf" nivelSigilo="0" hash="75d58f490355d767782902b806c8911f" descricao="DECLARAÇÃO HIPOSSUFICIÊNCIA">
               </ns2:documentoVinculado>
            </ns2:documento>
         </processo>
      </ns4:consultarProcessoResposta>
   </soap:Body>
</soap:Envelope>"""
    
    # Criar arquivo temporário
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.xml')
    with open(temp_file.name, 'w') as f:
        f.write(xml_content)
    
    return temp_file.name

if __name__ == "__main__":
    try:
        # Criar arquivo XML temporário
        xml_file = create_test_xml_file()
        
        # Ler conteúdo do arquivo
        with open(xml_file, 'r') as f:
            xml_content = f.read()
        
        # Executar teste
        if test_with_xml_content(xml_content):
            print("\n✓ TESTE COM XML REAL PASSOU: Todos os IDs críticos foram extraídos corretamente!")
        else:
            print("\n✗ TESTE COM XML REAL FALHOU: Nem todos os IDs críticos foram extraídos!")
        
        # Limpar arquivo temporário
        os.unlink(xml_file)
    
    except Exception as e:
        print(f"\n✗ ERRO DURANTE O TESTE: {str(e)}")
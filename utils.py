import logging
from functools import wraps
import io
from PyPDF2 import PdfMerger
from base64 import b64decode
from datetime import datetime

# Configure logging
logger = logging.getLogger(__name__)

def extract_mni_data(resposta):
    """Extrai dados relevantes da resposta MNI de forma segura"""
    try:
        dados = {
            'sucesso': getattr(resposta, 'sucesso', False),
            'mensagem': getattr(resposta, 'mensagem', ''),
            'processo': {}
        }

        if hasattr(resposta, 'processo'):
            processo = resposta.processo
            dados['processo'] = {
                'numero': getattr(processo, 'numero', ''),
                'classeProcessual': getattr(processo, 'classeProcessual', ''),
                'dataAjuizamento': getattr(processo, 'dataAjuizamento', ''),
                'orgaoJulgador': getattr(getattr(processo, 'orgaoJulgador', {}), 'descricao', ''),
                'documentos': []
            }

            if hasattr(processo, 'documento'):
                # Dicionários para armazenar documentos
                principais = []
                vinculados = {}

                def extract_doc_info(doc):
                    """Extrai informações básicas do documento"""
                    return {
                        'idDocumento': getattr(doc, 'idDocumento', ''),
                        'tipoDocumento': getattr(doc, 'tipoDocumento', ''),
                        'descricao': getattr(doc, 'descricao', ''),
                        'dataHora': getattr(doc, 'dataHora', ''),
                        'mimetype': getattr(doc, 'mimetype', ''),
                        'nivelSigilo': getattr(doc, 'nivelSigilo', 0),
                        'movimento': getattr(doc, 'movimento', None),
                        'hash': getattr(doc, 'hash', ''),
                        'conteudo': getattr(doc, 'conteudo', None),
                        'documentos_vinculados': []
                    }

                # Processa todos os documentos do processo
                docs = processo.documento if isinstance(processo.documento, list) else [processo.documento]
                for doc in docs:
                    # Extrai informações do documento atual
                    doc_info = extract_doc_info(doc)
                    id_doc = doc_info['idDocumento']
                    logger.debug(f"\nProcessando documento: {id_doc}")

                    # 1. Verifica se é um documento vinculado (tem idDocumentoVinculado)
                    if hasattr(doc, 'idDocumentoVinculado'):
                        id_principal = getattr(doc, 'idDocumentoVinculado')
                        if id_principal:
                            if id_principal not in vinculados:
                                vinculados[id_principal] = []
                            vinculados[id_principal].append(doc_info)
                            logger.debug(f"  É vinculado ao documento: {id_principal}")
                            continue

                    # 2. Verifica se tem documentos vinculados como elementos
                    if hasattr(doc, 'documentoVinculado'):
                        docs_vinc = doc.documentoVinculado
                        if not isinstance(docs_vinc, list):
                            docs_vinc = [docs_vinc]

                        for doc_vinc in docs_vinc:
                            vinc_info = extract_doc_info(doc_vinc)
                            doc_info['documentos_vinculados'].append(vinc_info)
                            logger.debug(f"  Tem documento vinculado: {vinc_info['idDocumento']}")

                    # Se chegou aqui, é um documento principal
                    principais.append(doc_info)
                    logger.debug("  É um documento principal")

                # Adiciona os documentos vinculados aos seus principais
                for doc_info in principais:
                    id_doc = doc_info['idDocumento']
                    if id_doc in vinculados:
                        doc_info['documentos_vinculados'].extend(vinculados[id_doc])
                        logger.debug(f"Vinculando {len(vinculados[id_doc])} documentos ao {id_doc}")

                # Adiciona os documentos principais ao resultado
                dados['processo']['documentos'] = principais
                logger.debug(f"\nTotal de documentos principais: {len(principais)}")
                logger.debug(f"Total de documentos vinculados: {sum(len(v) for v in vinculados.values())}")

        return dados
    except Exception as e:
        logger.error(f"Erro ao extrair dados MNI: {str(e)}")
        return {'sucesso': False, 'mensagem': f'Erro ao processar dados: {str(e)}'}

def filter_documents(documentos, filtros=None):
    """
    Filtra documentos com base em critérios específicos.

    Args:
        documentos (list): Lista de documentos do processo
        filtros (dict): Dicionário com critérios de filtro
            - tipos_documento (list): Lista de tipos de documento a incluir
            - data_inicial (str): Data inicial formato YYYYMMDD
            - data_final (str): Data final formato YYYYMMDD
            - descricao (str): Texto a buscar na descrição
            - apenas_principais (bool): Se True, inclui apenas documentos principais
            - apenas_pdf (bool): Se True, inclui apenas documentos PDF

    Returns:
        list: Lista de documentos filtrados
    """
    if not filtros:
        return documentos

    def match_document(doc):
        """Verifica se o documento atende aos critérios"""
        # Filtra por tipo de documento
        if 'tipos_documento' in filtros and filtros['tipos_documento']:
            if doc['tipoDocumento'] not in filtros['tipos_documento']:
                return False

        # Filtra por data
        if 'data_inicial' in filtros or 'data_final' in filtros:
            doc_data = datetime.strptime(doc['dataHora'][:8], '%Y%m%d')

            if 'data_inicial' in filtros and filtros['data_inicial']:
                data_inicial = datetime.strptime(filtros['data_inicial'], '%Y%m%d')
                if doc_data < data_inicial:
                    return False

            if 'data_final' in filtros and filtros['data_final']:
                data_final = datetime.strptime(filtros['data_final'], '%Y%m%d')
                if doc_data > data_final:
                    return False

        # Filtra por descrição
        if 'descricao' in filtros and filtros['descricao']:
            if filtros['descricao'].lower() not in doc['descricao'].lower():
                return False

        # Filtra apenas PDFs
        if filtros.get('apenas_pdf', False):
            if doc.get('mimetype') != 'application/pdf':
                return False

        return True

    def filter_recursive(docs):
        """Aplica o filtro recursivamente nos documentos e seus vinculados"""
        filtered = []
        for doc in docs:
            if match_document(doc):
                # Cria uma cópia do documento para não modificar o original
                doc_filtered = doc.copy()

                # Se não é para incluir apenas documentos principais, processa vinculados
                if not filtros.get('apenas_principais', False):
                    vinculados = filter_recursive(doc.get('documentos_vinculados', []))
                    doc_filtered['documentos_vinculados'] = vinculados
                else:
                    doc_filtered['documentos_vinculados'] = []

                filtered.append(doc_filtered)

        return filtered

    # Aplica os filtros em todos os documentos
    documentos_filtrados = filter_recursive(documentos)

    # Log do resultado da filtragem
    total_docs = len(documentos)
    total_filtrados = len(documentos_filtrados)
    logger.debug(f"Filtro aplicado: {total_filtrados} documentos selecionados de {total_docs}")

    return documentos_filtrados

def merge_process_documents(documentos, filtros=None):
    """
    Mescla documentos do processo em um único PDF, aplicando filtros se especificados.

    Args:
        documentos (list): Lista de documentos do processo
        filtros (dict): Critérios de filtro para os documentos

    Returns:
        bytes: Conteúdo do PDF mesclado
    """
    # Aplica filtros se especificados
    if filtros:
        documentos = filter_documents(documentos, filtros)
        if not documentos:
            raise ValueError("Nenhum documento encontrado com os filtros especificados")

    merger = PdfMerger()

    def add_document_to_merger(doc):
        """Adiciona um documento ao merger"""
        try:
            if doc.get('conteudo') and doc.get('mimetype') == 'application/pdf':
                # Converte conteúdo base64 para bytes
                pdf_content = b64decode(doc['conteudo'])
                pdf_stream = io.BytesIO(pdf_content)

                # Adiciona ao merger
                merger.append(pdf_stream)
                logger.debug(f"Documento {doc['idDocumento']} adicionado ao PDF")

                # Processa documentos vinculados
                for doc_vinc in doc.get('documentos_vinculados', []):
                    add_document_to_merger(doc_vinc)
        except Exception as e:
            logger.error(f"Erro ao processar documento {doc.get('idDocumento')}: {str(e)}")

    try:
        # Processa todos os documentos filtrados
        for doc in documentos:
            add_document_to_merger(doc)

        # Gera o PDF final
        output = io.BytesIO()
        merger.write(output)
        merger.close()

        return output.getvalue()

    except Exception as e:
        logger.error(f"Erro ao mesclar documentos: {str(e)}")
        raise
from flask import Blueprint, jsonify, send_file, request
import os
import logging
from funcoes_mni import retorna_processo, retorna_documento_processo, retorna_peticao_inicial_e_anexos
from utils import extract_mni_data, extract_capa_processo
import core
import tempfile
import time
import io
from PyPDF2 import PdfReader, PdfWriter, PdfMerger
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
import weasyprint
import concurrent.futures

# Configure logging
logger = logging.getLogger(__name__)

# Criar o blueprint da API
api = Blueprint('api', __name__, url_prefix='/api/v1')

def get_mni_credentials():
    """Obtém credenciais do MNI dos headers ou environment"""
    cpf = request.headers.get('X-MNI-CPF') or os.environ.get('MNI_ID_CONSULTANTE')
    senha = request.headers.get('X-MNI-SENHA') or os.environ.get('MNI_SENHA_CONSULTANTE')
    return cpf, senha

@api.before_request
def log_request_info():
    """Log detalhes da requisição para debug"""
    logger.debug('Headers: %s', dict(request.headers))
    logger.debug('Body: %s', request.get_data())
    logger.debug('URL: %s', request.url)

@api.route('/processo/<num_processo>', methods=['GET'])
def get_processo(num_processo):
    """
    Retorna os dados do processo incluindo lista de documentos
    """
    try:
        logger.debug(f"API: Consultando processo {num_processo}")
        cpf, senha = get_mni_credentials()

        if not cpf or not senha:
            return jsonify({
                'erro': 'Credenciais MNI não fornecidas',
                'mensagem': 'Forneça as credenciais nos headers X-MNI-CPF e X-MNI-SENHA'
            }), 401

        resposta = retorna_processo(num_processo, cpf=cpf, senha=senha)

        # Extrair dados relevantes
        dados = extract_mni_data(resposta)
        return jsonify(dados)

    except Exception as e:
        logger.error(f"API: Erro ao consultar processo: {str(e)}", exc_info=True)
        return jsonify({
            'erro': str(e),
            'mensagem': 'Erro ao consultar processo'
        }), 500

@api.route('/processo/<num_processo>/documento/<num_documento>', methods=['GET'])
def download_documento(num_processo, num_documento):
    """
    Faz download de um documento específico do processo
    """
    try:
        logger.debug(f"API: Download do documento {num_documento} do processo {num_processo}")
        cpf, senha = get_mni_credentials()

        if not cpf or not senha:
            return jsonify({
                'erro': 'Credenciais MNI não fornecidas',
                'mensagem': 'Forneça as credenciais nos headers X-MNI-CPF e X-MNI-SENHA'
            }), 401

        resposta = retorna_documento_processo(num_processo, num_documento, cpf=cpf, senha=senha)

        if 'msg_erro' in resposta:
            return jsonify({
                'erro': resposta['msg_erro'],
                'mensagem': 'Erro ao baixar documento'
            }), 404

        # Criar arquivo temporário para download
        extensao = core.mime_to_extension.get(resposta['mimetype'], '.bin')
        temp_dir = tempfile.mkdtemp()
        file_path = os.path.join(temp_dir, f'{num_documento}{extensao}')

        with open(file_path, 'wb') as f:
            f.write(resposta['conteudo'])

        return send_file(
            file_path,
            mimetype=resposta['mimetype'],
            as_attachment=True,
            download_name=f'documento_{num_documento}{extensao}'
        )

    except Exception as e:
        logger.error(f"API: Erro ao baixar documento: {str(e)}", exc_info=True)
        return jsonify({
            'erro': str(e),
            'mensagem': 'Erro ao baixar documento'
        }), 500
        
@api.route('/processo/<num_processo>/peticao-inicial', methods=['GET'])
def get_peticao_inicial(num_processo):
    """
    Retorna a petição inicial e seus anexos para o processo informado
    """
    try:
        logger.debug(f"API: Buscando petição inicial do processo {num_processo}")
        cpf, senha = get_mni_credentials()

        if not cpf or not senha:
            return jsonify({
                'erro': 'Credenciais MNI não fornecidas',
                'mensagem': 'Forneça as credenciais nos headers X-MNI-CPF e X-MNI-SENHA'
            }), 401

        resposta = retorna_peticao_inicial_e_anexos(num_processo, cpf=cpf, senha=senha)

        if 'msg_erro' in resposta:
            return jsonify({
                'erro': resposta['msg_erro'],
                'mensagem': 'Erro ao buscar petição inicial'
            }), 404

        return jsonify(resposta)

    except Exception as e:
        logger.error(f"API: Erro ao buscar petição inicial: {str(e)}", exc_info=True)
        return jsonify({
            'erro': str(e),
            'mensagem': 'Erro ao buscar petição inicial'
        }), 500
        
@api.route('/processo/<num_processo>/capa', methods=['GET'])
def get_capa_processo(num_processo):
    """
    Retorna apenas os dados da capa do processo (sem documentos),
    incluindo dados básicos, assuntos, polos e movimentações
    """
    try:
        logger.debug(f"API: Consultando capa do processo {num_processo}")
        cpf, senha = get_mni_credentials()

        if not cpf or not senha:
            return jsonify({
                'erro': 'Credenciais MNI não fornecidas',
                'mensagem': 'Forneça as credenciais nos headers X-MNI-CPF e X-MNI-SENHA'
            }), 401

        # Usando o parâmetro incluir_documentos=False para melhor performance
        resposta = retorna_processo(num_processo, cpf=cpf, senha=senha, incluir_documentos=False)

        # Extrair apenas os dados da capa do processo
        dados = extract_capa_processo(resposta)
        return jsonify(dados)

    except Exception as e:
        logger.error(f"API: Erro ao consultar capa do processo: {str(e)}", exc_info=True)
        return jsonify({
            'erro': str(e),
            'mensagem': 'Erro ao consultar capa do processo'
        }), 500
        
        
@api.route('/processo/<num_processo>/pdf-completo', methods=['GET'])
def gerar_pdf_completo(num_processo):
    """
    Gera um PDF único contendo documentos do processo.
    Aceita parâmetros para controlar quais documentos incluir.
    
    Parâmetros de consulta:
        inicio: Índice do primeiro documento a incluir (padrão: 0)
        fim: Índice do último documento a incluir (padrão: máximo permitido)
        max_docs: Número máximo de documentos a incluir (padrão: 10)
        ids: Lista de IDs específicos de documentos, separados por vírgula (opcional)
        capa_detalhada: Se true, inclui informações detalhadas sobre o processo na capa (padrão: true)
    
    Args:
        num_processo (str): Número do processo judicial
        
    Returns:
        O arquivo PDF combinado para download ou uma mensagem de erro
    """
    from datetime import datetime
    
    # Obter parâmetros da consulta
    inicio = request.args.get('inicio', '0')
    fim = request.args.get('fim', '-1')
    max_docs = request.args.get('max_docs', '10')
    ids_str = request.args.get('ids', '')
    capa_detalhada = request.args.get('capa_detalhada', 'true').lower() == 'true'
    
    # Converter parâmetros para valores numéricos
    try:
        inicio = int(inicio)
        fim = int(fim)
        max_docs = int(max_docs)
    except ValueError:
        return jsonify({
            'erro': 'Parâmetros inválidos',
            'mensagem': 'Os parâmetros inicio, fim e max_docs devem ser números inteiros'
        }), 400
    
    # Limitar max_docs para evitar sobrecarga
    max_docs = min(max_docs, 50)
    
    # Processar lista de IDs específicos, se fornecida
    ids_especificos = []
    if ids_str:
        try:
            ids_especificos = [id.strip() for id in ids_str.split(',') if id.strip()]
        except Exception:
            logger.warning(f"Formato inválido para parâmetro 'ids': {ids_str}")
    
    # Buffer para o PDF final
    buffer = io.BytesIO()
    pdf_merger = PdfMerger()
    
    # Informações de status para incluir no PDF
    status_info = {
        'data_geracao': datetime.now().strftime('%d/%m/%Y %H:%M:%S'),
        'num_processo': num_processo,
        'total_documentos': 0,
        'documentos_processados': 0,
        'documentos_com_erro': 0,
        'erro_consulta': None,
        'inicio': inicio,
        'fim': fim,
        'max_docs': max_docs,
        'ids_especificos': ids_especificos,
        'detalhes_processo': {}
    }
    
    # Obter credenciais
    cpf, senha = get_mni_credentials()
    
    # Tentar obter a lista de documentos do processo
    try:
        if cpf and senha:
            # Tentar consultar o processo
            logger.debug(f"Consultando processo {num_processo}")
            resposta_processo = retorna_processo(num_processo, cpf=cpf, senha=senha)
            dados = extract_mni_data(resposta_processo)
            
            # Guardar detalhes do processo para a capa
            if dados.get('sucesso'):
                if 'processo' in dados:
                    status_info['detalhes_processo'] = {
                        'classe_processual': dados['processo'].get('classeProcessual', 'N/A'),
                        'orgao_julgador': dados['processo'].get('orgaoJulgador', 'N/A'),
                        'data_ajuizamento': dados['processo'].get('dataAjuizamento', 'N/A'),
                        'valor_causa': dados['processo'].get('valorCausa', 'N/A'),
                        'partes': []
                    }
                    
                    # Adicionar informações sobre as partes
                    if 'polos' in dados['processo']:
                        for polo in dados['processo']['polos']:
                            polo_tipo = 'Autor' if polo.get('polo') == 'AT' else 'Réu' if polo.get('polo') == 'PA' else polo.get('polo', 'Outro')
                            
                            for parte in polo.get('partes', []):
                                nome_parte = parte.get('nome', 'N/A')
                                advogados = [adv.get('nome', 'N/A') for adv in parte.get('advogados', [])]
                                
                                status_info['detalhes_processo']['partes'].append({
                                    'tipo': polo_tipo,
                                    'nome': nome_parte,
                                    'advogados': advogados
                                })
            
            if dados.get('sucesso') and dados.get('documentos'):
                documentos = dados['documentos']
                status_info['total_documentos'] = len(documentos)
                
                # Determinar quais documentos processar
                documentos_para_processar = []
                
                if ids_especificos:
                    # Filtrar por IDs específicos
                    id_map = {doc['id']: doc for doc in documentos}
                    documentos_para_processar = [id_map[doc_id] for doc_id in ids_especificos if doc_id in id_map]
                    # Registrar quais IDs não foram encontrados
                    ids_nao_encontrados = [doc_id for doc_id in ids_especificos if doc_id not in id_map]
                    if ids_nao_encontrados:
                        logger.warning(f"IDs não encontrados: {ids_nao_encontrados}")
                else:
                    # Aplicar intervalo (inicio-fim)
                    if fim < 0:
                        fim = len(documentos) - 1
                    
                    # Garantir limites válidos
                    inicio = max(0, min(inicio, len(documentos) - 1))
                    fim = max(inicio, min(fim, len(documentos) - 1))
                    
                    # Aplicar limite máximo de documentos
                    fim = min(fim, inicio + max_docs - 1)
                    
                    # Selecionar documentos no intervalo
                    documentos_para_processar = documentos[inicio:fim + 1]
                
                # Processar documentos selecionados
                for doc in documentos_para_processar:
                    doc_id = doc['id']
                    tipo_doc = doc.get('tipoDocumento', 'Documento')
                    data_doc = doc.get('dataDocumento', '')
                    
                    # Tentar obter o documento
                    try:
                        resposta = retorna_documento_processo(num_processo, doc_id, cpf=cpf, senha=senha)
                        
                        if 'msg_erro' not in resposta and resposta.get('conteudo'):
                            mimetype = resposta.get('mimetype', '')
                            conteudo = resposta.get('conteudo', b'')
                            
                            # Processar com base no mimetype
                            if mimetype == 'application/pdf':
                                # Já é PDF, usar diretamente
                                doc_buffer = io.BytesIO(conteudo)
                                
                                # Adicionar separador/cabeçalho como PDF
                                sep_buffer = io.BytesIO()
                                sep = canvas.Canvas(sep_buffer, pagesize=letter)
                                sep.setFont("Helvetica-Bold", 14)
                                sep.drawString(72, 750, f"Documento {doc_id} - {tipo_doc}")
                                if data_doc:
                                    sep.setFont("Helvetica", 12)
                                    sep.drawString(72, 730, f"Data: {data_doc}")
                                sep.setFont("Helvetica", 12)
                                sep.drawString(72, 710, "Tipo: PDF")
                                
                                # Linha divisória
                                sep.setStrokeColorRGB(0.8, 0.8, 0.8)
                                sep.setLineWidth(1)
                                sep.line(72, 690, 540, 690)
                                
                                sep.showPage()
                                sep.save()
                                sep_buffer.seek(0)
                                
                                # Adicionar separador e documento ao PDF
                                pdf_merger.append(sep_buffer)
                                pdf_merger.append(doc_buffer)
                                status_info['documentos_processados'] += 1
                            else:
                                # Criar PDF para outros tipos
                                doc_buffer = io.BytesIO()
                                pdf = canvas.Canvas(doc_buffer, pagesize=letter)
                                
                                # Cabeçalho do documento
                                pdf.setFont("Helvetica-Bold", 14)
                                pdf.drawString(72, 750, f"Documento {doc_id} - {tipo_doc}")
                                if data_doc:
                                    pdf.setFont("Helvetica", 12)
                                    pdf.drawString(72, 730, f"Data: {data_doc}")
                                
                                # Tipo de conteúdo
                                pdf.setFont("Helvetica", 12)
                                pdf.drawString(72, 710, f"Tipo: {mimetype}")
                                pdf.drawString(72, 690, f"Tamanho: {len(conteudo)} bytes")
                                
                                # Linha divisória
                                pdf.setStrokeColorRGB(0.8, 0.8, 0.8)
                                pdf.setLineWidth(1)
                                pdf.line(72, 670, 540, 670)
                                
                                # Tentar incluir conteúdo para alguns formatos
                                if mimetype in ['text/plain', 'text/html', 'text/xml']:
                                    try:
                                        texto = conteudo.decode('utf-8', errors='ignore')
                                        # Limite para evitar textos muito longos
                                        if len(texto) > 5000:
                                            texto = texto[:5000] + "...\n[Texto truncado por ser muito longo]"
                                        
                                        # Quebrar o texto em linhas
                                        y = 650
                                        pdf.setFont("Courier", 10)
                                        
                                        linhas = texto.split('\n')
                                        for i, linha in enumerate(linhas):
                                            if y < 50:  # Verificar espaço na página
                                                pdf.showPage()
                                                y = 750
                                                pdf.setFont("Courier", 10)
                                            
                                            # Truncar linhas muito longas
                                            if len(linha) > 80:
                                                linha = linha[:77] + "..."
                                                
                                            pdf.drawString(72, y, linha)
                                            y -= 12
                                            
                                            # Limitar número de linhas
                                            if i > 300:
                                                pdf.drawString(72, y, "[...]")
                                                break
                                    except Exception as e:
                                        pdf.setFont("Helvetica", 12)
                                        pdf.setFillColorRGB(0.8, 0.2, 0.2)
                                        pdf.drawString(72, 650, f"Erro ao processar texto: {str(e)}")
                                else:
                                    pdf.setFont("Helvetica", 12)
                                    pdf.drawString(72, 650, "Conteúdo em formato binário não pode ser exibido diretamente.")
                                    pdf.drawString(72, 630, "Use o endpoint de download específico para este documento.")
                                
                                pdf.showPage()
                                pdf.save()
                                doc_buffer.seek(0)
                                
                                # Adicionar ao PDF final
                                pdf_merger.append(doc_buffer)
                                status_info['documentos_processados'] += 1
                        else:
                            # Documento com erro, gerar página informativa
                            erro_msg = resposta.get('msg_erro', 'Erro desconhecido ao obter documento')
                            erro_buffer = io.BytesIO()
                            erro_pdf = canvas.Canvas(erro_buffer, pagesize=letter)
                            
                            erro_pdf.setFont("Helvetica-Bold", 14)
                            erro_pdf.drawString(72, 750, f"Documento {doc_id} - {tipo_doc}")
                            if data_doc:
                                erro_pdf.setFont("Helvetica", 12)
                                erro_pdf.drawString(72, 730, f"Data: {data_doc}")
                            
                            erro_pdf.setFont("Helvetica-Bold", 12)
                            erro_pdf.setFillColorRGB(0.8, 0.2, 0.2)
                            erro_pdf.drawString(72, 700, "ERRO AO OBTER DOCUMENTO")
                            
                            erro_pdf.setFont("Helvetica", 12)
                            erro_pdf.drawString(72, 680, erro_msg)
                            
                            erro_pdf.showPage()
                            erro_pdf.save()
                            erro_buffer.seek(0)
                            
                            pdf_merger.append(erro_buffer)
                            status_info['documentos_com_erro'] += 1
                    except Exception as e:
                        logger.error(f"Erro ao processar documento {doc_id}: {str(e)}")
                        status_info['documentos_com_erro'] += 1
        else:
            status_info['erro_consulta'] = "Credenciais MNI não fornecidas"
    except Exception as e:
        logger.error(f"Erro ao consultar processo: {str(e)}")
        status_info['erro_consulta'] = str(e)
    
    # Criar página de capa com informações detalhadas do processo
    capa_buffer = io.BytesIO()
    capa = canvas.Canvas(capa_buffer, pagesize=letter)
    
    # Cabeçalho
    capa.setFont("Helvetica-Bold", 16)
    capa.drawString(72, 750, f"PROCESSO {num_processo}")
    
    # Informações básicas
    capa.setFont("Helvetica", 12)
    y = 720
    capa.drawString(72, y, f"PDF gerado em: {status_info['data_geracao']}")
    y -= 20
    
    if status_info['erro_consulta']:
        capa.setFont("Helvetica-Bold", 12)
        capa.drawString(72, y, "Erro na consulta:")
        y -= 20
        capa.setFont("Helvetica", 12)
        capa.drawString(72, y, status_info['erro_consulta'])
    else:
        # Informações sobre os documentos
        capa.drawString(72, y, f"Total de documentos no processo: {status_info['total_documentos']}")
        y -= 20
        
        if ids_especificos:
            capa.drawString(72, y, f"Documentos selecionados por ID: {', '.join(ids_especificos)}")
        else:
            capa.drawString(72, y, f"Intervalo de documentos: {status_info['inicio']} a {status_info['fim']}")
        y -= 20
        
        capa.drawString(72, y, f"Documentos incluídos neste PDF: {status_info['documentos_processados']}")
        y -= 20
        
        if status_info['documentos_com_erro'] > 0:
            capa.setFillColorRGB(0.8, 0.2, 0.2)
            capa.drawString(72, y, f"Documentos com erro: {status_info['documentos_com_erro']}")
            capa.setFillColorRGB(0, 0, 0)
            y -= 20
        
        # Adicionar informações detalhadas do processo, se solicitado
        if capa_detalhada and status_info['detalhes_processo']:
            y -= 10
            capa.setFont("Helvetica-Bold", 14)
            capa.drawString(72, y, "INFORMAÇÕES DO PROCESSO")
            y -= 20
            
            capa.setFont("Helvetica", 12)
            detalhes = status_info['detalhes_processo']
            
            # Classe processual
            if detalhes.get('classe_processual'):
                capa.drawString(72, y, f"Classe: {detalhes['classe_processual']}")
                y -= 20
            
            # Órgão julgador
            if detalhes.get('orgao_julgador'):
                capa.drawString(72, y, f"Órgão Julgador: {detalhes['orgao_julgador']}")
                y -= 20
            
            # Data de ajuizamento
            if detalhes.get('data_ajuizamento'):
                data_str = detalhes['data_ajuizamento']
                # Formatar data se estiver no formato YYYYMMDD
                if isinstance(data_str, str) and len(data_str) == 8:
                    try:
                        data_str = f"{data_str[6:8]}/{data_str[4:6]}/{data_str[0:4]}"
                    except:
                        pass
                capa.drawString(72, y, f"Data de Ajuizamento: {data_str}")
                y -= 20
            
            # Valor da causa
            if detalhes.get('valor_causa'):
                valor = detalhes['valor_causa']
                if isinstance(valor, (int, float)):
                    valor = f"R$ {valor:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
                capa.drawString(72, y, f"Valor da Causa: {valor}")
                y -= 30
            
            # Partes do processo
            if detalhes.get('partes'):
                capa.setFont("Helvetica-Bold", 14)
                capa.drawString(72, y, "PARTES DO PROCESSO")
                y -= 20
                
                # Agrupar partes por tipo (autor/réu)
                partes_por_tipo = {}
                for parte in detalhes['partes']:
                    tipo = parte.get('tipo', 'Outro')
                    if tipo not in partes_por_tipo:
                        partes_por_tipo[tipo] = []
                    partes_por_tipo[tipo].append(parte)
                
                # Exibir partes agrupadas
                capa.setFont("Helvetica", 12)
                for tipo, lista_partes in partes_por_tipo.items():
                    if y < 100:  # Verificar se precisa de nova página
                        capa.showPage()
                        y = 750
                        capa.setFont("Helvetica", 12)
                    
                    capa.setFont("Helvetica-Bold", 12)
                    capa.drawString(72, y, f"{tipo}:")
                    y -= 20
                    
                    capa.setFont("Helvetica", 12)
                    for parte in lista_partes:
                        capa.drawString(90, y, parte.get('nome', 'N/A'))
                        y -= 15
                        
                        # Advogados
                        if parte.get('advogados'):
                            capa.setFont("Helvetica-Oblique", 10)
                            capa.drawString(108, y, f"Advogados: {', '.join(parte['advogados'])}")
                            capa.setFont("Helvetica", 12)
                            y -= 20
                        else:
                            y -= 5
                    
                    y -= 10  # Espaço extra entre grupos
        
        # Mostrar opções para geração de PDF por partes
        if status_info['total_documentos'] > 10:
            if y < 150:  # Se não tiver espaço suficiente, criar nova página
                capa.showPage()
                y = 750
                capa.setFont("Helvetica-Bold", 14)
            else:
                y -= 20
            
            capa.setFont("Helvetica-Bold", 14)
            capa.drawString(72, y, "GERAR PDF POR PARTES")
            y -= 20
            
            capa.setFont("Helvetica", 12)
            capa.drawString(72, y, "Para gerar PDFs parciais, use os seguintes parâmetros de consulta:")
            y -= 20
            
            # Mostrar exemplos de intervalos
            capa.setFont("Courier", 10)
            total_docs = status_info['total_documentos']
            
            # Calcular intervalos recomendados (dividir em grupos de 10)
            intervalos = []
            for i in range(0, total_docs, 10):
                fim = min(i + 9, total_docs - 1)
                intervalos.append(f"inicio={i}&fim={fim}")
            
            # Mostrar intervalos recomendados
            for i, intervalo in enumerate(intervalos[:5]):  # Mostrar até 5 intervalos
                capa.drawString(90, y, f"{i+1}. {intervalo}")
                y -= 15
            
            if len(intervalos) > 5:
                capa.drawString(90, y, "...")
                y -= 15
                capa.drawString(90, y, f"{len(intervalos)}. inicio={total_docs-10}&fim={total_docs-1}")
                y -= 15
    
    capa.showPage()
    capa.save()
    capa_buffer.seek(0)
    
    # Adicionar capa como primeira página
    pdf_merger.append(capa_buffer)
    
    # Finalizar e salvar o PDF
    pdf_merger.write(buffer)
    pdf_merger.close()
    buffer.seek(0)
    
    # Retornar o PDF completo
    return send_file(
        buffer,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f'processo_{num_processo}.pdf'
    )


def gerar_cabecalho_processo(dados_processo):
    """
    Gera um PDF contendo informações básicas do processo como cabeçalho.
    
    Args:
        dados_processo (dict): Dados do processo
        
    Returns:
        io.BytesIO: Buffer com o PDF gerado
    """
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    pdf.setTitle(f"Informações do Processo {dados_processo.get('processo', {}).get('numero', '')}")
    
    # Configurar fonte e tamanho
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(72, 750, "INFORMAÇÕES DO PROCESSO")
    
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(72, 720, f"Processo: {dados_processo.get('processo', {}).get('numero', 'N/A')}")
    
    pdf.setFont("Helvetica", 12)
    y = 690
    
    # Dados básicos
    if 'processo' in dados_processo:
        proc = dados_processo['processo']
        
        # Classe processual
        classe_desc = ''
        if proc.get('classeProcessual'):
            classe_desc = f"Classe: {proc.get('classeProcessual', 'N/A')}"
        pdf.drawString(72, y, classe_desc)
        y -= 20
        
        # Órgão julgador
        if proc.get('orgaoJulgador'):
            pdf.drawString(72, y, f"Órgão Julgador: {proc.get('orgaoJulgador', 'N/A')}")
            y -= 20
            
        # Data de ajuizamento
        if proc.get('dataAjuizamento'):
            data_str = proc.get('dataAjuizamento')
            # Formatar data se estiver no formato YYYYMMDD
            if len(data_str) == 8:
                try:
                    data_str = f"{data_str[6:8]}/{data_str[4:6]}/{data_str[0:4]}"
                except:
                    pass
            pdf.drawString(72, y, f"Data de Ajuizamento: {data_str}")
            y -= 30
    
    # Adicionar lista de documentos
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(72, y, "DOCUMENTOS DO PROCESSO")
    y -= 20
    
    pdf.setFont("Helvetica", 10)
    for i, doc in enumerate(dados_processo.get('documentos', []), 1):
        pdf.drawString(72, y, f"{i}. {doc.get('tipoDocumento', 'Documento')} (ID: {doc.get('id', 'N/A')})")
        if doc.get('dataDocumento'):
            pdf.drawString(350, y, f"Data: {doc.get('dataDocumento', 'N/A')}")
        y -= 15
        
        # Evitar que o texto ultrapasse a página
        if y < 72:
            pdf.showPage()
            pdf.setFont("Helvetica", 10)
            y = 750
    
    pdf.showPage()
    pdf.save()
    
    buffer.seek(0)
    return buffer


def converter_para_pdf(temp_dir, doc_id, tipo_doc, mimetype, conteudo):
    """
    Converte o conteúdo de um documento para PDF.
    
    Args:
        temp_dir (str): Diretório temporário para armazenar arquivos
        doc_id (str): ID do documento
        tipo_doc (str): Tipo do documento
        mimetype (str): Tipo MIME do conteúdo
        conteudo (bytes): Conteúdo binário do documento
        
    Returns:
        str: Caminho para o arquivo PDF gerado, ou None em caso de erro
    """
    try:
        # Caminho para o arquivo temporário
        arquivo_temp = os.path.join(temp_dir, f"doc_{doc_id}")
        
        # Variável para armazenar o caminho do PDF final
        pdf_path = None
            
        if mimetype == 'application/pdf':
            # Já é PDF, salvar diretamente
            pdf_path = f"{arquivo_temp}.pdf"
            with open(pdf_path, 'wb') as f:
                f.write(conteudo)
                
        elif mimetype == 'text/html':
            # Converter HTML para PDF
            html_path = f"{arquivo_temp}.html"
            pdf_path = f"{arquivo_temp}.pdf"
            
            with open(html_path, 'wb') as f:
                f.write(conteudo)
                
            # Gerar PDF a partir do HTML usando WeasyPrint
            try:
                html = weasyprint.HTML(filename=html_path)
                html.write_pdf(pdf_path)
                logger.debug(f"Arquivo HTML convertido para PDF: {pdf_path}")
            except Exception as e:
                logger.error(f"Erro ao converter HTML para PDF: {str(e)}")
                # Tenta criar um PDF simples com o texto
                try:
                    texto_html = conteudo.decode('utf-8', errors='ignore')
                    create_text_pdf(texto_html, pdf_path, doc_id, tipo_doc)
                except Exception as ex:
                    logger.error(f"Erro secundário ao processar HTML: {str(ex)}")
                    return None
                
        elif mimetype in ['text/plain', 'text/xml']:
            # Converter texto para PDF
            try:
                text = conteudo.decode('utf-8', errors='ignore')
                pdf_path = f"{arquivo_temp}.pdf"
                create_text_pdf(text, pdf_path, doc_id, tipo_doc)
            except Exception as e:
                logger.error(f"Erro ao criar PDF de texto: {str(e)}")
                return None
        else:
            # Para outros tipos, criar um PDF com informações básicas
            logger.warning(f"Tipo de arquivo não suportado diretamente: {mimetype}")
            pdf_path = f"{arquivo_temp}.pdf"
            message = f"Documento {doc_id} ({tipo_doc}) possui formato não suportado: {mimetype}"
            create_info_pdf(message, pdf_path, doc_id, tipo_doc)
        
        # Verificar se o PDF foi gerado com sucesso
        if pdf_path and os.path.exists(pdf_path):
            # Adicionar cabeçalho ao PDF com informações do documento
            try:
                add_document_header(pdf_path, doc_id, tipo_doc)
                logger.debug(f"Documento {doc_id} processado com sucesso")
                return pdf_path
            except Exception as e:
                logger.error(f"Erro ao adicionar cabeçalho ao PDF: {str(e)}")
                return pdf_path
        else:
            logger.error(f"Falha ao gerar PDF para o documento {doc_id}")
            return None
            
    except Exception as e:
        logger.error(f"Erro ao converter documento {doc_id} para PDF: {str(e)}", exc_info=True)
        return None


def criar_pdf_erro(temp_dir, doc_id, tipo_doc, mensagem_erro):
    """
    Cria um PDF com informações sobre um erro relacionado a um documento.
    
    Args:
        temp_dir (str): Diretório temporário para armazenar arquivos
        doc_id (str): ID do documento
        tipo_doc (str): Tipo do documento
        mensagem_erro (str): Mensagem de erro
        
    Returns:
        str: Caminho para o arquivo PDF gerado, ou None em caso de erro
    """
    try:
        arquivo_temp = os.path.join(temp_dir, f"doc_{doc_id}")
        pdf_path = f"{arquivo_temp}.pdf"
        create_info_pdf(mensagem_erro, pdf_path, doc_id, tipo_doc)
        
        if os.path.exists(pdf_path):
            return pdf_path
        return None
    except Exception as e:
        logger.error(f"Erro ao criar PDF de erro para o documento {doc_id}: {str(e)}")
        return None


def baixar_documento(num_processo, id_documento, tipo_documento, cpf, senha, temp_dir):
    """
    Baixa um documento do processo e o converte para PDF se necessário.
    Usa o endpoint de download para obter o documento.
    
    Args:
        num_processo (str): Número do processo
        id_documento (str): ID do documento
        tipo_documento (str): Tipo do documento
        cpf (str): CPF/CNPJ do consultante
        senha (str): Senha do consultante
        temp_dir (str): Diretório temporário para armazenar arquivos
        
    Returns:
        dict: Informações do documento processado, incluindo caminho para o PDF gerado
    """
    try:
        # Obter o documento usando o endpoint de download
        resposta = retorna_documento_processo(num_processo, id_documento, cpf=cpf, senha=senha)
        
        if 'msg_erro' in resposta:
            logger.error(f"Erro ao obter documento {id_documento}: {resposta['msg_erro']}")
            # Criar um PDF informativo sobre o erro
            arquivo_temp = os.path.join(temp_dir, f"doc_{id_documento}")
            pdf_path = f"{arquivo_temp}.pdf"
            message = f"Erro ao obter documento {id_documento}: {resposta['msg_erro']}"
            create_info_pdf(message, pdf_path, id_documento, tipo_documento)
            return {'id': id_documento, 'caminho_pdf': pdf_path}
            
        mimetype = resposta.get('mimetype', '')
        conteudo = resposta.get('conteudo', b'')  # Garantir que conteúdo nunca seja None
        
        logger.debug(f"Documento {id_documento} baixado com sucesso. Mimetype: {mimetype}, Tamanho: {len(conteudo) if conteudo else 0} bytes")
        
        # O restante do processamento é igual ao método original
        return processar_conteudo_documento(id_documento, tipo_documento, mimetype, conteudo, temp_dir)
            
    except Exception as e:
        logger.error(f"Erro ao baixar documento {id_documento}: {str(e)}", exc_info=True)
        return None


def processar_conteudo_documento(id_documento, tipo_documento, mimetype, conteudo, temp_dir):
    """
    Processa o conteúdo de um documento, convertendo-o para PDF se necessário.
    
    Args:
        id_documento (str): ID do documento
        tipo_documento (str): Tipo do documento
        mimetype (str): Tipo MIME do conteúdo
        conteudo (bytes): Conteúdo binário do documento
        temp_dir (str): Diretório temporário para armazenar arquivos
        
    Returns:
        dict: Informações do documento processado, incluindo caminho para o PDF gerado
    """
    try:
        # Verificar se temos conteúdo válido
        if not conteudo:
            logger.warning(f"Documento {id_documento} sem conteúdo")
            # Criar um PDF informativo sobre o erro
            arquivo_temp = os.path.join(temp_dir, f"doc_{id_documento}")
            pdf_path = f"{arquivo_temp}.pdf"
            message = f"Documento {id_documento} ({tipo_documento}) não possui conteúdo"
            create_info_pdf(message, pdf_path, id_documento, tipo_documento)
            return {'id': id_documento, 'caminho_pdf': pdf_path}
        
        # Caminho para o arquivo temporário
        arquivo_temp = os.path.join(temp_dir, f"doc_{id_documento}")
        
        # Variável para armazenar o caminho do PDF final
        pdf_path = None
            
        if mimetype == 'application/pdf':
            # Já é PDF, salvar diretamente
            pdf_path = f"{arquivo_temp}.pdf"
            with open(pdf_path, 'wb') as f:
                f.write(conteudo)
                
        elif mimetype == 'text/html':
            # Converter HTML para PDF
            html_path = f"{arquivo_temp}.html"
            pdf_path = f"{arquivo_temp}.pdf"
            
            with open(html_path, 'wb') as f:
                f.write(conteudo)
                
            # Gerar PDF a partir do HTML usando WeasyPrint
            try:
                html = weasyprint.HTML(filename=html_path)
                html.write_pdf(pdf_path)
                logger.debug(f"Arquivo HTML convertido para PDF: {pdf_path}")
            except Exception as e:
                logger.error(f"Erro ao converter HTML para PDF: {str(e)}")
                # Tenta criar um PDF simples com o texto
                try:
                    texto_html = conteudo.decode('utf-8', errors='ignore')
                    create_text_pdf(texto_html, pdf_path, id_documento, tipo_documento)
                except Exception as ex:
                    logger.error(f"Erro secundário ao processar HTML: {str(ex)}")
                    return None
                
        elif mimetype in ['text/plain', 'text/xml']:
            # Converter texto para PDF
            try:
                text = conteudo.decode('utf-8', errors='ignore')
                pdf_path = f"{arquivo_temp}.pdf"
                create_text_pdf(text, pdf_path, id_documento, tipo_documento)
            except Exception as e:
                logger.error(f"Erro ao criar PDF de texto: {str(e)}")
                return None
        else:
            # Para outros tipos, criar um PDF com informações básicas
            logger.warning(f"Tipo de arquivo não suportado diretamente: {mimetype}")
            pdf_path = f"{arquivo_temp}.pdf"
            message = f"Documento {id_documento} ({tipo_documento}) possui formato não suportado: {mimetype}"
            create_info_pdf(message, pdf_path, id_documento, tipo_documento)
        
        # Verificar se o PDF foi gerado com sucesso
        if pdf_path and os.path.exists(pdf_path):
            # Adicionar cabeçalho ao PDF com informações do documento
            try:
                add_document_header(pdf_path, id_documento, tipo_documento)
                logger.debug(f"Documento {id_documento} processado com sucesso")
                return {'id': id_documento, 'caminho_pdf': pdf_path}
            except Exception as e:
                logger.error(f"Erro ao adicionar cabeçalho ao PDF: {str(e)}")
                return {'id': id_documento, 'caminho_pdf': pdf_path}
        else:
            logger.error(f"Falha ao gerar PDF para o documento {id_documento}")
            return None
            
    except Exception as e:
        logger.error(f"Erro ao processar conteúdo do documento {id_documento}: {str(e)}", exc_info=True)
        return None


def processar_documento(num_processo, id_documento, tipo_documento, cpf, senha, temp_dir):
    """
    Processa um documento do processo, convertendo para PDF se necessário.
    Mantido para compatibilidade com código existente.
    
    Args:
        num_processo (str): Número do processo
        id_documento (str): ID do documento
        tipo_documento (str): Tipo do documento
        cpf (str): CPF/CNPJ do consultante
        senha (str): Senha do consultante
        temp_dir (str): Diretório temporário para armazenar arquivos
        
    Returns:
        dict: Informações do documento processado, incluindo caminho para o PDF gerado
    """
    try:
        # Obter o documento
        resposta = retorna_documento_processo(num_processo, id_documento, cpf=cpf, senha=senha)
        
        if 'msg_erro' in resposta:
            logger.error(f"Erro ao obter documento {id_documento}: {resposta['msg_erro']}")
            # Criar um PDF informativo sobre o erro
            arquivo_temp = os.path.join(temp_dir, f"doc_{id_documento}")
            pdf_path = f"{arquivo_temp}.pdf"
            message = f"Erro ao obter documento {id_documento}: {resposta['msg_erro']}"
            create_info_pdf(message, pdf_path, id_documento, tipo_documento)
            return {'id': id_documento, 'caminho_pdf': pdf_path}
            
        mimetype = resposta.get('mimetype', '')
        conteudo = resposta.get('conteudo', b'')  # Garantir que conteúdo nunca seja None
        
        # Verificar se temos conteúdo válido
        if not conteudo:
            logger.warning(f"Documento {id_documento} sem conteúdo")
            # Criar um PDF informativo sobre o erro
            arquivo_temp = os.path.join(temp_dir, f"doc_{id_documento}")
            pdf_path = f"{arquivo_temp}.pdf"
            message = f"Documento {id_documento} ({tipo_documento}) não possui conteúdo"
            create_info_pdf(message, pdf_path, id_documento, tipo_documento)
            return {'id': id_documento, 'caminho_pdf': pdf_path}
        
        # Caminho para o arquivo temporário
        arquivo_temp = os.path.join(temp_dir, f"doc_{id_documento}")
        
        # Variável para armazenar o caminho do PDF final
        pdf_path = None
            
        if mimetype == 'application/pdf':
            # Já é PDF, salvar diretamente
            pdf_path = f"{arquivo_temp}.pdf"
            with open(pdf_path, 'wb') as f:
                f.write(conteudo)
                
        elif mimetype == 'text/html':
            # Converter HTML para PDF
            html_path = f"{arquivo_temp}.html"
            pdf_path = f"{arquivo_temp}.pdf"
            
            with open(html_path, 'wb') as f:
                f.write(conteudo)
                
            # Gerar PDF a partir do HTML usando WeasyPrint
            try:
                html = weasyprint.HTML(filename=html_path)
                html.write_pdf(pdf_path)
                logger.debug(f"Arquivo HTML convertido para PDF: {pdf_path}")
            except Exception as e:
                logger.error(f"Erro ao converter HTML para PDF: {str(e)}")
                # Tenta criar um PDF simples com o texto
                try:
                    texto_html = conteudo.decode('utf-8', errors='ignore')
                    create_text_pdf(texto_html, pdf_path, id_documento, tipo_documento)
                except Exception as ex:
                    logger.error(f"Erro secundário ao processar HTML: {str(ex)}")
                    return None
                
        elif mimetype in ['text/plain', 'text/xml']:
            # Converter texto para PDF
            try:
                text = conteudo.decode('utf-8', errors='ignore')
                pdf_path = f"{arquivo_temp}.pdf"
                create_text_pdf(text, pdf_path, id_documento, tipo_documento)
            except Exception as e:
                logger.error(f"Erro ao criar PDF de texto: {str(e)}")
                return None
        else:
            # Para outros tipos, criar um PDF com informações básicas
            logger.warning(f"Tipo de arquivo não suportado diretamente: {mimetype}")
            pdf_path = f"{arquivo_temp}.pdf"
            message = f"Documento {id_documento} ({tipo_documento}) possui formato não suportado: {mimetype}"
            create_info_pdf(message, pdf_path, id_documento, tipo_documento)
        
        # Verificar se o PDF foi gerado com sucesso
        if pdf_path and os.path.exists(pdf_path):
            # Adicionar cabeçalho ao PDF com informações do documento
            try:
                add_document_header(pdf_path, id_documento, tipo_documento)
                logger.debug(f"Documento {id_documento} processado com sucesso")
                return {'id': id_documento, 'caminho_pdf': pdf_path}
            except Exception as e:
                logger.error(f"Erro ao adicionar cabeçalho ao PDF: {str(e)}")
                return {'id': id_documento, 'caminho_pdf': pdf_path}
        else:
            logger.error(f"Falha ao gerar PDF para o documento {id_documento}")
            return None
            
    except Exception as e:
        logger.error(f"Erro ao processar documento {id_documento}: {str(e)}", exc_info=True)
        return None


def create_text_pdf(text, output_path, doc_id, doc_type):
    """
    Cria um PDF a partir de texto.
    
    Args:
        text (str): Texto a ser convertido
        output_path (str): Caminho para salvar o PDF
        doc_id (str): ID do documento
        doc_type (str): Tipo do documento
    """
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    
    width, height = letter
    margin = 72  # 1 inch margins
    y = height - margin
    
    # Título
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(margin, y, f"Documento: {doc_type}")
    y -= 20
    
    pdf.setFont("Helvetica", 10)
    pdf.drawString(margin, y, f"ID: {doc_id}")
    y -= 30
    
    # Dividir o texto em linhas
    pdf.setFont("Courier", 10)
    linha_altura = 12
    max_width = width - 2 * margin
    
    # Função para quebrar texto em linhas
    def wrap_text(text, width, pdf):
        lines = []
        for paragraph in text.split('\n'):
            if not paragraph:
                lines.append('')
                continue
                
            words = paragraph.split(' ')
            line = ''
            
            for word in words:
                test_line = line + word + ' '
                if pdf.stringWidth(test_line, "Courier", 10) < width:
                    line = test_line
                else:
                    lines.append(line)
                    line = word + ' '
            
            if line:
                lines.append(line)
                
        return lines
    
    lines = wrap_text(text, max_width, pdf)
    
    for line in lines:
        if y < margin:
            pdf.showPage()
            y = height - margin
            pdf.setFont("Courier", 10)
            
        pdf.drawString(margin, y, line)
        y -= linha_altura
    
    pdf.showPage()
    pdf.save()
    
    with open(output_path, 'wb') as f:
        f.write(buffer.getvalue())


def create_info_pdf(message, output_path, doc_id, doc_type):
    """
    Cria um PDF informativo quando o tipo de arquivo não é suportado.
    
    Args:
        message (str): Mensagem a ser incluída no PDF
        output_path (str): Caminho para salvar o PDF
        doc_id (str): ID do documento
        doc_type (str): Tipo do documento
    """
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    
    width, height = letter
    
    # Título
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(72, height - 72, "INFORMAÇÃO DO DOCUMENTO")
    
    # Informações do documento
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(72, height - 100, f"Documento: {doc_type}")
    pdf.drawString(72, height - 120, f"ID: {doc_id}")
    
    # Mensagem
    pdf.setFont("Helvetica", 12)
    pdf.drawString(72, height - 160, message)
    pdf.drawString(72, height - 180, "Este documento não pôde ser convertido para PDF.")
    
    pdf.showPage()
    pdf.save()
    
    with open(output_path, 'wb') as f:
        f.write(buffer.getvalue())


def add_document_header(pdf_path, doc_id, doc_type):
    """
    Adiciona um cabeçalho com informações ao PDF existente.
    
    Args:
        pdf_path (str): Caminho do PDF a ser modificado
        doc_id (str): ID do documento
        doc_type (str): Tipo do documento
    """
    try:
        # Criar um novo arquivo para armazenar o resultado
        temp_output = f"{pdf_path}.temp.pdf"
        
        # Ler o PDF existente
        reader = PdfReader(pdf_path)
        writer = PdfWriter()
        
        # Para cada página do PDF original
        for i in range(len(reader.pages)):
            page = reader.pages[i]
            
            # Se for a primeira página, adicionar o cabeçalho
            if i == 0:
                # Criar um PDF com o cabeçalho
                packet = io.BytesIO()
                can = canvas.Canvas(packet, pagesize=letter)
                
                # Desenhar um retângulo cinza como plano de fundo para o cabeçalho
                can.setFillColorRGB(0.9, 0.9, 0.9)  # Cinza claro
                can.rect(10, 10, 575, 50, fill=True)
                
                # Adicionar texto do cabeçalho
                can.setFillColorRGB(0, 0, 0)  # Preto
                can.setFont("Helvetica-Bold", 12)
                can.drawString(20, 40, f"Documento: {doc_type}")
                can.setFont("Helvetica", 10)
                can.drawString(20, 25, f"ID: {doc_id}")
                
                can.save()
                
                # Mover para o início do buffer
                packet.seek(0)
                header_pdf = PdfReader(packet)
                header_page = header_pdf.pages[0]
                
                # Sobrepor o cabeçalho na página original
                page.merge_page(header_page)
            
            # Adicionar a página ao PDF de saída
            writer.add_page(page)
        
        # Salvar o PDF modificado
        with open(temp_output, 'wb') as f:
            writer.write(f)
            
        # Substituir o PDF original pelo modificado
        os.replace(temp_output, pdf_path)
        
    except Exception as e:
        logger.error(f"Erro ao adicionar cabeçalho ao PDF: {str(e)}")
        # Se falhar, não modifica o arquivo original
        return False
        
    return True
import os
import logging
from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
from dotenv import load_dotenv
import requests
from zeep import Client
from zeep.transports import Transport
from lxml import etree
import base64
from datetime import datetime
import json
import io
from PyPDF2 import PdfMerger
import tempfile

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Carregar variáveis de ambiente
load_dotenv()

app = Flask(__name__)
CORS(app)

# Configurações
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-secret-key-here')
app.config['MNI_CPF'] = os.getenv('MNI_CPF')
app.config['MNI_SENHA'] = os.getenv('MNI_SENHA')

# Mapeamento de tribunais por código
TRIBUNAL_WSDL_MAP = {
    '8.06': 'https://pje.tjce.jus.br/pje1grau/intercomunicacao?wsdl',  # TJCE
    '8.02': 'https://pje.tjal.jus.br/pje1grau/intercomunicacao?wsdl',  # TJAL
    '8.05': 'https://pje.tjba.jus.br/pje1grau/intercomunicacao?wsdl',  # TJBA
    '8.13': 'https://pje.tjmg.jus.br/pje/intercomunicacao?wsdl',      # TJMG
    '8.26': 'https://pje.tjsp.jus.br/pje/intercomunicacao?wsdl',      # TJSP
    '8.15': 'https://pje.tjpb.jus.br/pje1grau/intercomunicacao?wsdl', # TJPB
    '8.17': 'https://pje.tjpe.jus.br/pje1grau/intercomunicacao?wsdl', # TJPE
    '8.18': 'https://pje.tjpr.jus.br/pje1grau/intercomunicacao?wsdl', # TJPR
    '8.19': 'https://pje.tjrj.jus.br/pje1grau/intercomunicacao?wsdl', # TJRJ
    '8.20': 'https://pje.tjrn.jus.br/pje1grau/intercomunicacao?wsdl', # TJRN
    '8.21': 'https://pje.tjrs.jus.br/pje1grau/intercomunicacao?wsdl', # TJRS
    '8.24': 'https://pje.tjsc.jus.br/pje1grau/intercomunicacao?wsdl', # TJSC
    '8.25': 'https://pje.tjse.jus.br/pje1grau/intercomunicacao?wsdl', # TJSE
    '4.01': 'https://pje1g.trf1.jus.br/pje/intercomunicacao?wsdl',    # TRF1
    '4.02': 'https://pje.trf2.jus.br/pje/intercomunicacao?wsdl',      # TRF2
    '4.03': 'https://pje1g.trf3.jus.br/pje/intercomunicacao?wsdl',    # TRF3
    '4.04': 'https://pje.trf4.jus.br/pje/intercomunicacao?wsdl',      # TRF4
    '4.05': 'https://pje.trf5.jus.br/pje/intercomunicacao?wsdl',      # TRF5
}

def get_tribunal_from_numero_cnj(numero_processo):
    """Extrai o código do tribunal do número CNJ do processo"""
    try:
        # Remove pontos e traços se houver
        numero_limpo = numero_processo.replace('.', '').replace('-', '')
        
        # O código do tribunal está nas posições 13-16 (0-indexed)
        if len(numero_limpo) >= 16:
            codigo_tribunal = f"{numero_limpo[13]}.{numero_limpo[14:16]}"
            return codigo_tribunal
        
        logger.error(f"Número do processo inválido: {numero_processo}")
        return None
    except Exception as e:
        logger.error(f"Erro ao extrair tribunal: {str(e)}")
        return None

def get_wsdl_url(numero_processo):
    """Obtém a URL WSDL do tribunal correto baseado no número do processo"""
    codigo_tribunal = get_tribunal_from_numero_cnj(numero_processo)
    if codigo_tribunal and codigo_tribunal in TRIBUNAL_WSDL_MAP:
        return TRIBUNAL_WSDL_MAP[codigo_tribunal]
    
    logger.warning(f"Tribunal não mapeado para código: {codigo_tribunal}")
    # URL padrão do CNJ para testes
    return 'https://wwwh.cnj.jus.br/pjemni-2x/intercomunicacao?wsdl'

def consultar_processo_mni(numero_processo, cpf=None, senha=None):
    """Consulta processo via MNI/SOAP"""
    try:
        # Usar credenciais fornecidas ou padrão
        cpf = cpf or app.config['MNI_CPF']
        senha = senha or app.config['MNI_SENHA']
        
        if not cpf or not senha:
            return None, "Credenciais não fornecidas"
        
        # Obter URL WSDL apropriada
        wsdl_url = get_wsdl_url(numero_processo)
        logger.info(f"Usando WSDL: {wsdl_url}")
        
        # Criar cliente SOAP
        transport = Transport(timeout=30)
        client = Client(wsdl=wsdl_url, transport=transport)
        
        # Fazer a consulta
        response = client.service.consultarProcesso(
            idConsultante=cpf,
            senhaConsultante=senha,
            numeroProcesso=numero_processo,
            movimentos=True,
            incluirCabecalho=True,
            incluirDocumentos=True
        )
        
        return response, None
        
    except Exception as e:
        logger.error(f"Erro ao consultar MNI: {str(e)}")
        return None, str(e)

def consultar_avisos_pendentes(cpf, senha):
    """Consulta avisos pendentes do usuário"""
    try:
        # Por enquanto retorna mock - implementar quando necessário
        return [], None
    except Exception as e:
        return None, str(e)

def baixar_documento_mni(numero_processo, id_documento, cpf=None, senha=None):
    """Baixa documento específico via MNI"""
    try:
        # Implementação simplificada - em produção, usar consultarTeorComunicacao
        return None, "Funcionalidade em desenvolvimento"
    except Exception as e:
        return None, str(e)

def parse_processo_response(response):
    """Parse da resposta SOAP para JSON com todos os detalhes"""
    try:
        processo_data = {
            'sucesso': True,
            'processo': {
                'dadosBasicos': {},
                'documentos': [],
                'polos': [],
                'movimentos': [],
                'assuntos': [],
                'resumo': {}
            }
        }
        
        # Extrair dados básicos
        if hasattr(response, 'processo'):
            proc = response.processo
            
            # Dados básicos
            if hasattr(proc, 'dadosBasicos'):
                dados = proc.dadosBasicos
                processo_data['processo']['dadosBasicos'] = {
                    'numero': getattr(dados, 'numero', ''),
                    'classeProcessualNome': getattr(dados, 'classeProcessualNome', ''),
                    'classeProcessualCodigo': getattr(dados, 'codigoClasseProcessual', ''),
                    'dataAjuizamento': str(getattr(dados, 'dataAjuizamento', '')),
                    'valorCausa': float(getattr(dados, 'valorCausa', 0)),
                    'nivelSigilo': int(getattr(dados, 'nivelSigilo', 0)),
                    'orgaoJulgador': {
                        'nome': getattr(dados.orgaoJulgador, 'nomeOrgao', '') if hasattr(dados, 'orgaoJulgador') else '',
                        'codigo': getattr(dados.orgaoJulgador, 'codigoOrgao', '') if hasattr(dados, 'orgaoJulgador') else '',
                        'instancia': getattr(dados.orgaoJulgador, 'instancia', 'ORIG') if hasattr(dados, 'orgaoJulgador') else 'ORIG'
                    },
                    'prioridade': getattr(dados, 'prioridade', ''),
                    'competencia': getattr(dados, 'competencia', '')
                }
                
                # Assuntos
                if hasattr(dados, 'assunto') and dados.assunto:
                    for assunto in dados.assunto:
                        processo_data['processo']['assuntos'].append({
                            'codigo': getattr(assunto, 'codigoNacional', ''),
                            'descricao': getattr(assunto, 'descricao', ''),
                            'principal': getattr(assunto, 'principal', False)
                        })
            
            # Documentos
            if hasattr(proc, 'documento') and proc.documento:
                for doc in proc.documento:
                    doc_data = {
                        'idDocumento': getattr(doc, 'idDocumento', ''),
                        'tipoDocumentoNome': getattr(doc, 'tipoDocumento', ''),
                        'tipoDocumentoCodigo': getattr(doc, 'tipoDocumentoCodigo', ''),
                        'descricao': getattr(doc, 'descricao', ''),
                        'dataHoraInclusao': str(getattr(doc, 'dataHora', '')),
                        'mimetype': getattr(doc, 'mimetype', 'application/pdf'),
                        'nivelSigilo': int(getattr(doc, 'nivelSigilo', 0)),
                        'hash': getattr(doc, 'hash', ''),
                        'tamanho': getattr(doc, 'tamanho', 0)
                    }
                    
                    # Documentos vinculados (anexos)
                    if hasattr(doc, 'documentoVinculado') and doc.documentoVinculado:
                        doc_data['documentosVinculados'] = []
                        for vinc in doc.documentoVinculado:
                            doc_data['documentosVinculados'].append({
                                'idDocumento': getattr(vinc, 'idDocumento', ''),
                                'tipoDocumentoNome': getattr(vinc, 'tipoDocumento', ''),
                                'descricao': getattr(vinc, 'descricao', '')
                            })
                    
                    processo_data['processo']['documentos'].append(doc_data)
            
            # Polos
            if hasattr(proc, 'polo') and proc.polo:
                for polo in proc.polo:
                    polo_data = {
                        'polo': getattr(polo, 'polo', ''),
                        'parte': []
                    }
                    
                    if hasattr(polo, 'parte') and polo.parte:
                        for parte in polo.parte:
                            parte_data = {
                                'nome': getattr(parte, 'nome', ''),
                                'tipoPessoa': getattr(parte, 'tipoPessoa', ''),
                                'numeroDocumentoPrincipal': getattr(parte, 'numeroDocumentoPrincipal', ''),
                                'dataNascimento': str(getattr(parte, 'dataNascimento', '')) if hasattr(parte, 'dataNascimento') else '',
                                'nomeGenitor': getattr(parte, 'nomeGenitor', ''),
                                'nomeGenitora': getattr(parte, 'nomeGenitora', '')
                            }
                            
                            # Endereço
                            if hasattr(parte, 'endereco'):
                                end = parte.endereco
                                parte_data['endereco'] = {
                                    'cep': getattr(end, 'cep', ''),
                                    'logradouro': getattr(end, 'logradouro', ''),
                                    'numero': getattr(end, 'numero', ''),
                                    'complemento': getattr(end, 'complemento', ''),
                                    'bairro': getattr(end, 'bairro', ''),
                                    'cidade': getattr(end, 'cidade', ''),
                                    'estado': getattr(end, 'estado', '')
                                }
                            
                            # Representantes (advogados)
                            if hasattr(parte, 'representanteProcessual') and parte.representanteProcessual:
                                parte_data['advogados'] = []
                                for rep in parte.representanteProcessual:
                                    parte_data['advogados'].append({
                                        'nome': getattr(rep, 'nome', ''),
                                        'inscricao': getattr(rep, 'inscricao', ''),
                                        'numeroDocumentoPrincipal': getattr(rep, 'numeroDocumentoPrincipal', ''),
                                        'tipoRepresentante': getattr(rep, 'tipoRepresentante', '')
                                    })
                            
                            polo_data['parte'].append(parte_data)
                    
                    processo_data['processo']['polos'].append(polo_data)
            
            # Movimentos processuais
            if hasattr(proc, 'movimento') and proc.movimento:
                for mov in proc.movimento:
                    mov_data = {
                        'dataHora': str(getattr(mov, 'dataHora', '')),
                        'descricao': getattr(mov, 'descricao', ''),
                        'tipoMovimento': getattr(mov, 'tipoMovimento', ''),
                        'complemento': []
                    }
                    
                    # Complementos do movimento
                    if hasattr(mov, 'complemento') and mov.complemento:
                        for comp in mov.complemento:
                            mov_data['complemento'].append({
                                'nome': getattr(comp, 'nome', ''),
                                'descricao': getattr(comp, 'descricao', '')
                            })
                    
                    processo_data['processo']['movimentos'].append(mov_data)
                
                # Ordenar movimentos por data (mais recente primeiro)
                processo_data['processo']['movimentos'].sort(
                    key=lambda x: x['dataHora'], 
                    reverse=True
                )
            
            # Gerar resumo do processo
            processo_data['processo']['resumo'] = gerar_resumo_processo(processo_data['processo'])
        
        return processo_data
        
    except Exception as e:
        logger.error(f"Erro ao fazer parse da resposta: {str(e)}")
        return {
            'sucesso': False,
            'erro': 'PARSE_ERROR',
            'mensagem': f'Erro ao processar resposta: {str(e)}'
        }

def gerar_resumo_processo(processo):
    """Gera um resumo analítico do processo"""
    resumo = {
        'situacao': 'EM_ANDAMENTO',
        'temSentenca': False,
        'temRecurso': False,
        'temAcordao': False,
        'faseAtual': 'CONHECIMENTO',
        'ultimasMovimentacoes': [],
        'proximosPassos': [],
        'analise': ''
    }
    
    # Analisar movimentos para determinar situação
    movimentos = processo.get('movimentos', [])
    
    palavras_sentenca = ['sentença', 'sentenca', 'julgado', 'procedente', 'improcedente', 'extinto']
    palavras_recurso = ['recurso', 'apelação', 'apelacao', 'agravo', 'embargos']
    palavras_acordao = ['acórdão', 'acordao', 'turma', 'câmara', 'camara']
    palavras_transito = ['trânsito', 'transito', 'transitado', 'arquivado']
    
    for mov in movimentos[:20]:  # Analisar últimos 20 movimentos
        desc_lower = mov['descricao'].lower()
        
        # Verificar sentença
        if any(palavra in desc_lower for palavra in palavras_sentenca):
            resumo['temSentenca'] = True
            resumo['faseAtual'] = 'SENTENCIADO'
        
        # Verificar recurso
        if any(palavra in desc_lower for palavra in palavras_recurso):
            resumo['temRecurso'] = True
            resumo['faseAtual'] = 'RECURSAL'
        
        # Verificar acórdão
        if any(palavra in desc_lower for palavra in palavras_acordao):
            resumo['temAcordao'] = True
            resumo['faseAtual'] = 'SEGUNDA_INSTANCIA'
        
        # Verificar trânsito em julgado
        if any(palavra in desc_lower for palavra in palavras_transito):
            resumo['situacao'] = 'ARQUIVADO'
            resumo['faseAtual'] = 'TRANSITADO_JULGADO'
    
    # Últimas 5 movimentações
    resumo['ultimasMovimentacoes'] = movimentos[:5] if movimentos else []
    
    # Análise textual
    instancia = processo['dadosBasicos']['orgaoJulgador']['instancia']
    if instancia == 'ORIG':
        instancia_texto = '1ª instância'
    elif instancia == 'RECURSAL':
        instancia_texto = '2ª instância'
    else:
        instancia_texto = instancia
    
    resumo['analise'] = f"Processo em tramitação na {instancia_texto}. "
    
    if resumo['temSentenca']:
        resumo['analise'] += "Já foi proferida sentença. "
    
    if resumo['temRecurso']:
        resumo['analise'] += "Há recurso interposto. "
    
    if resumo['temAcordao']:
        resumo['analise'] += "Já houve julgamento em 2º grau. "
    
    if resumo['situacao'] == 'ARQUIVADO':
        resumo['analise'] += "Processo arquivado/transitado em julgado. "
    
    # Próximos passos possíveis
    if not resumo['temSentenca']:
        resumo['proximosPassos'].append("Aguardar sentença de 1º grau")
    elif resumo['temSentenca'] and not resumo['temRecurso']:
        resumo['proximosPassos'].append("Prazo para recurso")
    elif resumo['temRecurso'] and not resumo['temAcordao']:
        resumo['proximosPassos'].append("Aguardar julgamento do recurso")
    elif resumo['temAcordao']:
        resumo['proximosPassos'].append("Verificar possibilidade de recursos aos tribunais superiores")
    
    return resumo

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/v1/processo/<numero_processo>', methods=['GET'])
def consultar_processo(numero_processo):
    """Consulta dados completos do processo"""
    try:
        cpf = request.headers.get('X-MNI-CPF')
        senha = request.headers.get('X-MNI-SENHA')
        
        response, error = consultar_processo_mni(numero_processo, cpf, senha)
        
        if error:
            return jsonify({
                'sucesso': False,
                'erro': 'MNI_ERROR',
                'mensagem': error
            }), 400
        
        processo_data = parse_processo_response(response)
        
        return jsonify(processo_data)
        
    except Exception as e:
        logger.error(f"Erro na API: {str(e)}")
        return jsonify({
            'sucesso': False,
            'erro': 'INTERNAL_ERROR',
            'mensagem': str(e)
        }), 500

@app.route('/api/v1/processo/<numero_processo>/resumo', methods=['GET'])
def consultar_resumo_processo(numero_processo):
    """Retorna apenas o resumo analítico do processo"""
    try:
        cpf = request.headers.get('X-MNI-CPF')
        senha = request.headers.get('X-MNI-SENHA')
        
        response, error = consultar_processo_mni(numero_processo, cpf, senha)
        
        if error:
            return jsonify({
                'sucesso': False,
                'erro': 'MNI_ERROR',
                'mensagem': error
            }), 400
        
        processo_data = parse_processo_response(response)
        
        if processo_data['sucesso']:
            return jsonify({
                'sucesso': True,
                'numeroProcesso': numero_processo,
                'dadosBasicos': processo_data['processo']['dadosBasicos'],
                'resumo': processo_data['processo']['resumo'],
                'totalDocumentos': len(processo_data['processo']['documentos']),
                'totalMovimentos': len(processo_data['processo']['movimentos'])
            })
        
        return jsonify(processo_data)
        
    except Exception as e:
        logger.error(f"Erro na API: {str(e)}")
        return jsonify({
            'sucesso': False,
            'erro': 'INTERNAL_ERROR',
            'mensagem': str(e)
        }), 500

@app.route('/api/v1/processo/<numero_processo>/movimentos', methods=['GET'])
def consultar_movimentos(numero_processo):
    """Retorna movimentações do processo com filtros"""
    try:
        cpf = request.headers.get('X-MNI-CPF')
        senha = request.headers.get('X-MNI-SENHA')
        
        # Parâmetros de filtro
        limite = int(request.args.get('limite', 10))
        tipo = request.args.get('tipo', '')  # sentenca, recurso, etc
        
        response, error = consultar_processo_mni(numero_processo, cpf, senha)
        
        if error:
            return jsonify({
                'sucesso': False,
                'erro': 'MNI_ERROR',
                'mensagem': error
            }), 400
        
        processo_data = parse_processo_response(response)
        
        if processo_data['sucesso']:
            movimentos = processo_data['processo']['movimentos']
            
            # Aplicar filtro por tipo se especificado
            if tipo:
                movimentos = [m for m in movimentos if tipo.lower() in m['descricao'].lower()]
            
            # Limitar quantidade
            movimentos = movimentos[:limite]
            
            return jsonify({
                'sucesso': True,
                'numeroProcesso': numero_processo,
                'movimentos': movimentos,
                'total': len(processo_data['processo']['movimentos'])
            })
        
        return jsonify(processo_data)
        
    except Exception as e:
        logger.error(f"Erro na API: {str(e)}")
        return jsonify({
            'sucesso': False,
            'erro': 'INTERNAL_ERROR',
            'mensagem': str(e)
        }), 500

@app.route('/api/v1/processo/<numero_processo>/copia-integral', methods=['GET'])
def baixar_copia_integral(numero_processo):
    """Baixa cópia integral do processo (todos os documentos em um PDF)"""
    try:
        cpf = request.headers.get('X-MNI-CPF')
        senha = request.headers.get('X-MNI-SENHA')
        
        # Por enquanto, retornar informação sobre como seria implementado
        # Em produção, isso baixaria todos os documentos e mesclaria em um PDF
        
        return jsonify({
            'sucesso': False,
            'erro': 'NOT_IMPLEMENTED',
            'mensagem': 'Download de cópia integral será implementado em breve',
            'info': 'Esta funcionalidade baixará todos os documentos e mesclará em um único PDF'
        }), 501
        
    except Exception as e:
        logger.error(f"Erro na API: {str(e)}")
        return jsonify({
            'sucesso': False,
            'erro': 'INTERNAL_ERROR',
            'mensagem': str(e)
        }), 500

@app.route('/api/v1/processo/<numero_processo>/documento/<id_documento>', methods=['GET'])
def baixar_documento(numero_processo, id_documento):
    """Baixa um documento específico do processo"""
    try:
        cpf = request.headers.get('X-MNI-CPF')
        senha = request.headers.get('X-MNI-SENHA')
        
        # Por enquanto, retornar placeholder
        return jsonify({
            'sucesso': False,
            'erro': 'NOT_IMPLEMENTED',
            'mensagem': 'Endpoint de download individual em desenvolvimento'
        }), 501
        
    except Exception as e:
        logger.error(f"Erro na API: {str(e)}")
        return jsonify({
            'sucesso': False,
            'erro': 'INTERNAL_ERROR',
            'mensagem': str(e)
        }), 500

@app.route('/api/v1/avisos-pendentes', methods=['GET'])
def listar_avisos_pendentes():
    """Lista avisos/intimações pendentes do usuário"""
    try:
        cpf = request.headers.get('X-MNI-CPF')
        senha = request.headers.get('X-MNI-SENHA')
        
        avisos, error = consultar_avisos_pendentes(cpf, senha)
        
        if error:
            return jsonify({
                'sucesso': False,
                'erro': 'MNI_ERROR',
                'mensagem': error
            }), 400
        
        return jsonify({
            'sucesso': True,
            'avisos': avisos
        })
        
    except Exception as e:
        logger.error(f"Erro na API: {str(e)}")
        return jsonify({
            'sucesso': False,
            'erro': 'INTERNAL_ERROR',
            'mensagem': str(e)
        }), 500

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)

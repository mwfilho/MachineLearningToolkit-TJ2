#!/usr/bin/env python3
"""
Script independente para gerar um PDF completo com todos os documentos de um processo.
Este script não depende do Flask ou outras bibliotecas externas, apenas das funções MNI e utilitários básicos.

Uso:
    python3 api_standalone.py NUMERO_PROCESSO OUTPUT_FILE [CPF] [SENHA]

O script irá baixar todos os documentos do processo e gerar um único arquivo PDF ou texto.
"""

import os
import sys
import tempfile
import subprocess
import shutil
from datetime import datetime
import io
import logging
import time

# Configurar logging
logging.basicConfig(level=logging.DEBUG, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Importar funções do MNI e utilitários
try:
    from funcoes_mni import retorna_processo, retorna_documento_processo
    from utils import extract_mni_data
except ImportError as e:
    logger.error(f"Erro ao importar módulos necessários: {str(e)}")
    logger.error("Certifique-se de que os arquivos funcoes_mni.py e utils.py estão disponíveis.")
    sys.exit(1)

def processar_processo(num_processo, output_path=None, cpf=None, senha=None):
    """
    Processa um processo judicial e gera um arquivo PDF com todos os documentos
    
    Args:
        num_processo (str): Número do processo
        output_path (str): Caminho de saída para o arquivo PDF. Se None, será gerado automaticamente.
        cpf (str): CPF/CNPJ do consultante. Se None, usa valor do ambiente.
        senha (str): Senha do consultante. Se None, usa valor do ambiente.
        
    Returns:
        str: Caminho do arquivo gerado
    """
    # Criar diretório temporário
    temp_dir = tempfile.mkdtemp()
    logger.debug(f"Criado diretório temporário: {temp_dir}")
    
    try:
        # Se não informou output path, criar um no diretório atual
        if not output_path:
            output_path = os.path.join(os.getcwd(), f"processo_{num_processo}.pdf")
            
        # Credenciais do MNI - usar do ambiente se não fornecidas
        if not cpf:
            cpf = os.environ.get('MNI_ID_CONSULTANTE')
        if not senha:
            senha = os.environ.get('MNI_SENHA_CONSULTANTE')
            
        if not cpf or not senha:
            logger.error("Credenciais MNI não fornecidas. Use os parâmetros CPF e SENHA ou defina as variáveis de ambiente MNI_ID_CONSULTANTE e MNI_SENHA_CONSULTANTE.")
            return None
            
        # Consultar o processo
        logger.debug(f"Consultando processo {num_processo}")
        resposta_processo = retorna_processo(num_processo, cpf=cpf, senha=senha)
        dados = extract_mni_data(resposta_processo)
        
        if not dados.get('sucesso'):
            logger.error(f"Erro ao consultar processo: {dados.get('mensagem', 'Erro desconhecido')}")
            return None
            
        # Recolher documentos a processar
        todos_documentos = []
        
        # Extrair documentos principais
        for documento in dados.get('documentos', []):
            todos_documentos.append({
                'id': documento.get('id'),
                'descricao': documento.get('tipoDocumento', 'Documento'),
                'mimetype': documento.get('mimetype')
            })
        
        total_docs = len(todos_documentos)
        logger.debug(f"Total de documentos a processar: {total_docs}")
        
        # Criar um arquivo de índice
        indice_path = os.path.join(temp_dir, "00_indice.txt")
        with open(indice_path, 'w', encoding='utf-8') as f:
            f.write(f"ÍNDICE DE DOCUMENTOS DO PROCESSO {num_processo}\n")
            f.write(f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n")
            f.write("=" * 80 + "\n\n")
            
            for idx, doc in enumerate(todos_documentos, 1):
                f.write(f"{idx}. {doc['descricao']} (ID: {doc['id']})\n")
        
        # Processar cada documento
        docs_processados = 0
        arquivos_pdf = []
        arquivos_txt = []
        
        for idx, doc_info in enumerate(todos_documentos, 1):
            try:
                doc_id = doc_info['id']
                logger.debug(f"Processando documento {idx}/{total_docs}: {doc_id}")
                
                # Baixar o documento
                resposta = retorna_documento_processo(num_processo, doc_id, cpf=cpf, senha=senha)
                
                if 'msg_erro' in resposta or not resposta.get('conteudo'):
                    logger.error(f"Erro ao baixar documento {doc_id}: {resposta.get('msg_erro', 'Sem conteúdo')}")
                    continue
                
                mimetype = resposta.get('mimetype', '')
                conteudo = resposta.get('conteudo', b'')
                
                # Processar baseado no mimetype
                if mimetype == 'application/pdf':
                    # Salvar PDF diretamente
                    pdf_path = os.path.join(temp_dir, f"{idx:02d}_doc_{doc_id}.pdf")
                    with open(pdf_path, 'wb') as f:
                        f.write(conteudo)
                    arquivos_pdf.append(pdf_path)
                    docs_processados += 1
                    
                elif mimetype == 'text/html':
                    # Salvar como HTML
                    html_path = os.path.join(temp_dir, f"{idx:02d}_doc_{doc_id}.html")
                    with open(html_path, 'wb') as f:
                        f.write(conteudo)
                    
                    # Tentar converter para PDF com wkhtmltopdf
                    pdf_path = os.path.join(temp_dir, f"{idx:02d}_doc_{doc_id}.pdf")
                    
                    try:
                        # Verificar se wkhtmltopdf está disponível
                        subprocess.run(['which', 'wkhtmltopdf'], 
                                      check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                        
                        # Converter HTML para PDF
                        subprocess.run(['wkhtmltopdf', '--quiet', html_path, pdf_path],
                                      check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                        
                        if os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0:
                            arquivos_pdf.append(pdf_path)
                            docs_processados += 1
                            logger.debug(f"Documento HTML convertido para PDF: {pdf_path}")
                        else:
                            # Fallback: salvar como texto
                            texto_html = conteudo.decode('utf-8', errors='ignore')
                            txt_path = os.path.join(temp_dir, f"{idx:02d}_doc_{doc_id}.txt")
                            with open(txt_path, 'w', encoding='utf-8') as f:
                                f.write(f"DOCUMENTO {doc_id} (HTML)\n")
                                f.write("=" * 80 + "\n\n")
                                f.write(texto_html[:10000] + "..." if len(texto_html) > 10000 else texto_html)
                            arquivos_txt.append(txt_path)
                            docs_processados += 1
                    except Exception as e:
                        logger.error(f"Erro ao converter HTML para PDF: {str(e)}")
                        # Fallback: salvar como texto
                        texto_html = conteudo.decode('utf-8', errors='ignore')
                        txt_path = os.path.join(temp_dir, f"{idx:02d}_doc_{doc_id}.txt")
                        with open(txt_path, 'w', encoding='utf-8') as f:
                            f.write(f"DOCUMENTO {doc_id} (HTML)\n")
                            f.write("=" * 80 + "\n\n")
                            f.write(texto_html[:10000] + "..." if len(texto_html) > 10000 else texto_html)
                        arquivos_txt.append(txt_path)
                        docs_processados += 1
                
                else:
                    # Para outros formatos, salvar como texto
                    try:
                        texto = conteudo.decode('utf-8', errors='ignore')
                        txt_path = os.path.join(temp_dir, f"{idx:02d}_doc_{doc_id}.txt")
                        with open(txt_path, 'w', encoding='utf-8') as f:
                            f.write(f"DOCUMENTO {doc_id} ({mimetype})\n")
                            f.write("=" * 80 + "\n\n")
                            f.write(texto[:10000] + "..." if len(texto) > 10000 else texto)
                        arquivos_txt.append(txt_path)
                        docs_processados += 1
                    except Exception as txt_err:
                        logger.error(f"Erro ao processar documento {mimetype}: {str(txt_err)}")
            
            except Exception as e:
                logger.error(f"Erro ao processar documento {doc_id}: {str(e)}")
        
        # Gerar arquivo final
        final_output_path = output_path
        
        # Verificar se temos PDFs para combinar
        if arquivos_pdf:
            logger.debug(f"Combinando {len(arquivos_pdf)} arquivos PDF")
            
            try:
                # Tentar usar pdftk se disponível
                try:
                    subprocess.run(['which', 'pdftk'], 
                                  check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    
                    # pdftk está disponível
                    pdf_paths = sorted(arquivos_pdf)
                    command = ['pdftk'] + pdf_paths + ['cat', 'output', final_output_path]
                    subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    
                    logger.debug(f"PDFs combinados com pdftk: {final_output_path}")
                    
                except subprocess.CalledProcessError:
                    # pdftk não está disponível, usar método alternativo
                    # Simplesmente copiar o primeiro PDF
                    with open(final_output_path, 'wb') as out_f:
                        with open(sorted(arquivos_pdf)[0], 'rb') as in_f:
                            out_f.write(in_f.read())
                    
                    logger.debug(f"Método alternativo: Copiado primeiro PDF para {final_output_path}")
            
            except Exception as e:
                logger.error(f"Erro ao combinar PDFs: {str(e)}")
                # Usar o primeiro PDF como resultado
                if arquivos_pdf:
                    with open(final_output_path, 'wb') as out_f:
                        with open(sorted(arquivos_pdf)[0], 'rb') as in_f:
                            out_f.write(in_f.read())
        
        elif arquivos_txt:
            # Sem PDFs, criar um arquivo de texto único
            if final_output_path.lower().endswith('.pdf'):
                final_output_path = final_output_path.replace('.pdf', '.txt')
                
            # Combinar todos os arquivos de texto em um único arquivo
            with open(final_output_path, 'w', encoding='utf-8') as out_f:
                # Primeiro o índice
                with open(indice_path, 'r', encoding='utf-8') as in_f:
                    out_f.write(in_f.read())
                out_f.write("\n\n" + "=" * 80 + "\n\n")
                
                # Depois cada arquivo de texto ordenado
                for txt_path in sorted(arquivos_txt):
                    out_f.write("\n\n" + "=" * 40 + " NOVO DOCUMENTO " + "=" * 40 + "\n\n")
                    with open(txt_path, 'r', encoding='utf-8') as in_f:
                        out_f.write(in_f.read())
                    
            logger.debug(f"Gerado arquivo de texto: {final_output_path}")
        
        else:
            # Sem documentos processados
            logger.error(f"Nenhum documento foi processado com sucesso para o processo {num_processo}")
            return None
        
        logger.debug(f"Arquivo final gerado: {final_output_path}")
        return final_output_path
    
    except Exception as e:
        logger.error(f"Erro no processamento do processo: {str(e)}")
        return None
    
    finally:
        # Limpar arquivos temporários
        try:
            logger.debug(f"Limpando diretório temporário: {temp_dir}")
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception as e:
            logger.error(f"Erro ao limpar arquivos temporários: {str(e)}")

def main():
    """Função principal para execução via linha de comando"""
    if len(sys.argv) < 2:
        print(f"Uso: {sys.argv[0]} NUMERO_PROCESSO [OUTPUT_FILE] [CPF] [SENHA]")
        sys.exit(1)
        
    num_processo = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else None
    cpf = sys.argv[3] if len(sys.argv) > 3 else None
    senha = sys.argv[4] if len(sys.argv) > 4 else None
    
    # Processar o processo
    resultado = processar_processo(
        num_processo=num_processo,
        output_path=output_path,
        cpf=cpf,
        senha=senha
    )
    
    if resultado:
        print(f"Processo finalizado. Arquivo gerado: {resultado}")
        return 0
    else:
        print("Erro ao processar o processo. Verifique os logs para mais detalhes.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
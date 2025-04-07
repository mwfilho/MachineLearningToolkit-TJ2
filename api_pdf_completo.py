#!/usr/bin/env python3
"""
Script independente para gerar um PDF completo com todos os documentos de um processo.
Este script pode ser executado separadamente para testar a funcionalidade sem
necessidade de iniciar o servidor Flask completo.

Uso:
    python3 api_pdf_completo.py NUMERO_PROCESSO

O script irá baixar todos os documentos do processo e gerar um único arquivo PDF.
"""

import os
import sys
import tempfile
import shutil
import subprocess
import time
import io
from datetime import datetime

# Caminho absoluto para a raiz do projeto
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# Adicionar o projeto ao sys.path para poder importar módulos
sys.path.insert(0, PROJECT_ROOT)

# Importar as funções necessárias
from funcoes_mni import retorna_processo, retorna_documento_processo
from utils import extract_mni_data

# Credenciais do MNI
CPF = os.environ.get('MNI_ID_CONSULTANTE')
SENHA = os.environ.get('MNI_SENHA_CONSULTANTE')

def salvar_conteudo_como_txt(conteudo, caminho_saida, titulo="Documento"):
    """Salva conteúdo como arquivo de texto"""
    try:
        # Tentar decodificar como texto
        texto = conteudo.decode('utf-8', errors='ignore')
        
        with open(caminho_saida, 'w', encoding='utf-8') as f:
            f.write(f"{'=' * 80}\n")
            f.write(f"{titulo}\n")
            f.write(f"{'=' * 80}\n\n")
            f.write(texto)
            
        return True
    except Exception as e:
        print(f"Erro ao salvar conteúdo como texto: {str(e)}")
        return False

def converter_html_para_txt(caminho_html, caminho_txt, titulo="Documento HTML"):
    """Extrai texto de HTML e salva como TXT"""
    try:
        with open(caminho_html, 'rb') as f:
            conteudo = f.read()
            
        return salvar_conteudo_como_txt(conteudo, caminho_txt, titulo)
    except Exception as e:
        print(f"Erro ao converter HTML para TXT: {str(e)}")
        return False

def main(num_processo):
    print(f"Gerando PDF completo para o processo {num_processo}")
    
    # Usar credenciais de ambiente ou padrão para testes
    cpf = CPF
    senha = SENHA
    
    if not cpf or not senha:
        print("ERRO: Credenciais MNI não definidas!")
        print("Defina as variáveis de ambiente MNI_ID_CONSULTANTE e MNI_SENHA_CONSULTANTE")
        return 1
    
    # Criar diretório temporário
    temp_dir = tempfile.mkdtemp()
    print(f"Usando diretório temporário: {temp_dir}")
    
    try:
        # Consultar o processo
        print("Consultando processo...")
        resposta_processo = retorna_processo(num_processo, cpf=cpf, senha=senha)
        dados = extract_mni_data(resposta_processo)
        
        if not dados.get('sucesso'):
            print(f"ERRO: {dados.get('mensagem', 'Não foi possível obter os detalhes do processo')}")
            return 1
        
        # Recolher documentos a processar
        todos_documentos = []
        
        # Extrair documentos principais e anexos
        for documento in dados.get('documentos', []):
            todos_documentos.append({
                'id': documento.get('id'),
                'descricao': documento.get('tipoDocumento', 'Documento'),
                'mimetype': documento.get('mimetype')
            })
        
        print(f"Total de documentos a processar: {len(todos_documentos)}")
        
        # Criar arquivo de índice
        indice_path = os.path.join(temp_dir, "00_indice.txt")
        with open(indice_path, 'w', encoding='utf-8') as f:
            f.write(f"ÍNDICE DE DOCUMENTOS DO PROCESSO {num_processo}\n")
            f.write(f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n")
            f.write("=" * 80 + "\n\n")
            
            for idx, doc in enumerate(todos_documentos, 1):
                f.write(f"{idx}. {doc['descricao']} (ID: {doc['id']})\n")
        
        # Processar cada documento
        docs_processados = 0
        
        for idx, doc_info in enumerate(todos_documentos, 1):
            doc_id = doc_info['id']
            print(f"Processando documento {idx}/{len(todos_documentos)}: {doc_id}")
            
            # Baixar o documento
            resposta = retorna_documento_processo(num_processo, doc_id, cpf=cpf, senha=senha)
            
            if 'msg_erro' in resposta or not resposta.get('conteudo'):
                print(f"Erro ao baixar documento {doc_id}: {resposta.get('msg_erro', 'Sem conteúdo')}")
                continue
            
            mimetype = resposta.get('mimetype', '')
            conteudo = resposta.get('conteudo', b'')
            
            # Processar baseado no mimetype
            if mimetype == 'application/pdf':
                # Salvar PDF diretamente
                pdf_path = os.path.join(temp_dir, f"{idx:02d}_doc_{doc_id}.pdf")
                with open(pdf_path, 'wb') as f:
                    f.write(conteudo)
                docs_processados += 1
                
            elif mimetype == 'text/html':
                # Salvar como HTML
                html_path = os.path.join(temp_dir, f"{idx:02d}_doc_{doc_id}.html")
                with open(html_path, 'wb') as f:
                    f.write(conteudo)
                
                # Tentar converter para PDF com wkhtmltopdf se disponível
                pdf_path = os.path.join(temp_dir, f"{idx:02d}_doc_{doc_id}.pdf")
                
                try:
                    subprocess.run(['wkhtmltopdf', '--quiet', html_path, pdf_path],
                                check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    
                    if os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0:
                        docs_processados += 1
                    else:
                        # Fallback: salvar como texto
                        txt_path = os.path.join(temp_dir, f"{idx:02d}_doc_{doc_id}.txt")
                        if converter_html_para_txt(html_path, txt_path, f"Documento {doc_id} (HTML)"):
                            docs_processados += 1
                except Exception as e:
                    # Fallback: salvar como texto
                    txt_path = os.path.join(temp_dir, f"{idx:02d}_doc_{doc_id}.txt")
                    if converter_html_para_txt(html_path, txt_path, f"Documento {doc_id} (HTML)"):
                        docs_processados += 1
            
            else:
                # Para outros formatos, salvar como texto
                txt_path = os.path.join(temp_dir, f"{idx:02d}_doc_{doc_id}.txt")
                if salvar_conteudo_como_txt(conteudo, txt_path, f"Documento {doc_id} ({mimetype})"):
                    docs_processados += 1
        
        # Tentar combinar PDFs
        print(f"\nDocumentos processados: {docs_processados}/{len(todos_documentos)}")
        
        # Verificar se existem PDFs no diretório
        pdfs = [f for f in os.listdir(temp_dir) if f.endswith('.pdf')]
        txts = [f for f in os.listdir(temp_dir) if f.endswith('.txt')]
        
        if pdfs:
            print(f"Encontrados {len(pdfs)} arquivos PDF e {len(txts)} arquivos TXT")
            
            # Tentar mesclar PDFs com ferramenta disponível
            try:
                output_path = f"processo_{num_processo}.pdf"
                
                # Tentar usar pdftk (se disponível)
                pdf_paths = [os.path.join(temp_dir, pdf) for pdf in sorted(pdfs)]
                command = ['pdftk'] + pdf_paths + ['cat', 'output', output_path]
                
                try:
                    subprocess.run(command, check=True, capture_output=True)
                    print(f"\nArquivo PDF gerado com sucesso: {output_path}")
                except:
                    # Se pdftk falhar, copiar apenas o primeiro PDF como resultado
                    if pdfs:
                        with open(output_path, 'wb') as out_f:
                            with open(os.path.join(temp_dir, sorted(pdfs)[0]), 'rb') as in_f:
                                out_f.write(in_f.read())
                        print(f"\nArquivo PDF (parcial) gerado: {output_path}")
            except Exception as e:
                print(f"Erro ao combinar PDFs: {str(e)}")
        
        else:
            print("Nenhum arquivo PDF gerado para combinar.")
    
    finally:
        # Limpar arquivos temporários
        print(f"\nLimpando diretório temporário: {temp_dir}")
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    return 0

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Uso: python3 api_pdf_completo.py NUMERO_PROCESSO")
        sys.exit(1)
    
    num_processo = sys.argv[1]
    sys.exit(main(num_processo))
#!/usr/bin/env python3
"""
Script para iniciar a aplicação Flask diretamente.
"""
import os
import sys

print("=" * 80)
print("Iniciando aplicação Flask diretamente")
print("Não foi possível usar o Gunicorn, iniciando com o módulo nativo do Flask")
print("=" * 80)

try:
    # Tentar importar Flask
    from flask import Flask
    print("Flask está instalado!")
except ImportError:
    print("Flask não está instalado no ambiente.")
    print("Tentando executar sem o Flask...")
    
    # Print instruções para script standalone
    print("\nVocê pode usar o script standalone para processar arquivos sem o servidor Flask:")
    print("./api_standalone.py NUMERO_PROCESSO [ARQUIVO_SAIDA] [CPF] [SENHA]")
    print("\nExemplo:")
    print("./api_standalone.py 12345678920210801001 output.pdf seu_cpf sua_senha")
    
    sys.exit(1)

# Tentar iniciar a aplicação
try:
    from app import app
    
    print("\nIniciando aplicação...")
    
    # Verificar se estamos no Replit
    if 'REPL_ID' in os.environ:
        app.run(host='0.0.0.0', port=5000, debug=True)
    else:
        app.run(host='127.0.0.1', port=5000, debug=True)
        
except Exception as e:
    print(f"Erro ao iniciar a aplicação: {e}")
    print("\nComo alternativa, você pode usar o script standalone:")
    print("./api_standalone.py NUMERO_PROCESSO [ARQUIVO_SAIDA] [CPF] [SENHA]")
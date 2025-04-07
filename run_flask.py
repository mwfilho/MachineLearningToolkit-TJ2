#!/usr/bin/env python3
"""
Script para iniciar o servidor Flask diretamente sem o Gunicorn.
Use este script quando o Gunicorn não estiver disponível no ambiente.
"""

from app import app

if __name__ == '__main__':
    print("=== Iniciando servidor Flask (sem Gunicorn) ===")
    print("Acessível em: http://127.0.0.1:5000")
    print("Para gerar um PDF completo, envie uma requisição para:")
    print("GET /api/v1/processo/{numero_processo}/pdf-completo")
    print("Forneça as credenciais MNI nos headers X-MNI-CPF e X-MNI-SENHA")
    print("=============================================")
    app.run(host='0.0.0.0', port=5000, debug=True)
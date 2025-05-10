#!/usr/bin/env python3
import os
import sys
import psycopg2
from urllib.parse import urlparse

def test_db_connection():
    """
    Testa a conexão com o banco de dados PostgreSQL.
    
    Este script deve ser executado antes de fazer deploy da aplicação para
    verificar se as credenciais do banco de dados estão corretas.
    """
    # Obter URL do banco de dados da variável de ambiente
    db_url = os.environ.get("DATABASE_URL")
    
    if not db_url:
        print("Erro: Variável de ambiente DATABASE_URL não está definida.")
        sys.exit(1)
    
    print(f"Testando conexão com: {db_url.replace('://', '://***:***@')}")
    
    try:
        # Parse da URL
        result = urlparse(db_url)
        username = result.username
        password = result.password
        database = result.path[1:]
        hostname = result.hostname
        port = result.port or 5432
        
        # Conectar ao banco de dados
        conn = psycopg2.connect(
            database=database,
            user=username,
            password=password,
            host=hostname,
            port=port
        )
        
        # Criar um cursor
        cursor = conn.cursor()
        
        # Verificar versão do PostgreSQL
        cursor.execute("SELECT version();")
        db_version = cursor.fetchone()
        
        print("Conexão com o banco de dados PostgreSQL estabelecida com sucesso!")
        print(f"Versão do PostgreSQL: {db_version[0]}")
        
        # Fechar o cursor e a conexão
        cursor.close()
        conn.close()
        print("Conexão com PostgreSQL fechada.")
        
    except Exception as e:
        print(f"Erro ao conectar ao banco de dados PostgreSQL: {e}")
        sys.exit(1)

if __name__ == "__main__":
    test_db_connection()
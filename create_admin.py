#!/usr/bin/env python3
import os
import sys
import getpass
from app import app, db
from models import User

def create_admin_user(username, password, force=False):
    """
    Cria um usuário administrador no banco de dados.
    
    Args:
        username (str): Nome de usuário para o admin
        password (str): Senha para o admin
        force (bool): Se True, sobrescreve usuário existente
    """
    with app.app_context():
        # Verificar se já existe um usuário com este nome
        existing_user = User.query.filter_by(username=username).first()
        
        if existing_user and not force:
            print(f"Um usuário com o nome '{username}' já existe.")
            return False
        
        if existing_user and force:
            # Atualizar usuário existente
            existing_user.set_password(password)
            existing_user.is_admin = True
            db.session.commit()
            print(f"Usuário '{username}' atualizado com sucesso!")
            return True
        
        # Criar novo usuário admin
        user = User(username=username, is_admin=True)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        print(f"Usuário admin '{username}' criado com sucesso!")
        return True

if __name__ == "__main__":
    print("Criar usuário administrador")
    print("--------------------------")
    
    if len(sys.argv) >= 3:
        # Argumentos fornecidos via linha de comando
        username = sys.argv[1]
        password = sys.argv[2]
        force = len(sys.argv) > 3 and sys.argv[3].lower() == 'force'
    else:
        # Solicitar interativamente
        username = input("Nome de usuário: ")
        password = getpass.getpass("Senha: ")
        confirm = getpass.getpass("Confirme a senha: ")
        
        if password != confirm:
            print("As senhas não coincidem!")
            sys.exit(1)
        
        force_input = input("Sobrescrever usuário existente? (s/N): ")
        force = force_input.lower() in ('s', 'sim', 'y', 'yes')
    
    if not username or not password:
        print("Usuário e senha são obrigatórios!")
        sys.exit(1)
    
    success = create_admin_user(username, password, force)
    if not success:
        print("Falha ao criar usuário admin!")
        sys.exit(1)
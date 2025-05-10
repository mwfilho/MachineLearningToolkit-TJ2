from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from models import User, ApiKey, db

auth = Blueprint('auth', __name__)

@auth.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('web.index'))

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()

        if user is None or not user.check_password(password):
            flash('Usuário ou senha inválidos', 'error')
            return redirect(url_for('auth.login'))

        login_user(user)
        next_page = request.args.get('next')
        if not next_page or next_page.startswith('//'):
            next_page = url_for('web.index')
        return redirect(next_page)

    return render_template('auth/login.html')

@auth.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('web.index'))

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        if User.query.filter_by(username=username).first():
            flash('Este usuário já existe', 'error')
            return redirect(url_for('auth.register'))

        user = User()
        user.username = username
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        flash('Registro realizado com sucesso!', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/register.html')

@auth.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('web.index'))

@auth.route('/api-keys', methods=['GET'])
@login_required
def list_api_keys():
    """Lista todas as API keys do usuário atual"""
    can_create = current_user.is_admin or current_user.can_create_api_keys
    return render_template('auth/api_keys.html', 
                          api_keys=current_user.get_api_keys(),
                          can_create=can_create)

@auth.route('/api-keys/create', methods=['POST'])
@login_required
def create_api_key():
    """Cria uma nova API key para o usuário"""
    # Verificar se o usuário tem permissão para criar API keys
    if not (current_user.is_admin or current_user.can_create_api_keys):
        flash('Você não tem permissão para criar API keys. Entre em contato com um administrador.', 'error')
        return redirect(url_for('auth.list_api_keys'))
        
    description = request.form.get('description', '')
    new_key = current_user.generate_api_key(description)
    flash('Nova API key criada com sucesso', 'success')
    # Este é o único momento em que a chave completa é mostrada
    return render_template('auth/api_key_created.html', api_key=new_key)

@auth.route('/api-keys/<int:key_id>/revoke', methods=['POST'])
@login_required
def revoke_api_key(key_id):
    """Revoga (desativa) uma API key"""
    key = ApiKey.query.get_or_404(key_id)
    
    # Verificar se a key pertence ao usuário atual
    if key.user_id != current_user.id:
        flash('Você não tem permissão para revogar esta API key', 'error')
        return redirect(url_for('auth.list_api_keys'))
    
    key.is_active = False
    db.session.commit()
    
    flash('API key revogada com sucesso', 'success')
    return redirect(url_for('auth.list_api_keys'))

# Funções de administração
def admin_required(f):
    """Decorator para exigir permissão de administrador"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('Acesso negado. Você precisa ser administrador para acessar esta página.', 'error')
            return redirect(url_for('web.index'))
        return f(*args, **kwargs)
    return decorated_function

@auth.route('/admin', methods=['GET'])
@login_required
@admin_required
def admin_panel():
    """Painel de administração"""
    users = User.query.all()
    all_api_keys = ApiKey.query.all()
    return render_template('auth/admin.html', users=users, all_api_keys=all_api_keys)

@auth.route('/admin/user/<int:user_id>/toggle-api-permission', methods=['POST'])
@login_required
@admin_required
def toggle_api_permission(user_id):
    """Alterna a permissão de criação de API keys de um usuário"""
    user = User.query.get_or_404(user_id)
    
    # Não permitir que um administrador remova sua própria permissão
    if user.is_admin and user.id == current_user.id:
        flash('Você não pode remover suas próprias permissões de administrador.', 'error')
        return redirect(url_for('auth.admin_panel'))
    
    user.can_create_api_keys = not user.can_create_api_keys
    db.session.commit()
    
    action = "concedida" if user.can_create_api_keys else "removida"
    flash(f'Permissão para criar API keys {action} para o usuário {user.username}', 'success')
    return redirect(url_for('auth.admin_panel'))

@auth.route('/admin/user/<int:user_id>/toggle-admin', methods=['POST'])
@login_required
@admin_required
def toggle_admin(user_id):
    """Alterna o status de administrador de um usuário"""
    user = User.query.get_or_404(user_id)
    
    # Não permitir que um administrador se remova como administrador
    if user.id == current_user.id:
        flash('Você não pode alterar seu próprio status de administrador.', 'error')
        return redirect(url_for('auth.admin_panel'))
    
    user.is_admin = not user.is_admin
    db.session.commit()
    
    action = "concedido" if user.is_admin else "removido"
    flash(f'Status de administrador {action} para o usuário {user.username}', 'success')
    return redirect(url_for('auth.admin_panel'))

@auth.route('/admin/api-key/<int:key_id>/revoke', methods=['POST'])
@login_required
@admin_required
def admin_revoke_api_key(key_id):
    """Revoga (desativa) uma API key por um administrador"""
    key = ApiKey.query.get_or_404(key_id)
    
    key.is_active = False
    db.session.commit()
    
    flash(f'API key #{key_id} do usuário {key.user.username} revogada com sucesso', 'success')
    return redirect(url_for('auth.admin_panel'))
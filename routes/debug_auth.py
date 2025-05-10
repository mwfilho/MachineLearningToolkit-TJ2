from flask import Blueprint, request, jsonify
from flask_login import current_user, login_required
import logging

logger = logging.getLogger(__name__)

debug_auth = Blueprint('debug_auth', __name__)

@debug_auth.route('/auth_status')
def auth_status():
    """Rota para testar o status de autenticação"""
    is_authenticated = current_user.is_authenticated
    user_info = None
    
    logger.debug(f"Status de autenticação: {is_authenticated}")
    
    if is_authenticated:
        user_info = {
            'id': current_user.id,
            'username': current_user.username,
            'is_admin': getattr(current_user, 'is_admin', False)
        }
        logger.debug(f"Usuário autenticado: {user_info}")
    
    return jsonify({
        'authenticated': is_authenticated,
        'user': user_info
    })

@debug_auth.route('/protected_test')
@login_required
def protected_test():
    """Rota protegida para testar o login_required"""
    logger.debug("Acessando rota protegida de teste")
    return jsonify({
        'success': True,
        'message': 'Você está autenticado!',
        'user': {
            'id': current_user.id,
            'username': current_user.username,
            'is_admin': getattr(current_user, 'is_admin', False)
        }
    })
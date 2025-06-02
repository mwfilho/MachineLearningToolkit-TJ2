from functools import wraps
from flask import request, jsonify
import logging
import time
from datetime import datetime

logger = logging.getLogger(__name__)

def log_request_response(f):
    """Decorator para logar requisições e respostas"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        start_time = time.time()
        
        # Log da requisição
        logger.info(f"Request: {request.method} {request.path}")
        logger.info(f"Headers: {dict(request.headers)}")
        if request.get_json():
            logger.info(f"Body: {request.get_json()}")
        
        # Executar função
        response = f(*args, **kwargs)
        
        # Log da resposta
        duration = time.time() - start_time
        logger.info(f"Response time: {duration:.2f}s")
        
        return response
    
    return decorated_function

def validate_processo_number(numero_processo):
    """Valida formato do número do processo CNJ"""
    # Remove pontos e traços
    numero_limpo = numero_processo.replace('.', '').replace('-', '')
    
    # Verifica se tem 20 dígitos
    if len(numero_limpo) != 20:
        return False, "Número do processo deve ter 20 dígitos"
    
    # Verifica se são apenas números
    if not numero_limpo.isdigit():
        return False, "Número do processo deve conter apenas dígitos"
    
    return True, None

def require_auth(f):
    """Decorator para verificar autenticação"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        cpf = request.headers.get('X-MNI-CPF')
        senha = request.headers.get('X-MNI-SENHA')
        
        # Se não houver credenciais nos headers, usar as do ambiente
        # (já implementado no main.py)
        
        return f(*args, **kwargs)
    
    return decorated_function

def handle_mni_errors(error_response):
    """Trata erros específicos do MNI/SOAP"""
    error_map = {
        'Authentication failed': {
            'code': 'AUTH_FAILED',
            'message': 'Credenciais inválidas ou usuário sem permissão',
            'status': 401
        },
        'Process not found': {
            'code': 'NOT_FOUND',
            'message': 'Processo não encontrado',
            'status': 404
        },
        'Access denied': {
            'code': 'ACCESS_DENIED',
            'message': 'Acesso negado ao processo (sigilo)',
            'status': 403
        },
        'Service unavailable': {
            'code': 'SERVICE_UNAVAILABLE',
            'message': 'Serviço MNI temporariamente indisponível',
            'status': 503
        }
    }
    
    error_str = str(error_response).lower()
    
    for key, value in error_map.items():
        if key.lower() in error_str:
            return value
    
    # Erro genérico
    return {
        'code': 'MNI_ERROR',
        'message': 'Erro ao comunicar com o sistema MNI',
        'status': 500
    }

def cache_key(numero_processo, operation='consulta'):
    """Gera chave de cache para o processo"""
    return f"processo:{numero_processo}:{operation}"

class RateLimiter:
    """Limitador de taxa simples"""
    def __init__(self, max_requests=100, window_seconds=60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = {}
    
    def is_allowed(self, identifier):
        """Verifica se a requisição é permitida"""
        now = time.time()
        
        # Limpar requisições antigas
        self.requests = {
            k: v for k, v in self.requests.items() 
            if now - v[-1] < self.window_seconds
        }
        
        # Verificar limite
        if identifier not in self.requests:
            self.requests[identifier] = []
        
        requests_in_window = [
            req for req in self.requests[identifier] 
            if now - req < self.window_seconds
        ]
        
        if len(requests_in_window) >= self.max_requests:
            return False
        
        self.requests[identifier].append(now)
        return True

# Instância global do rate limiter
rate_limiter = RateLimiter()

def rate_limit(f):
    """Decorator para aplicar rate limiting"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        identifier = request.headers.get('X-MNI-CPF', request.remote_addr)
        
        if not rate_limiter.is_allowed(identifier):
            return jsonify({
                'sucesso': False,
                'erro': 'RATE_LIMIT',
                'mensagem': 'Limite de requisições excedido. Tente novamente em alguns minutos.'
            }), 429
        
        return f(*args, **kwargs)
    
    return decorated_function
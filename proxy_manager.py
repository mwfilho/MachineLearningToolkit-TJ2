"""
Módulo de gerenciamento de proxies para contornar bloqueios de API.

Este módulo oferece:
1. Rotação de IPs/proxies para evitar bloqueios por limitação de taxa
2. Implementação de retry com exponential backoff
3. Cache de respostas para reduzir o número de chamadas à API

Autor: Sistema de Consulta MNI
"""

import os
import time
import random
import logging
import hashlib
import requests
from requests.packages.urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter
from functools import wraps
from datetime import datetime, timedelta
import json
import tempfile

# Configurando o logger
logger = logging.getLogger(__name__)

# Diretório para cache de arquivos
CACHE_DIR = os.path.join(tempfile.gettempdir(), 'mni_cache')
os.makedirs(CACHE_DIR, exist_ok=True)

# Tempo máximo de cache em segundos (24 horas)
DEFAULT_CACHE_TTL = 24 * 60 * 60

# Lista de proxies disponíveis
# Formato: {"http": "http://user:pass@ip:port", "https": "https://user:pass@ip:port"}
PROXIES = []

# Adicionar proxies do ambiente se disponíveis
if os.environ.get('PROXY_LIST'):
    try:
        PROXIES = json.loads(os.environ.get('PROXY_LIST'))
    except Exception as e:
        logger.error(f"Erro ao carregar lista de proxies do ambiente: {str(e)}")

# Status dos proxies {proxy_url: {'fail_count': 0, 'last_fail': datetime, 'banned_until': datetime}}
PROXY_STATUS = {}

# Máximo de falhas antes de banir um proxy temporariamente
MAX_FAILURES = 3

# Tempo de ban em minutos após atingir MAX_FAILURES
BAN_TIME_MINUTES = 30

class ProxySession(requests.Session):
    """Sessão com suporte a proxy, retry e cache"""
    
    def __init__(self, cache_ttl=DEFAULT_CACHE_TTL, use_proxy=True, retries=3, backoff_factor=0.3):
        super().__init__()
        self.cache_ttl = cache_ttl
        self.use_proxy = use_proxy
        
        # Configurar política de retry
        retry_strategy = Retry(
            total=retries,
            backoff_factor=backoff_factor,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "POST", "PUT", "DELETE", "OPTIONS", "TRACE"]
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.mount("http://", adapter)
        self.mount("https://", adapter)
        
        # Atualizar proxy se necessário
        if self.use_proxy:
            self.update_proxy()
    
    def update_proxy(self):
        """Seleciona um proxy disponível da lista e atualiza a sessão"""
        if not PROXIES:
            logger.warning("Nenhum proxy disponível para uso")
            self.proxies = None
            return
        
        available_proxies = [p for p in PROXIES if self._is_proxy_available(p)]
        
        if not available_proxies:
            logger.warning("Todos os proxies estão banidos ou indisponíveis! Usando conexão direta.")
            self.proxies = None
            return
        
        # Escolhe um proxy aleatório entre os disponíveis
        proxy = random.choice(available_proxies)
        logger.debug(f"Usando proxy: {self._mask_proxy_credentials(proxy)}")
        self.proxies = proxy
    
    def _is_proxy_available(self, proxy):
        """Verifica se um proxy está disponível para uso"""
        proxy_url = proxy.get('http') or proxy.get('https')
        if not proxy_url:
            return False
            
        status = PROXY_STATUS.get(proxy_url, {})
        
        # Se o proxy estiver banido temporariamente, verifica se o tempo já passou
        if status.get('banned_until') and status['banned_until'] > datetime.now():
            return False
        
        # Proxy está disponível
        return True
    
    def _mask_proxy_credentials(self, proxy):
        """Mascara credenciais nos logs por segurança"""
        masked = {}
        for protocol, url in proxy.items():
            if '@' in url:
                parts = url.split('@')
                auth_part = parts[0].split('//')[-1]
                if ':' in auth_part:
                    username = auth_part.split(':')[0]
                    masked[protocol] = url.replace(auth_part, f"{username}:****")
                else:
                    masked[protocol] = url
            else:
                masked[protocol] = url
        return masked
    
    def _report_proxy_failure(self, proxy_url):
        """Registra falha de proxy e bane temporariamente se necessário"""
        if not proxy_url:
            return
            
        if proxy_url not in PROXY_STATUS:
            PROXY_STATUS[proxy_url] = {'fail_count': 0, 'last_fail': None, 'banned_until': None}
            
        status = PROXY_STATUS[proxy_url]
        status['fail_count'] += 1
        status['last_fail'] = datetime.now()
        
        if status['fail_count'] >= MAX_FAILURES:
            status['banned_until'] = datetime.now() + timedelta(minutes=BAN_TIME_MINUTES)
            status['fail_count'] = 0
            logger.warning(f"Proxy {proxy_url} banido temporariamente até {status['banned_until']}")
    
    def _report_proxy_success(self, proxy_url):
        """Registra sucesso de proxy e reseta contador de falhas"""
        if not proxy_url or proxy_url not in PROXY_STATUS:
            return
            
        status = PROXY_STATUS[proxy_url]
        if status['fail_count'] > 0:
            status['fail_count'] = max(0, status['fail_count'] - 1)
    
    def _get_cache_key(self, method, url, data=None, params=None):
        """Gera uma chave única para o cache baseada na request"""
        # Combina os parâmetros para gerar um hash
        key_parts = [method.upper(), url]
        
        if params:
            key_parts.append(json.dumps(params, sort_keys=True))
        
        if data:
            if isinstance(data, bytes):
                key_parts.append(data.decode('utf-8', errors='ignore'))
            elif isinstance(data, str):
                key_parts.append(data)
            else:
                key_parts.append(json.dumps(data, sort_keys=True))
                
        key_string = '|'.join(str(p) for p in key_parts)
        return hashlib.md5(key_string.encode('utf-8')).hexdigest()
    
    def _get_cache_path(self, cache_key):
        """Retorna o caminho do arquivo de cache para uma determinada chave"""
        return os.path.join(CACHE_DIR, f"{cache_key}.cache")
    
    def _is_cache_valid(self, cache_path):
        """Verifica se o cache é válido (existe e não expirou)"""
        if not os.path.exists(cache_path):
            return False
            
        # Verifica a idade do arquivo
        file_time = os.path.getmtime(cache_path)
        age = time.time() - file_time
        
        return age < self.cache_ttl
    
    def _save_response_to_cache(self, cache_path, response):
        """Salva a resposta no cache"""
        try:
            with open(cache_path, 'wb') as f:
                # Salvamos apenas o conteúdo, não o objeto response completo
                f.write(response.content)
            logger.debug(f"Resposta salva em cache: {cache_path}")
        except Exception as e:
            logger.error(f"Erro ao salvar cache: {str(e)}")
    
    def _load_response_from_cache(self, cache_path, original_request):
        """Carrega a resposta do cache"""
        try:
            with open(cache_path, 'rb') as f:
                content = f.read()
                
            # Criamos uma resposta sintética
            response = requests.Response()
            response.status_code = 200
            response._content = content
            response.request = original_request
            response.url = original_request.url
            response.headers['X-Cache'] = 'HIT'
            
            logger.debug(f"Resposta carregada do cache: {cache_path}")
            return response
        except Exception as e:
            logger.error(f"Erro ao carregar cache: {str(e)}")
            return None
    
    def request(self, method, url, *args, use_cache=True, **kwargs):
        """
        Sobrescreve o método request para adicionar funcionalidades de proxy, retry e cache
        
        Args:
            method: Método HTTP (GET, POST, etc)
            url: URL da requisição
            use_cache: Se True, tenta usar o cache (default: True)
            *args, **kwargs: Argumentos passados para requests.Session.request
            
        Returns:
            Response: Objeto de resposta do requests
        """
        # Gerar chave de cache
        cache_key = None
        cache_path = None
        
        # Só usa cache para GETs ou POSTs específicos (configurável)
        cacheable = method.upper() == 'GET' or (
            method.upper() == 'POST' and kwargs.get('headers', {}).get('X-Allow-Cache') == 'true'
        )
        
        if use_cache and cacheable:
            cache_key = self._get_cache_key(method, url, 
                                           kwargs.get('data'), 
                                           kwargs.get('params'))
            cache_path = self._get_cache_path(cache_key)
            
            # Verifica o cache
            if self._is_cache_valid(cache_path):
                # Cria um objeto Request para passar ao método _load_response_from_cache
                original_request = requests.Request(
                    method=method, 
                    url=url, 
                    headers=kwargs.get('headers', {}),
                    data=kwargs.get('data'),
                    params=kwargs.get('params')
                ).prepare()
                
                cached_response = self._load_response_from_cache(cache_path, original_request)
                if cached_response:
                    return cached_response
        
        # Preparar para fazer a requisição real
        max_attempts = 3
        attempt = 0
        
        while attempt < max_attempts:
            attempt += 1
            
            # Atualiza o proxy a cada tentativa se necessário
            if self.use_proxy and attempt > 1:
                self.update_proxy()
            
            try:
                # Tenta fazer a requisição
                response = super().request(method, url, *args, **kwargs)
                
                # Se for bem sucedido, reporte o sucesso do proxy (se estiver usando)
                if self.proxies:
                    proxy_url = self.proxies.get('http') or self.proxies.get('https')
                    self._report_proxy_success(proxy_url)
                
                # Se a requisição foi bem sucedida, salva no cache (se aplicável)
                if response.status_code == 200 and cache_path and cacheable:
                    self._save_response_to_cache(cache_path, response)
                
                return response
                
            except (requests.RequestException, Exception) as e:
                # Registrar a falha do proxy (se estiver usando)
                if self.proxies:
                    proxy_url = self.proxies.get('http') or self.proxies.get('https')
                    self._report_proxy_failure(proxy_url)
                
                logger.warning(f"Tentativa {attempt}/{max_attempts} falhou: {str(e)}")
                
                # Se for a última tentativa, propaga a exceção
                if attempt >= max_attempts:
                    raise
                
                # Espera um tempo antes de tentar novamente (pode incorporar exponential backoff aqui)
                wait_time = 2 ** attempt  # Implementação simples de backoff exponencial
                logger.debug(f"Aguardando {wait_time}s antes da próxima tentativa")
                time.sleep(wait_time)


def with_proxy_session(use_cache=True, use_proxy=True, retries=3, backoff_factor=0.3, cache_ttl=DEFAULT_CACHE_TTL):
    """
    Decorator para usar ProxySession em funções que fazem requisições HTTP.
    
    Args:
        use_cache: Se True, utiliza cache (default: True)
        use_proxy: Se True, utiliza proxies (default: True)
        retries: Número de retentativas para erros 429/5xx (default: 3)
        backoff_factor: Fator para backoff exponencial (default: 0.3)
        cache_ttl: Tempo de vida do cache em segundos (default: 24h)
        
    Exemplo de uso:
        @with_proxy_session(use_cache=True, use_proxy=True)
        def fetch_data(url, session=None):
            return session.get(url)
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Cria uma sessão de proxy se não foi fornecida
            session = kwargs.pop('session', None) or ProxySession(
                cache_ttl=cache_ttl,
                use_proxy=use_proxy,
                retries=retries,
                backoff_factor=backoff_factor
            )
            
            # Se a função requer um argumento session, passa a sessão
            kwargs['session'] = session
            
            # Define o uso de cache para essa chamada específica
            kwargs['use_cache'] = use_cache
            
            return func(*args, **kwargs)
        return wrapper
    return decorator


def clear_proxy_cache(older_than_hours=None):
    """
    Limpa o cache de respostas.
    
    Args:
        older_than_hours: Se definido, remove apenas cache mais antigo que X horas
    """
    try:
        count = 0
        now = time.time()
        
        for filename in os.listdir(CACHE_DIR):
            if not filename.endswith('.cache'):
                continue
                
            filepath = os.path.join(CACHE_DIR, filename)
            
            # Se older_than_hours está definido, verifica a idade do arquivo
            if older_than_hours:
                file_time = os.path.getmtime(filepath)
                age_hours = (now - file_time) / 3600
                
                if age_hours < older_than_hours:
                    continue
            
            # Remove o arquivo
            os.remove(filepath)
            count += 1
        
        logger.info(f"Limpeza de cache concluída. {count} arquivos removidos.")
        return count
    except Exception as e:
        logger.error(f"Erro ao limpar cache: {str(e)}")
        return 0


def add_proxy(proxy_url, protocol='http'):
    """
    Adiciona um proxy à lista de proxies disponíveis.
    
    Args:
        proxy_url: URL do proxy no formato user:pass@ip:port
        protocol: Protocolo (http ou https)
    """
    if not proxy_url.startswith(f"{protocol}://"):
        proxy_url = f"{protocol}://{proxy_url}"
    
    new_proxy = {protocol: proxy_url}
    
    # Adiciona o proxy se ainda não existir
    if new_proxy not in PROXIES:
        PROXIES.append(new_proxy)
        logger.info(f"Proxy adicionado: {proxy_url.split('@')[-1]}")
        return True
    
    return False


def load_proxies_from_file(filepath):
    """
    Carrega proxies de um arquivo.
    
    Formato esperado (uma linha por proxy):
    http://user:pass@ip:port
    https://ip:port
    user:pass@ip:port
    """
    if not os.path.exists(filepath):
        logger.error(f"Arquivo de proxies não encontrado: {filepath}")
        return 0
    
    count = 0
    with open(filepath, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
                
            # Determina o protocolo com base na URL
            if line.startswith('http://'):
                add_proxy(line, 'http')
            elif line.startswith('https://'):
                add_proxy(line, 'https')
            else:
                # Assume http se não especificado
                add_proxy(line, 'http')
            
            count += 1
    
    logger.info(f"{count} proxies carregados do arquivo")
    return count


def reset_banned_proxies():
    """Reseta todos os proxies banidos"""
    count = 0
    for proxy_url, status in PROXY_STATUS.items():
        if status.get('banned_until'):
            status['banned_until'] = None
            status['fail_count'] = 0
            count += 1
    
    logger.info(f"{count} proxies foram desbloqueados")
    return count
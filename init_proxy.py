#!/usr/bin/env python3
"""
Inicialização do sistema de proxy para o MNI.

Este módulo carrega os proxies a partir de um arquivo e configura o ambiente.
"""

import os
import logging
import json
from proxy_manager import load_proxies_from_file, add_proxy, clear_proxy_cache, PROXIES

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def init_proxy_system():
    """Inicializa o sistema de proxy"""
    
    logger.info("Inicializando sistema de proxy para MNI")
    
    # Limpar o cache antigo (mais de 24h)
    cache_cleared = clear_proxy_cache(older_than_hours=24)
    logger.info(f"Cache limpo: {cache_cleared} arquivos removidos")
    
    # Verificar variáveis de ambiente para lista de proxies
    proxy_env = os.environ.get('PROXY_LIST')
    if proxy_env:
        try:
            proxy_list = json.loads(proxy_env)
            for proxy in proxy_list:
                if isinstance(proxy, dict):
                    for protocol, url in proxy.items():
                        add_proxy(url, protocol)
                else:
                    # Assume HTTP se não for dict
                    add_proxy(proxy)
            logger.info(f"Carregados {len(proxy_list)} proxies da variável de ambiente PROXY_LIST")
        except Exception as e:
            logger.error(f"Erro ao carregar proxies da variável de ambiente: {str(e)}")
    
    # Verificar arquivo de proxies
    proxy_file = os.path.join(os.path.dirname(__file__), 'proxies.txt')
    if os.path.exists(proxy_file):
        count = load_proxies_from_file(proxy_file)
        logger.info(f"Carregados {count} proxies do arquivo {proxy_file}")
    else:
        logger.warning(f"Arquivo de proxies não encontrado: {proxy_file}")
        # Criar arquivo de exemplo se não existir
        example_file = os.path.join(os.path.dirname(__file__), 'proxies.example.txt')
        if os.path.exists(example_file):
            logger.info(f"Arquivo de exemplo disponível em: {example_file}")
            logger.info("Copie-o para proxies.txt e adicione seus proxies")
    
    # Configurações adicionais do proxy
    use_proxy = os.environ.get('USE_PROXY', 'true').lower() in ('true', '1', 't', 'yes', 'y')
    use_cache = os.environ.get('USE_CACHE', 'true').lower() in ('true', '1', 't', 'yes', 'y')
    
    logger.info(f"Sistema de proxy configurado: use_proxy={use_proxy}, use_cache={use_cache}")
    logger.info(f"Total de proxies disponíveis: {len(PROXIES)}")
    
    return {
        'use_proxy': use_proxy,
        'use_cache': use_cache,
        'proxy_count': len(PROXIES)
    }
    
if __name__ == "__main__":
    init_result = init_proxy_system()
    print(f"Inicialização do sistema de proxy: {init_result}")
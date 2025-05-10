# Sistema de Proxy para API MNI

Este documento descreve o sistema de proxy implementado para contornar bloqueios na API do PJe/MNI.

## Visão Geral

O sistema de proxy foi desenvolvido para:

1. **Rotacionar IPs/servidores proxy** para evitar bloqueios por limitação de taxa
2. **Implementar mecanismos de retry** com exponential backoff para lidar com falhas temporárias
3. **Caching de respostas** para reduzir o número de chamadas à API
4. **Deteção e banimento automático** de proxies problemáticos
5. **Tratamento robusto de erros** para garantir a continuidade da operação

## Componentes Principais

### 1. ProxySession

Classe que estende `requests.Session` para adicionar funcionalidades de proxy, retry e cache:

```python
from proxy_manager import ProxySession

# Criação básica
session = ProxySession(
    cache_ttl=24*60*60,  # 24 horas
    use_proxy=True,      # Habilita uso de proxies
    retries=3,           # Número de tentativas em caso de falha
    backoff_factor=0.5   # Fator para backoff exponencial
)

# Uso como uma sessão requests normal
response = session.get('https://api.example.com/endpoint')
```

### 2. Decorador @with_proxy_session

Um decorador que facilita o uso de `ProxySession` em funções existentes:

```python
from proxy_manager import with_proxy_session

@with_proxy_session(use_cache=True, use_proxy=True)
def fetch_data(url, session=None):
    return session.get(url)
```

### 3. Gerenciamento de Proxies

O sistema mantém uma lista de proxies disponíveis e monitora seu desempenho, banindo temporariamente aqueles que apresentam falhas consecutivas.

### 4. Cache de Respostas

As respostas são armazenadas em cache no sistema de arquivos para reduzir o número de chamadas à API.

## Configuração

### 1. Arquivo de Proxies

Crie um arquivo `proxies.txt` no diretório raiz do projeto com a lista de proxies:

```
# Formato: [protocolo://][usuário:senha@]ip:porta
http://user:pass@12.34.56.78:8080
https://12.34.56.78:8080
user:pass@12.34.56.78:8080
```

### 2. Variáveis de Ambiente

O sistema também pode ser configurado através de variáveis de ambiente:

- `PROXY_LIST`: Lista de proxies em formato JSON
- `USE_PROXY`: "true" para habilitar o uso de proxies (padrão: true)
- `USE_CACHE`: "true" para habilitar o cache (padrão: true)

Exemplo de `PROXY_LIST`:
```
export PROXY_LIST='[{"http":"http://user:pass@12.34.56.78:8080"}, {"https":"https://12.34.56.78:8080"}]'
```

## Uso nas Funções MNI

O sistema de proxy foi integrado às seguintes funções:

- `extrair_ids_requests_lxml`: Para extração de IDs de documentos

```python
# Exemplo de uso
from funcoes_mni import extrair_ids_requests_lxml

# O decorador já adiciona a funcionalidade de proxy automaticamente
document_ids = extrair_ids_requests_lxml("0000000-00.0000.0.00.0000")
```

## Manutenção do Cache

O cache é limpo automaticamente durante a inicialização da aplicação, removendo entradas com mais de 24 horas. Você também pode limpar manualmente o cache:

```python
from proxy_manager import clear_proxy_cache

# Limpar todo o cache
clear_proxy_cache()

# Limpar apenas cache mais antigo que X horas
clear_proxy_cache(older_than_hours=12)
```

## Benefícios

1. **Maior Taxa de Sucesso**: Contorna limitações de taxa do PJe/MNI
2. **Resiliência**: O sistema tenta automaticamente outro proxy em caso de falha
3. **Desempenho**: Respostas em cache reduzem o tempo de resposta
4. **Economia de Recursos**: Menos chamadas à API significam menos consumo de recursos
5. **Manutenção Automática**: Proxies problemáticos são banidos automaticamente

## Solução de Problemas

### Verificar Status dos Proxies

```python
from proxy_manager import PROXY_STATUS
import pprint

# Verificar o status de todos os proxies
pprint.pprint(PROXY_STATUS)
```

### Resetar Proxies Banidos

```python
from proxy_manager import reset_banned_proxies

# Resetar todos os proxies banidos
reset_banned_proxies()
```

### Logs

Os logs do sistema de proxy são armazenados no mesmo local dos logs da aplicação principal e contêm informações detalhadas sobre as operações de proxy e cache.

## Limitações

1. O sistema não funciona para todas as funções da biblioteca `zeep` que fazem requests diretamente
2. O cache não funciona para respostas que incluem conteúdo binário grande (como documentos PDF)
3. É necessário fornecer sua própria lista de proxies

## Próximos Passos

- Integrar o sistema de proxy com as demais funções MNI
- Implementar rotação automática de proxies baseada em geolocalização
- Adicionar métricas de desempenho para cada proxy
- Desenvolver uma interface web para gerenciamento de proxies
import time
import threading
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)

class RateLimiter:
    """
    Implementa um limitador de taxa de requisições ao serviço MNI.
    Esta classe ajuda a evitar múltiplas requisições em curto período 
    que possam causar bloqueio de senha.
    """
    
    def __init__(self, max_calls=5, time_window=60):
        """
        Inicializa o limitador de taxa.
        
        Args:
            max_calls (int): Número máximo de chamadas permitidas no período
            time_window (int): Janela de tempo em segundos
        """
        self.max_calls = max_calls
        self.time_window = time_window
        self.calls = defaultdict(list)
        self.lock = threading.Lock()
        
    def can_make_request(self, key):
        """
        Verifica se é possível fazer uma requisição para um determinado recurso.
        
        Args:
            key (str): Identificador do recurso (geralmente CPF do consultante)
            
        Returns:
            bool: True se a requisição pode ser feita, False caso contrário
        """
        current_time = time.time()
        
        with self.lock:
            # Remover chamadas antigas (fora da janela de tempo)
            self.calls[key] = [timestamp for timestamp in self.calls[key] 
                              if current_time - timestamp < self.time_window]
            
            # Verificar se o limite foi atingido
            if len(self.calls[key]) >= self.max_calls:
                time_to_wait = self.time_window - (current_time - self.calls[key][0])
                logger.warning(f"Rate limit excedido para {key}. Aguarde {int(time_to_wait)} segundos.")
                return False
            
            # Registrar nova chamada
            self.calls[key].append(current_time)
            return True
            
    def get_wait_time(self, key):
        """
        Retorna o tempo de espera estimado até que uma nova requisição seja permitida.
        
        Args:
            key (str): Identificador do recurso
            
        Returns:
            float: Tempo em segundos até que uma nova requisição seja permitida
        """
        current_time = time.time()
        
        with self.lock:
            if not self.calls[key]:
                return 0
                
            if len(self.calls[key]) < self.max_calls:
                return 0
                
            return max(0, self.time_window - (current_time - self.calls[key][0]))

# Instância global do rate limiter
mni_rate_limiter = RateLimiter(max_calls=10, time_window=120)  # 10 chamadas por 2 minutos
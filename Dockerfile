FROM python:3.11-slim

WORKDIR /app

# Instalar dependências
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código fonte
COPY . .

# Variáveis de ambiente padrão
ENV PORT=8080
ENV PYTHONUNBUFFERED=1

# Expor a porta
EXPOSE $PORT

# Comando para iniciar a aplicação
CMD gunicorn --bind 0.0.0.0:$PORT main:app
# API de Consulta MNI - Sistema de Processamento de Documentos Judiciais

Este projeto é uma API para processamento avançado de documentos judiciais que utiliza o Modelo Nacional de Interoperabilidade (MNI) para consulta, análise e extração inteligente de documentos legais.

## Visão Geral

A API facilita a consulta e processamento de documentos judiciais através do MNI, com recursos avançados de:

- Consulta de processos judiciais
- Download de documentos específicos
- Extração e processamento de petições iniciais e seus anexos
- Obtenção de lista completa de IDs de documentos
- Consulta da capa do processo (dados básicos)

## Tecnologias

- **Backend**: Python com Flask
- **Interação com serviços SOAP**: Zeep
- **Processamento de XML**: lxml
- **Banco de dados**: PostgreSQL (com SQLAlchemy)
- **Sistema de proxy**: Proxy rotativo com cache e retry
- **Autenticação**: Flask-Login com controle de permissões
- **Servidor de produção**: Gunicorn

## Requisitos

- Python 3.11 ou superior
- PostgreSQL
- Credenciais de acesso ao MNI

## Instalação Local

### 1. Clone o repositório

```bash
git clone https://github.com/seu-usuario/api-mni.git
cd api-mni
```

### 2. Configure o ambiente virtual

```bash
python -m venv venv
source venv/bin/activate  # No Windows: venv\Scripts\activate
```

### 3. Instale as dependências

```bash
pip install -r requirements.txt
```

Se o arquivo `requirements.txt` não existir, você pode criá-lo a partir do `pyproject.toml` usando:

```bash
pip install -e .
# ou manualmente instalar as dependências:
pip install easydict email-validator flask flask-login flask-sqlalchemy gunicorn lxml pandas psycopg2-binary requests sqlalchemy trafilatura werkzeug zeep
```

### 4. Configure as variáveis de ambiente

Crie um arquivo `.env` na raiz do projeto com o seguinte conteúdo:

```
# Credenciais MNI
MNI_URL=https://pjews.tjce.jus.br/pje1grau/intercomunicacao?wsdl
MNI_CONSULTA_URL=https://pjews.tjce.jus.br/pje1grau/ConsultaPJe?wsdl
MNI_ID_CONSULTANTE=seu_id_consultante
MNI_SENHA_CONSULTANTE=sua_senha_consultante

# Configuração do Flask
SECRET_KEY=chave_secreta_para_sessao
SESSION_SECRET=chave_secreta_para_sessao

# Configuração do Banco de Dados
DATABASE_URL=postgresql://usuario:senha@localhost:5432/nome_do_banco
```

### 5. Inicialize o banco de dados

O banco é criado automaticamente ao iniciar a aplicação, mas você precisa ter um servidor PostgreSQL rodando e acessível com as credenciais do `DATABASE_URL`.

### 6. Execute a aplicação

```bash
python main.py
# ou
gunicorn --bind 0.0.0.0:5000 --reuse-port --reload main:app
```

A aplicação estará disponível em `http://localhost:5000`

## Deploy no Google Cloud Run

Google Cloud Run é uma excelente opção para hospedar aplicações containerizadas sem se preocupar com a infraestrutura. Veja como fazer o deploy desta API:

### 1. Preparação Inicial

#### Instale e configure o Google Cloud SDK

1. Faça o download e instale o [Google Cloud SDK](https://cloud.google.com/sdk/docs/install)
2. Inicialize e faça login:
   ```bash
   gcloud init
   gcloud auth login
   ```
3. Configure o projeto:
   ```bash
   gcloud config set project SEU_ID_DO_PROJETO
   ```

#### Habilite as APIs necessárias

```bash
gcloud services enable cloudbuild.googleapis.com
gcloud services enable run.googleapis.com
gcloud services enable artifactregistry.googleapis.com
gcloud services enable secretmanager.googleapis.com
```

### 2. Configure um Dockerfile

Crie um arquivo `Dockerfile` na raiz do projeto:

```Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Instalar dependências
COPY pyproject.toml .
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
```

### 3. Crie o arquivo requirements.txt se não existir

```bash
pip install -e . --no-deps
pip freeze > requirements.txt
```

Ou crie manualmente com o conteúdo necessário:

```
easydict>=1.13
email-validator>=2.2.0
flask-login>=0.6.3
flask>=3.1.0
flask-sqlalchemy>=3.1.1
gunicorn>=23.0.0
pandas>=2.2.3
psycopg2-binary>=2.9.10
requests>=2.32.3
zeep>=4.3.1
werkzeug>=3.1.3
sqlalchemy>=2.0.39
trafilatura>=2.0.0
lxml>=5.3.1
```

### 4. Configure Secrets no Google Cloud

Configure os segredos necessários no Google Secret Manager para proteger suas credenciais:

```bash
# Crie os segredos
echo -n "valor_mni_id_consultante" | gcloud secrets create mni-id-consultante --data-file=-
echo -n "valor_mni_senha_consultante" | gcloud secrets create mni-senha-consultante --data-file=-
echo -n "valor_chave_secreta" | gcloud secrets create secret-key --data-file=-
echo -n "postgresql://usuario:senha@host:5432/banco" | gcloud secrets create database-url --data-file=-

# Dê permissão de acesso à conta de serviço do Cloud Run
gcloud secrets add-iam-policy-binding mni-id-consultante \
    --member="serviceAccount:PROJECT_NUMBER-compute@developer.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor"

# Repita o comando acima para os outros segredos
```

### 5. Configure um banco de dados PostgreSQL

Você pode usar o Cloud SQL do Google Cloud para seu banco PostgreSQL:

1. Crie uma instância PostgreSQL:
   ```bash
   gcloud sql instances create mni-database \
     --database-version=POSTGRES_13 \
     --tier=db-f1-micro \
     --region=us-central1
   ```

2. Crie um banco de dados:
   ```bash
   gcloud sql databases create mni-api-db --instance=mni-database
   ```

3. Crie um usuário:
   ```bash
   gcloud sql users create mni-app-user \
     --instance=mni-database \
     --password=SENHA_SEGURA
   ```

4. Obtenha a string de conexão:
   ```
   postgresql://mni-app-user:SENHA_SEGURA@/mni-api-db?host=/cloudsql/PROJECT_ID:REGION:mni-database
   ```

### 6. Deploy no Cloud Run

Agora você pode fazer o deploy da aplicação:

```bash
gcloud run deploy mni-api \
  --source . \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --update-secrets=MNI_ID_CONSULTANTE=mni-id-consultante:latest,MNI_SENHA_CONSULTANTE=mni-senha-consultante:latest,SECRET_KEY=secret-key:latest,DATABASE_URL=database-url:latest \
  --set-env-vars="MNI_URL=https://pjews.tjce.jus.br/pje1grau/intercomunicacao?wsdl,MNI_CONSULTA_URL=https://pjews.tjce.jus.br/pje1grau/ConsultaPJe?wsdl"
```

Se estiver usando Cloud SQL, adicione a flag:
```
--add-cloudsql-instances=PROJECT_ID:REGION:mni-database
```

### 7. Verifique o deploy

Após o deploy, você receberá a URL do serviço. Teste a API usando um cliente HTTP como curl:

```bash
curl https://seu-servico-url.a.run.app/api/v1/processo/NUMERO_DO_PROCESSO \
  -H "X-MNI-CPF: SEU_CPF" \
  -H "X-MNI-SENHA: SUA_SENHA"
```

### 8. Configure CI/CD (opcional)

Para automatizar o processo de deploy, você pode configurar um pipeline CI/CD usando o GitHub Actions.

Crie um arquivo `.github/workflows/deploy.yml`:

```yaml
name: Deploy to Cloud Run

on:
  push:
    branches:
      - main

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout code
        uses: actions/checkout@v3

      - name: Setup Google Cloud SDK
        uses: google-github-actions/setup-gcloud@v0.3.0
        with:
          project_id: ${{ secrets.GCP_PROJECT_ID }}
          service_account_key: ${{ secrets.GCP_SA_KEY }}
          export_default_credentials: true

      - name: Deploy to Cloud Run
        run: |
          gcloud run deploy mni-api \
            --source . \
            --platform managed \
            --region us-central1 \
            --allow-unauthenticated \
            --update-secrets=MNI_ID_CONSULTANTE=mni-id-consultante:latest,MNI_SENHA_CONSULTANTE=mni-senha-consultante:latest,SECRET_KEY=secret-key:latest,DATABASE_URL=database-url:latest \
            --set-env-vars="MNI_URL=https://pjews.tjce.jus.br/pje1grau/intercomunicacao?wsdl,MNI_CONSULTA_URL=https://pjews.tjce.jus.br/pje1grau/ConsultaPJe?wsdl"
```

## Uso da API

### Endpoints Disponíveis

- **GET /api/v1/processo/{num_processo}**: Retorna dados completos do processo
- **GET /api/v1/processo/{num_processo}/documento/{num_documento}**: Faz download de um documento específico
- **GET /api/v1/processo/{num_processo}/peticao-inicial**: Retorna a petição inicial e anexos
- **GET /api/v1/processo/{num_processo}/documentos/ids**: Lista todos os IDs de documentos
- **GET /api/v1/processo/{num_processo}/capa**: Retorna apenas os dados da capa do processo

### Interfaces de Depuração

A aplicação inclui interfaces de depuração protegidas por senha e restritas a usuários com permissões de administrador:

- **/debug**: Interface principal de depuração
- **/debug/consulta**: Consulta detalhada de processos
- **/debug/documento**: Visualização detalhada de documentos
- **/debug/peticao-inicial**: Análise de petições iniciais
- **/debug/documentos-ids**: Listagem completa de IDs de documentos
- **/debug/capa**: Visualização da capa do processo

Para mais detalhes sobre o sistema de autenticação, consulte o arquivo [AUTH_README.md](AUTH_README.md).

### Autenticação da API (MNI)

A API aceita credenciais MNI de duas formas:

1. **Via Headers HTTP**:
   ```
   X-MNI-CPF: seu_cpf_ou_cnpj
   X-MNI-SENHA: sua_senha
   ```

2. **Via Variáveis de Ambiente**:
   ```
   MNI_ID_CONSULTANTE=seu_cpf_ou_cnpj
   MNI_SENHA_CONSULTANTE=sua_senha
   ```

### Autenticação da Interface Web

Para acessar as interfaces de depuração, é necessário:

1. Fazer login com um usuário que possua a flag `is_admin=True`
2. Usuário padrão:
   - Username: `admin`
   - Senha: `senhasegura` (altere após o primeiro acesso)

Para criar ou modificar usuários administradores:

```bash
python create_admin.py <username> <password> [force]
```

## Monitoramento e Logs

No Google Cloud Run, você pode monitorar sua aplicação através do Cloud Logging:

```bash
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=mni-api" --limit=10
```

## Custos

O Google Cloud Run cobra apenas pelo tempo em que seus contêineres estão processando solicitações, arredondado para cima até os 100ms mais próximos. Há um nível gratuito generoso que inclui:

- 2 milhões de solicitações gratuitas por mês
- 360.000 GB-segundos de memória gratuitos
- 180.000 vCPU-segundos gratuitos

Para o banco de dados Cloud SQL, a instância db-f1-micro custa aproximadamente US$ 7-12 por mês.

## Suporte e Contribuições

Para relatar problemas ou contribuir com o projeto, abra uma issue ou pull request no repositório GitHub.

## Licença

[Especifique a licença do seu projeto]
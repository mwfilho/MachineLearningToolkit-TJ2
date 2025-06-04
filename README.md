# Sistema de Processamento de Documentos Judiciais

Sistema avançado para processamento de documentos judiciais com autenticação segura e controle de acesso baseado em funções.

## Funcionalidades

- Backend Flask Python com autenticação granular
- Banco de dados PostgreSQL com gerenciamento avançado de permissões
- Geração e revogação segura de chaves API
- Capacidades de análise XML para documentos legais complexos
- Sistema robusto de gerenciamento de sessões e permissões

## Tecnologias

- **Backend**: Python Flask
- **Banco de Dados**: PostgreSQL
- **Autenticação**: Flask-Login, JWT
- **Parsing XML**: lxml, zeep
- **Web Server**: Gunicorn

## Instalação

1. Clone o repositório:
```bash
git clone <seu-repositorio>
cd <nome-do-projeto>
```

2. Instale as dependências:
```bash
pip install -r requirements.txt
```

3. Configure as variáveis de ambiente:
```bash
cp .env.example .env
# Edite o arquivo .env com suas configurações
```

4. Execute as migrações do banco:
```bash
python -c "from app import app; from database import db; app.app_context().push(); db.create_all()"
```

5. Inicie o servidor:
```bash
python main.py
```

## Deploy

### Heroku

1. Crie um app no Heroku
2. Adicione o addon PostgreSQL
3. Configure as variáveis de ambiente
4. Faça deploy via Git

### Railway

1. Conecte seu repositório GitHub
2. Adicione um banco PostgreSQL
3. Configure as variáveis de ambiente

### Vercel

Para deploy no Vercel, use o arquivo `vercel.json` incluído.

## Variáveis de Ambiente

- `DATABASE_URL`: URL de conexão com PostgreSQL
- `SESSION_SECRET`: Chave secreta para sessões
- `MNI_ID_CONSULTANTE`: CPF ou CNPJ do consultante para a API MNI (opcional)
- `MNI_SENHA_CONSULTANTE`: Senha do consultante para a API MNI (opcional)

## API Endpoints

### Autenticação
- `POST /auth/login` - Login
- `POST /auth/register` - Registro
- `POST /auth/logout` - Logout

### API de Processos (requer API key)
- `GET /api/v1/processo/<num_processo>` - Dados completos do processo
- `GET /api/v1/processo/<num_processo>/capa` - Apenas dados da capa
- `GET /api/v1/processo/<num_processo>/documento/<doc_id>` - Download de documento
- `GET /api/v1/processo/<num_processo>/peticao-inicial` - Petição inicial e anexos

## Segurança

- Autenticação via Flask-Login
- API Keys para acesso programático
- Controle de acesso baseado em funções
- Validação de entrada e sanitização

## Licença

[Sua licença aqui]
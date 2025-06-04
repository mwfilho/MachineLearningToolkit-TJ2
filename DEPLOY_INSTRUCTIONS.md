# Instruções para Deploy no GitHub

## Passos para copiar o projeto para o GitHub

### 1. Preparar o repositório local
```bash
# No seu computador, crie um novo diretório
mkdir meu-projeto-judicial
cd meu-projeto-judicial

# Inicialize o git
git init
```

### 2. Copiar os arquivos do Replit
Baixe ou copie todos os arquivos do seu projeto Replit para o diretório local, exceto:
- `.replit`
- `replit.nix` 
- `requirements.txt` (use o `github-requirements.txt` como `requirements.txt`)

### 3. Renomear arquivo de dependências
```bash
# Renomeie o arquivo de dependências
mv github-requirements.txt requirements.txt
```

### 4. Configurar o repositório GitHub
```bash
# Adicione todos os arquivos
git add .

# Faça o primeiro commit
git commit -m "Initial commit: Sistema de processamento de documentos judiciais"

# Adicione o repositório remoto (substitua pela URL do seu repositório)
git remote add origin https://github.com/SEU_USUARIO/SEU_REPOSITORIO.git

# Envie para o GitHub
git push -u origin main
```

## Opções de Deploy

### Opção 1: Heroku (Recomendado)
1. Crie uma conta no Heroku
2. Instale o Heroku CLI
3. Configure:
```bash
heroku create seu-app-name
heroku addons:create heroku-postgresql:mini
heroku config:set SESSION_SECRET=sua-chave-secreta-aqui
git push heroku main
```

### Opção 2: Railway
1. Acesse railway.app
2. Conecte seu repositório GitHub
3. Adicione um banco PostgreSQL
4. Configure as variáveis de ambiente:
   - `DATABASE_URL` (automático com PostgreSQL)
   - `SESSION_SECRET`

### Opção 3: Render
1. Acesse render.com
2. Conecte seu repositório GitHub
3. Crie um Web Service
4. Adicione um banco PostgreSQL
5. Configure as variáveis de ambiente

### Opção 4: Vercel (Para projetos menores)
1. Instale Vercel CLI: `npm i -g vercel`
2. No diretório do projeto: `vercel`
3. Configure um banco PostgreSQL externo (Supabase, Neon, etc.)

## Variáveis de Ambiente Necessárias

Para qualquer plataforma, configure:

```
DATABASE_URL=postgresql://usuario:senha@host:porta/database
SESSION_SECRET=uma-chave-secreta-longa-e-aleatoria
```

Opcionais (se usar API MNI):
```
MNI_ID_CONSULTANTE=seu-cpf-ou-cnpj
MNI_SENHA_CONSULTANTE=sua-senha
```

## Testando localmente

Depois de configurar, teste localmente:

```bash
# Instale as dependências
pip install -r requirements.txt

# Configure as variáveis de ambiente
cp .env.example .env
# Edite o .env com suas configurações

# Execute o projeto
python main.py
```

## GitHub Actions

O arquivo `.github/workflows/deploy.yml` está configurado para deploy automático no Heroku. Para usar:

1. Adicione secrets no GitHub:
   - `HEROKU_API_KEY`: Sua chave API do Heroku
2. Edite o arquivo com:
   - Seu nome de app do Heroku
   - Seu email

## Suporte

Se encontrar problemas:
1. Verifique os logs da plataforma de deploy
2. Confirme que todas as variáveis de ambiente estão configuradas
3. Verifique se o banco de dados está acessível

## Estrutura de arquivos criada

✅ `github-requirements.txt` → Renomear para `requirements.txt`
✅ `Procfile` → Para Heroku
✅ `runtime.txt` → Versão Python para Heroku
✅ `vercel.json` → Para deploy no Vercel
✅ `Dockerfile` → Para containers Docker
✅ `docker-compose.yml` → Para desenvolvimento local
✅ `.env.example` → Template de variáveis de ambiente
✅ `.gitignore` → Arquivos a ignorar no Git
✅ `README.md` → Documentação do projeto
✅ `.github/workflows/deploy.yml` → GitHub Actions para CI/CD
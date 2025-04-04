# API MNI - Sistema de Consulta Processual

## Descrição
API para consulta de processos judiciais através do Modelo Nacional de Interoperabilidade (MNI).

## Endpoints da API

1. **Consulta de Processo Completo**
   - `GET /api/v1/processo/<num_processo>`
   - Retorna o processo com todos os documentos.

2. **Consulta da Capa do Processo**
   - `GET /api/v1/processo/<num_processo>/capa`
   - Retorna apenas os dados básicos e movimentações do processo.

3. **Download de Documento**
   - `GET /api/v1/processo/<num_processo>/documento/<num_documento>`
   - Baixa um documento específico do processo.

4. **Petição Inicial e Anexos**
   - `GET /api/v1/processo/<num_processo>/peticao-inicial`
   - Retorna a petição inicial e seus anexos.

## Como Testar

Interface de Depuração: `/debug`
- `/debug/consulta` - Processo completo
- `/debug/capa` - Apenas capa do processo
- `/debug/documento` - Documento específico
- `/debug/peticao-inicial` - Petição inicial

## Publicação na AWS (Guia Detalhado)

### 1. Obter o código-fonte

Clone o repositório do GitHub:
```
git clone https://github.com/seu-usuario/api-mni.git
cd api-mni
```

### 2. Preparar o ambiente local

Instale e configure a AWS CLI:
```
pip install awscli
aws configure
# Insira AWS Access Key ID
# Insira AWS Secret Access Key
# Defina a região (ex: us-east-1)
```

### 3. Configurar a aplicação

Crie arquivos necessários para o Elastic Beanstalk:
```
# Crie um arquivo Procfile
echo "web: gunicorn --bind 0.0.0.0:5000 main:app" > Procfile

# Verifique se requirements.txt está atualizado
pip freeze > requirements.txt
```

### 4. Configurar Elastic Beanstalk

Instale e configure a EB CLI:
```
pip install awsebcli
eb init
# Selecione a região
# Selecione Python como plataforma
# Selecione Python 3.11
```

### 5. Configurar variáveis de ambiente

Crie um arquivo `.ebextensions/01_environment.config`:
```
option_settings:
  aws:elasticbeanstalk:application:environment:
    MNI_URL: https://pje.tjce.jus.br/pje1grau/intercomunicacao?wsdl
    MNI_CONSULTA_URL: https://pje.tjce.jus.br/pje1grau/ConsultaPJe?wsdl
  aws:elasticbeanstalk:container:python:
    WSGIPath: main:app
```

### 6. Criar ambiente e fazer deploy

```
# Criar ambiente de produção
eb create api-mni-production

# Configurar credenciais MNI (não armazene em repositórios!)
eb setenv MNI_ID_CONSULTANTE=seu_cpf MNI_SENHA_CONSULTANTE=sua_senha

# Fazer deploy
eb deploy

# Abrir a aplicação no navegador
eb open
```

### 7. Configurar HTTPS (recomendado)

1. No console AWS, solicite um certificado SSL no AWS Certificate Manager
2. Configure o load balancer para usar HTTPS
3. Use o Route 53 para configurar um domínio personalizado

### 8. Monitoramento

1. Configure CloudWatch para alertas de CPU, memória e erros
2. Verifique logs regularmente: `eb logs`
3. Configure métricas personalizadas para monitorar a performance da API

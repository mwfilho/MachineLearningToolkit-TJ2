# Documentação da API MNI

Este documento fornece informações detalhadas sobre como usar a API de consulta de processos judiciais baseada no Modelo Nacional de Interoperabilidade (MNI).

## Autenticação

### Autenticação de API (API Key)

Para acessar qualquer endpoint da API, é necessário se autenticar usando uma API key válida. A API key pode ser fornecida de duas formas:

1. **Via Header HTTP**:
   ```
   X-API-KEY: sua_api_key_aqui
   ```

2. **Via Parâmetro na URL**:
   ```
   ?api_key=sua_api_key_aqui
   ```

### Obtenção de API Keys

Para obter uma API key:

1. Registre-se no sistema: `/auth/register`
2. Faça login: `/auth/login`
3. Acesse o gerenciador de API keys: `/auth/api-keys`
4. Clique em "Nova API Key"
5. Copie a chave gerada e armazene em um local seguro

**IMPORTANTE**: A chave só é exibida uma única vez no momento da criação.

### Autenticação de Serviço MNI

Além da API key, todas as requisições precisam de credenciais MNI para acessar o serviço. Estas podem ser fornecidas:

1. **Via Headers HTTP**:
   ```
   X-MNI-CPF: seu_cpf_ou_cnpj
   X-MNI-SENHA: sua_senha
   ```

2. **Via Variáveis de Ambiente no Servidor**:
   Configure `MNI_ID_CONSULTANTE` e `MNI_SENHA_CONSULTANTE` no ambiente do servidor.

## Endpoints da API

### 1. Consulta Completa de Processo

**Endpoint**: `/api/v1/processo/<num_processo>`  
**Método**: GET  
**Descrição**: Retorna todos os dados do processo incluindo documentos.

**Exemplo de Requisição**:
```bash
curl -H "X-API-KEY: sua_api_key" -H "X-MNI-CPF: seu_cpf" -H "X-MNI-SENHA: sua_senha" http://localhost:5000/api/v1/processo/0000000-00.0000.0.00.0000
```

**Resposta de Sucesso**:
```json
{
  "sucesso": true,
  "mensagem": "Processo consultado com sucesso",
  "processo": {
    "numero": "0000000-00.0000.0.00.0000",
    "classe": "Procedimento Comum Cível",
    "documentos": [
      {
        "idDocumento": "12345678",
        "tipoDocumento": "Petição Inicial",
        "dataHora": "20250101120000",
        "mimetype": "text/html",
        "documentos_vinculados": []
      },
      // ... mais documentos
    ],
    "total_documentos": 10
  }
}
```

### 2. Download de Documento

**Endpoint**: `/api/v1/processo/<num_processo>/documento/<num_documento>`  
**Método**: GET  
**Descrição**: Faz download de um documento específico.

**Exemplo de Requisição**:
```bash
curl -H "X-API-KEY: sua_api_key" -H "X-MNI-CPF: seu_cpf" -H "X-MNI-SENHA: sua_senha" -o documento.pdf http://localhost:5000/api/v1/processo/0000000-00.0000.0.00.0000/documento/12345678
```

**Resposta de Sucesso**: O documento binário é retornado diretamente com o Content-Type apropriado.

### 3. Petição Inicial e Anexos

**Endpoint**: `/api/v1/processo/<num_processo>/peticao-inicial`  
**Método**: GET  
**Descrição**: Retorna a petição inicial e seus anexos.

**Exemplo de Requisição**:
```bash
curl -H "X-API-KEY: sua_api_key" -H "X-MNI-CPF: seu_cpf" -H "X-MNI-SENHA: sua_senha" http://localhost:5000/api/v1/processo/0000000-00.0000.0.00.0000/peticao-inicial
```

**Resposta de Sucesso**:
```json
{
  "sucesso": true,
  "mensagem": "Petição inicial encontrada",
  "peticao_inicial": {
    "idDocumento": "12345678",
    "tipoDocumento": "Petição Inicial",
    "dataHora": "20250101120000",
    "mimetype": "text/html"
  },
  "anexos": [
    {
      "idDocumento": "12345679",
      "tipoDocumento": "Procuração",
      "dataHora": "20250101120001",
      "mimetype": "application/pdf"
    }
    // ... mais anexos
  ]
}
```

### 4. Lista de IDs de Documentos

**Endpoint**: `/api/v1/processo/<num_processo>/documentos/ids`  
**Método**: GET  
**Descrição**: Retorna uma lista de todos os IDs de documentos do processo.

**Exemplo de Requisição**:
```bash
curl -H "X-API-KEY: sua_api_key" -H "X-MNI-CPF: seu_cpf" -H "X-MNI-SENHA: sua_senha" http://localhost:5000/api/v1/processo/0000000-00.0000.0.00.0000/documentos/ids
```

**Resposta de Sucesso**:
```json
{
  "sucesso": true,
  "mensagem": "IDs extraídos com sucesso",
  "documentos": [
    {
      "idDocumento": "12345678",
      "tipoDocumento": "Petição Inicial",
      "descricao": "Petição Inicial"
    },
    {
      "idDocumento": "12345679",
      "tipoDocumento": "Procuração",
      "descricao": "Procuração"
    }
    // ... mais documentos
  ]
}
```

### 5. Capa do Processo

**Endpoint**: `/api/v1/processo/<num_processo>/capa`  
**Método**: GET  
**Descrição**: Retorna apenas os dados da capa do processo (sem documentos).

**Exemplo de Requisição**:
```bash
curl -H "X-API-KEY: sua_api_key" -H "X-MNI-CPF: seu_cpf" -H "X-MNI-SENHA: sua_senha" http://localhost:5000/api/v1/processo/0000000-00.0000.0.00.0000/capa
```

**Resposta de Sucesso**:
```json
{
  "sucesso": true,
  "mensagem": "Capa do processo consultada com sucesso",
  "processo": {
    "numero": "0000000-00.0000.0.00.0000",
    "classe": "Procedimento Comum Cível",
    "assuntos": [
      {
        "codigo": "10000",
        "descricao": "Direito Civil"
      }
    ],
    "orgaoJulgador": {
      "codigoOrgao": "1000",
      "nomeOrgao": "1ª Vara Cível"
    },
    "dataAjuizamento": "20250101",
    "valorCausa": 10000.00,
    "polos": [
      {
        "polo": "ATIVO",
        "partes": [
          {
            "nome": "Parte Ativa",
            "documento": "123.456.789-00",
            "tipo": "PESSOA_FISICA"
          }
        ]
      },
      {
        "polo": "PASSIVO",
        "partes": [
          {
            "nome": "Parte Passiva",
            "documento": "987.654.321-00",
            "tipo": "PESSOA_FISICA"
          }
        ]
      }
    ],
    "movimentos": [
      {
        "dataHora": "20250101120000",
        "descricao": "Distribuído por sorteio"
      }
      // ... mais movimentos
    ]
  }
}
```

## Códigos de Erro

| Código | Descrição |
|--------|-----------|
| 400 | Requisição inválida ou com parâmetros incorretos |
| 401 | Não autorizado - API key ausente ou inválida |
| 403 | Proibido - API key válida mas sem permissão para o recurso |
| 404 | Recurso não encontrado |
| 500 | Erro interno do servidor |

## Exemplos de Erros Comuns

### API Key Não Fornecida:
```json
{
  "erro": "API key não fornecida",
  "mensagem": "Forneça uma API key válida no header X-API-KEY ou no parâmetro api_key"
}
```

### API Key Inválida:
```json
{
  "erro": "API key inválida",
  "mensagem": "A API key fornecida não é válida ou está inativa"
}
```

### Credenciais MNI Não Fornecidas:
```json
{
  "erro": "Credenciais MNI não fornecidas",
  "mensagem": "Forneça as credenciais nos headers X-MNI-CPF e X-MNI-SENHA"
}
```

### Processo Não Encontrado:
```json
{
  "erro": "Processo não encontrado",
  "mensagem": "O processo 0000000-00.0000.0.00.0000 não foi encontrado ou você não tem permissão para acessá-lo"
}
```

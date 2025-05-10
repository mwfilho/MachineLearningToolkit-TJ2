# MNI Document Processing System

O Sistema de Processamento de Documentos MNI é uma aplicação Flask avançada que aproveita o Modelo Nacional de Interoperabilidade (MNI) para realizar consultas e processamento de documentos judiciais de forma eficiente e robusta.

## Visão Geral

Este sistema foi desenvolvido para interagir com os serviços web SOAP do MNI, permitindo a consulta, processamento e download de documentos judiciais, oferecendo mecanismos avançados para garantir a extração completa de todos os documentos de um processo.

## Tecnologias Utilizadas

- **Flask**: Framework web para o backend
- **Flask-SQLAlchemy**: ORM para interação com o banco de dados
- **Zeep**: Cliente SOAP para comunicação com serviços web MNI
- **lxml**: Processamento avançado de XML
- **Requests**: Requisições HTTP para chamadas SOAP manuais
- **Gunicorn**: Servidor WSGI para produção

## Endpoints da API

Para uma documentação completa da API, incluindo exemplos de requisições e respostas, consulte o arquivo [API_DOCS.md](API_DOCS.md).

### Endpoints Web (Interface de Usuário)

| Rota | Método | Descrição |
|------|--------|-----------|
| `/` | GET | Página inicial da aplicação |
| `/debug` | GET | Interface de depuração para testes |
| `/debug/consulta` | POST | Consulta detalhada de processos incluindo documentos |
| `/debug/documento` | POST | Consulta de documentos específicos |
| `/debug/peticao-inicial` | POST | Consulta de petição inicial e anexos |
| `/download_documento/<num_processo>/<num_documento>` | GET | Download de documentos |
| `/debug/documentos-ids` | POST | Consulta de IDs de documentos |
| `/debug/capa-processo` | POST | Consulta da capa do processo |

### Endpoints REST API

| Rota | Método | Descrição |
|------|--------|-----------|
| `/api/v1/processo/<num_processo>` | GET | Retorna todos os dados do processo incluindo documentos |
| `/api/v1/processo/<num_processo>/documento/<num_documento>` | GET | Faz download de um documento específico |
| `/api/v1/processo/<num_processo>/peticao-inicial` | GET | Retorna a petição inicial e seus anexos |
| `/api/v1/processo/<num_processo>/documentos/ids` | GET | Retorna lista de IDs de documentos do processo |
| `/api/v1/processo/<num_processo>/capa` | GET | Retorna apenas os dados da capa do processo |

## Autenticação

### Autenticação MNI

A autenticação com o serviço MNI é realizada utilizando credenciais (CPF/CNPJ e senha) que podem ser fornecidas de três formas:

1. Headers HTTP (`X-MNI-CPF` e `X-MNI-SENHA`)
2. Variáveis de ambiente (`MNI_ID_CONSULTANTE` e `MNI_SENHA_CONSULTANTE`)
3. Formulários na interface web

### Autenticação da API (API Key)

Para acessar os endpoints da API REST, é necessário usar uma API key válida. A API key pode ser fornecida de duas formas:

1. Header HTTP: `X-API-KEY: sua_api_key_aqui`
2. Parâmetro na URL: `?api_key=sua_api_key_aqui`

#### Gerenciamento de API Keys

Para gerenciar suas API keys, é necessário estar autenticado no sistema:

1. Registre-se em `/auth/register` ou faça login em `/auth/login`
2. Acesse o gerenciador de API keys em `/auth/api-keys`
3. Use as opções para criar novas chaves ou revogar chaves existentes

As API keys só são exibidas uma vez no momento da criação. Armazene-as em um local seguro.

## Recursos Avançados

### Extração Robusta de Documentos

O sistema implementa dois métodos complementares para garantir a extração completa de todos os documentos de um processo:

1. **Abordagem Zeep**: Utiliza o cliente SOAP Zeep para extrair documentos e suas relações
2. **Abordagem XML/lxml**: Processa o XML bruto para garantir a extração de todos os documentos, incluindo aqueles que podem ser perdidos pelo Zeep

### Algoritmo BFS para Relacionamento de Documentos

Utiliza algoritmo de Busca em Largura (BFS) para rastrear e mapear complexos relacionamentos entre documentos principais e vinculados.

### Tratamento de MTOM/XOP

Implementa tratamento especial para mensagens SOAP com formato MTOM/XOP (otimização para transferência de dados binários).

## Modelos de Dados

- **User**: Modelo para autenticação e gerenciamento de usuários
- **ApiKey**: Modelo para armazenamento e gerenciamento de chaves de API
  - Cada usuário pode ter múltiplas API keys
  - As chaves contêm metadados como data de criação, último uso e status (ativa/inativa)
  - Vínculo direto com o usuário proprietário da chave

## Como o Código Funciona

### Fluxo de Consulta de Processos

1. As requisições chegam pelos endpoints web ou API
2. As credenciais são validadas e obtidas (de headers, formulários ou variáveis de ambiente)
3. A consulta ao MNI é realizada via SOAP (Zeep) ou requisições manuais (requests + lxml)
4. Os dados são processados, estruturados e retornados ao cliente

### Extração de Documentos

O sistema implementa um mecanismo de extração em duas etapas:

1. **Consulta Principal**: Obtém os dados gerais do processo e documentos principais
2. **Extração Completa**: Garante a extração de todos os documentos, incluindo vinculados, usando uma abordagem robusta baseada em XML

### Considerações de Segurança

- Tratamento de credenciais via variáveis de ambiente
- Autenticação em camadas (usuário/senha + API key)
- Validação de inputs
- Tratamento adequado de erros e exceções
- Proteção contra falhas de comunicação com o serviço MNI
- Sistema seguro para gerenciamento de API keys
  - Hash seguro para senhas de usuários
  - API keys geradas com alta entropia (32 bytes hexadecimais)
  - Controle de acesso baseado em propriedade
  - Possibilidade de revogar chaves comprometidas

## Histórico de Desenvolvimento

O sistema foi desenvolvido com foco em robustez e confiabilidade para processamento de documentos judiciais. A implementação atual aborda desafios específicos:

1. **Extração Completa de Documentos**: Desenvolvimento de um método robusto para garantir a extração de todos os documentos, inclusive os que podem ser perdidos pelo cliente SOAP
2. **Otimização de Performance**: Implementação de consultas otimizadas para acelerar o processamento
3. **Interface de Depuração**: Criação de ferramentas para facilitar o diagnóstico e análise de problemas
4. **Segurança em Camadas**: Implementação de um sistema de autenticação em duas camadas:
   - Login tradicional com usuário e senha
   - Autenticação da API baseada em API keys
5. **Gerenciamento de Acesso**: Implementação de um sistema completo para gerenciamento de API keys, permitindo aos usuários criar, visualizar e revogar suas chaves de API

O sistema está funcionando perfeitamente e pronto para uso em produção.

## Endpoints de Autenticação

| Rota | Método | Descrição |
|------|--------|-----------|
| `/auth/register` | GET/POST | Registro de novos usuários |
| `/auth/login` | GET/POST | Login de usuários |
| `/auth/logout` | GET | Logout de usuários |
| `/auth/api-keys` | GET | Lista todas as API keys do usuário atual |
| `/auth/api-keys/create` | POST | Cria uma nova API key |
| `/auth/api-keys/<key_id>/revoke` | POST | Revoga (desativa) uma API key |
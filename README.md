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

A autenticação é realizada utilizando credenciais MNI (CPF/CNPJ e senha) que podem ser fornecidas de três formas:

1. Headers HTTP (`X-MNI-CPF` e `X-MNI-SENHA`)
2. Variáveis de ambiente (`MNI_ID_CONSULTANTE` e `MNI_SENHA_CONSULTANTE`)
3. Formulários na interface web

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
- Validação de inputs
- Tratamento adequado de erros e exceções
- Proteção contra falhas de comunicação com o serviço MNI

## Histórico de Desenvolvimento

O sistema foi desenvolvido com foco em robustez e confiabilidade para processamento de documentos judiciais. A implementação atual aborda desafios específicos:

1. **Extração Completa de Documentos**: Desenvolvimento de um método robusto para garantir a extração de todos os documentos, inclusive os que podem ser perdidos pelo cliente SOAP
2. **Otimização de Performance**: Implementação de consultas otimizadas para acelerar o processamento
3. **Interface de Depuração**: Criação de ferramentas para facilitar o diagnóstico e análise de problemas

O sistema está funcionando perfeitamente e pronto para uso em produção.
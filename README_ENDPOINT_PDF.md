# API Endpoint para Geração de PDF Completo de Processos Judiciais

Este projeto implementa um endpoint de API para gerar um PDF completo contendo todos os documentos de um processo judicial acessado via MNI (Modelo Nacional de Interoperabilidade).

## Opções de Uso

Foram implementadas duas alternativas para a geração de PDFs completos:

### 1. Endpoint de API (Quando o Servidor Flask Estiver Funcionando)

O endpoint de API está implementado em `routes/api.py` e pode ser acessado via:

```
GET /api/v1/processo/{numero_processo}/pdf-completo
```

Headers necessários:
- `X-MNI-CPF`: CPF/CNPJ do consultante autorizado
- `X-MNI-SENHA`: Senha do consultante autorizado

O endpoint retorna um arquivo PDF único contendo todos os documentos do processo combinados.

### 2. Script Autônomo (Sem Dependência do Flask)

Para ambientes onde não é possível iniciar o servidor Flask, foi criado um script autônomo:

```
./api_standalone.py NUMERO_PROCESSO [OUTPUT_FILE] [CPF] [SENHA]
```

Este script realiza a mesma funcionalidade sem depender do servidor Flask.

## Funcionalidades Implementadas

- Consulta ao processo para obter lista de documentos
- Download de cada documento individual
- Processamento baseado no tipo de documento:
  - PDF: Preserva o formato original
  - HTML: Tenta converter para PDF, com fallback para texto
  - Outros formatos: Extraídos como texto
- Geração de índice com listagem de documentos
- Combinação de documentos em um único arquivo PDF
- Limpeza de arquivos temporários

## Dependências e Requisitos

O sistema faz uso das seguintes ferramentas externas (quando disponíveis):

- `pdftk`: Para combinar múltiplos PDFs
- `wkhtmltopdf`: Para converter HTML para PDF

Se essas ferramentas não estiverem disponíveis, o sistema usa métodos alternativos:
- Sem pdftk: Retorna apenas o primeiro documento PDF
- Sem wkhtmltopdf: Converte documentos HTML para texto simples

## Detalhes Técnicos

A implementação é robusta e projetada para funcionar mesmo em ambientes com limitações:

1. Implementa fallbacks para cada dependência externa
2. Usa recursos nativos do Python quando possível
3. Fornece informações detalhadas em logs para diagnóstico
4. Realiza limpeza adequada de recursos temporários

## Considerações de Desempenho

O processamento é feito sequencialmente para garantir compatibilidade em ambientes com recursos limitados. Para processos com muitos documentos, o tempo de processamento pode ser significativo.
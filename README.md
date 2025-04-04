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

## Publicação na AWS

1. Instalar AWS CLI e configurar credenciais.
2. Criar aplicação no Elastic Beanstalk com Python 3.11.
3. Configurar ambiente e variáveis necessárias.
4. Fazer deploy da aplicação.

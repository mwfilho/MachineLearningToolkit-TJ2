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

## Autenticação

Todas as requisições exigem credenciais MNI, que podem ser fornecidas através dos headers:
- `X-MNI-CPF` - CPF/CNPJ do consultante
- `X-MNI-SENHA` - Senha do consultante

## Como usar com cURL

### Consultar processo completo
```bash
curl -X GET "http://localhost:5000/api/v1/processo/0000000-00.0000.0.00.0000" \
  -H "X-MNI-CPF: seu_cpf_ou_cnpj" \
  -H "X-MNI-SENHA: sua_senha"
```

### Consultar apenas a capa do processo
```bash
curl -X GET "http://localhost:5000/api/v1/processo/0000000-00.0000.0.00.0000/capa" \
  -H "X-MNI-CPF: seu_cpf_ou_cnpj" \
  -H "X-MNI-SENHA: sua_senha"
```

### Baixar um documento específico
```bash
curl -X GET "http://localhost:5000/api/v1/processo/0000000-00.0000.0.00.0000/documento/12345" \
  -H "X-MNI-CPF: seu_cpf_ou_cnpj" \
  -H "X-MNI-SENHA: sua_senha" \
  --output documento.pdf
```

### Consultar petição inicial e anexos
```bash
curl -X GET "http://localhost:5000/api/v1/processo/0000000-00.0000.0.00.0000/peticao-inicial" \
  -H "X-MNI-CPF: seu_cpf_ou_cnpj" \
  -H "X-MNI-SENHA: sua_senha"
```

## Como usar com Postman

1. Abra o Postman e crie uma nova requisição.

2. Selecione o método `GET` e insira a URL de um dos endpoints:
   - `http://localhost:5000/api/v1/processo/0000000-00.0000.0.00.0000`
   - `http://localhost:5000/api/v1/processo/0000000-00.0000.0.00.0000/capa`
   - `http://localhost:5000/api/v1/processo/0000000-00.0000.0.00.0000/documento/12345`
   - `http://localhost:5000/api/v1/processo/0000000-00.0000.0.00.0000/peticao-inicial`

3. Na aba "Headers", adicione as credenciais MNI:
   - Key: `X-MNI-CPF` | Value: `seu_cpf_ou_cnpj`
   - Key: `X-MNI-SENHA` | Value: `sua_senha`

4. Clique em "Send" para enviar a requisição.

5. Para o endpoint de download de documentos, o arquivo será baixado automaticamente.

## Exemplo de Resposta JSON

### Consulta de processo
```json
{
  "processo": {
    "numero": "0000000-00.0000.0.00.0000",
    "classe": "Procedimento Comum Cível",
    "assuntos": ["Indenização por Dano Material", "Indenização por Dano Moral"],
    "dataDistribuicao": "2022-01-01T10:00:00",
    "orgaoJulgador": "1ª Vara Cível",
    "valorCausa": 10000.0
  },
  "documentos": [
    {
      "id": "12345",
      "tipoDocumento": "Petição Inicial",
      "dataDocumento": "2022-01-01T09:30:00",
      "mimetype": "application/pdf"
    },
    {
      "id": "12346",
      "tipoDocumento": "Procuração",
      "dataDocumento": "2022-01-01T09:35:00",
      "mimetype": "application/pdf"
    }
  ],
  "movimentacoes": [
    {
      "dataMovimentacao": "2022-01-02T11:00:00",
      "descricao": "Despacho - Cite-se o réu"
    },
    {
      "dataMovimentacao": "2022-01-01T10:00:00",
      "descricao": "Distribuído por sorteio"
    }
  ]
}
```

## Interface de Depuração

Para testar a API de forma interativa, você pode usar a interface de depuração disponível em:
- `/debug` - Interface principal
- `/debug/consulta` - Processo completo
- `/debug/capa` - Apenas capa do processo
- `/debug/documento` - Documento específico
- `/debug/peticao-inicial` - Petição inicial
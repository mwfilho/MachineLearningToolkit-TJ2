# Sistema de Consulta Processual MNI

## Descrição
Sistema de consulta processual judicial avançado que utiliza o Modelo Nacional de Interoperabilidade (MNI) para busca e gerenciamento eficiente de documentos processuais, com interface web moderna e intuitiva.

## Funcionalidades Principais

- ✅ Consulta de processos via MNI
- ✅ Extração completa de documentos principais e vinculados
- ✅ Visualização hierárquica de documentos do processo
- ✅ Download de documentos processuais
- ✅ Interface de debug para análise detalhada

## Configuração do Ambiente

### Credenciais MNI

O sistema utiliza credenciais do MNI armazenadas como variáveis de ambiente por questões de segurança:

- `MNI_ID_CONSULTANTE`: CPF/CNPJ do consultante 
- `MNI_SENHA_CONSULTANTE`: Senha do consultante

Estas credenciais são utilizadas para autenticar todas as requisições ao serviço MNI.

### URLs do MNI

As URLs de acesso ao MNI são configuradas em `config.py`:

```python
MNI_URL = "https://pje.tjce.jus.br/pje1grau/intercomunicacao?wsdl"
MNI_CONSULTA_URL = 'https://pje.tjce.jus.br/pje1grau/ConsultaPJe?wsdl'
```

## Estrutura do Código

### Arquivos Principais

- `main.py`: Rotas Flask e lógica de controle
- `funcoes_mni.py`: Funções de integração com o MNI
- `controle/exceptions.py`: Exceções personalizadas
- `templates/`: Templates HTML das páginas

### Fluxo de Execução

1. **Consulta Inicial**
   - Usuário fornece número do processo
   - Sistema faz requisição ao MNI
   - Extrai estrutura completa do processo

2. **Processamento de Documentos**
   - Identificação de documentos principais
   - Extração de documentos vinculados
   - Organização em estrutura hierárquica
   ```python
   doc_info = {
       'idDocumento': id_principal,
       'documentos_vinculados': [
           {'idDocumento': id_vinculado, ...}
       ]
   }
   ```

3. **Download de Documentos**
   - Sistema oferece download para cada documento
   - Identificação automática do tipo MIME
   - Nomeação adequada dos arquivos

## Hierarquia de Documentos

O sistema implementa uma estrutura hierárquica completa:

1. **Documentos Principais**
   - Petição Inicial
   - Decisões
   - Despachos

2. **Documentos Vinculados**
   - Procurações
   - Documentos de Identificação
   - Comprovantes
   - Anexos

3. **Relacionamentos**
   - Um documento principal pode ter múltiplos documentos vinculados
   - Cada documento mantém seus metadados (tipo, data, descrição)

## Como Usar

1. **Página Principal**
   - Acesse a raiz do sistema
   - Digite o número do processo no formato CNJ
   - Clique em "Consultar"

2. **Página de Debug**
   - Mostra estrutura completa do processo
   - Lista todos os documentos principais e vinculados
   - Permite download individual de cada documento

3. **Download de Documentos**
   - Clique no botão "Baixar" ao lado de cada documento
   - O sistema identificará automaticamente o tipo do arquivo
   - O download será iniciado com o nome e extensão corretos

## Tratamento de Erros

O sistema implementa tratamento robusto de erros:
- Validação de número do processo
- Tratamento de erros de comunicação com MNI
- Logging detalhado para debugging
- Mensagens amigáveis para o usuário

## Segurança

- Credenciais MNI em variáveis de ambiente
- Validação de inputs
- Tratamento de níveis de sigilo dos documentos
- Sanitização de dados antes da exibição

## Melhorias e Funcionalidades Implementadas

1. **Extração Completa de Documentos**
   - Implementada extração de documentos principais
   - Adicionado suporte a documentos vinculados usando o atributo 'documentoVinculado'
   - Interface hierárquica para visualização
   ```python
   if hasattr(doc, 'documentoVinculado'):
       for doc_vinc in doc.documentoVinculado:
           vinc_info = {
               'idDocumento': getattr(doc_vinc, 'idDocumento', ''),
               'tipoDocumento': getattr(doc_vinc, 'tipoDocumento', ''),
               'descricao': getattr(doc_vinc, 'descricao', ''),
               'dataHora': getattr(doc_vinc, 'dataHora', ''),
               'mimetype': getattr(doc_vinc, 'mimetype', ''),
               'nivelSigilo': getattr(doc_vinc, 'nivelSigilo', 0)
           }
           doc_info['documentos_vinculados'].append(vinc_info)
   ```

2. **Sistema de Download**
   - Download direto de documentos
   - Identificação automática de tipos MIME
   - Nomeação adequada dos arquivos
   ```python
   extensao = core.mime_to_extension.get(resposta['mimetype'], '.bin')
   with open(file_path, 'wb') as f:
       f.write(resposta['conteudo'])
   ```

3. **Interface de Debug**
   - Visualização detalhada da estrutura do processo
   - Exibição de metadados dos documentos
   - Facilidade para testes e verificações

## Próximos Passos

Possíveis melhorias futuras:
- Implementar cache de consultas
- Adicionar suporte a mais tipos de documentos
- Melhorar a interface de usuário
- Adicionar mais funcionalidades de busca

## Notas Importantes

1. **Estrutura XML do MNI**
   - O sistema processa a estrutura XML complexa do MNI
   - Extrai todos os documentos vinculados usando o atributo 'documentoVinculado'
   - Mantém a hierarquia original dos documentos

2. **Processamento de Documentos**
   - Cada documento principal pode ter vários documentos vinculados
   - A extração é feita recursivamente para garantir que todos os documentos sejam capturados
   - Os metadados são preservados para cada documento

3. **Downloads**
   - Sistema suporta múltiplos tipos de arquivos (PDF, DOC, etc)
   - Gerencia o download de forma segura usando arquivos temporários
   - Preserva os tipos MIME originais dos documentos

4. **Estrutura de IDs dos Documentos**
   - Documentos principais têm seus próprios IDs
   - Documentos vinculados são identificados pelo atributo 'documentoVinculado'
   - Cada documento pode ter múltiplos documentos relacionados
   - O sistema captura e organiza todos os IDs em uma estrutura hierárquica para facilitar o acesso

5. **Tipos de Documentos Suportados**
   - Petições (formato HTML/PDF)
   - Documentos de identificação (PDF/Imagens)
   - Procurações (PDF)
   - Comprovantes e anexos (formatos diversos)
   - Sistema detecta automaticamente o tipo MIME para download correto


## API REST

O sistema disponibiliza uma API REST para integração com outros sistemas:

### Endpoints

1. **Consulta de Processo**
   ```
   GET /api/v1/processo/{numero_processo}
   ```
   Retorna dados do processo e lista completa de documentos.

   Exemplo de resposta:
   ```json
   {
     "sucesso": true,
     "mensagem": "Processo consultado com sucesso",
     "processo": {
       "numero": "0000000-00.0000.0.00.0000",
       "classeProcessual": "Classe do Processo",
       "dataAjuizamento": "2025-03-17",
       "orgaoJulgador": "Vara Exemplo",
       "documentos": [
         {
           "idDocumento": "123456",
           "tipoDocumento": "58",
           "descricao": "Petição Inicial",
           "dataHora": "20250317000000",
           "mimetype": "text/html",
           "documentos_vinculados": [
             {
               "idDocumento": "123457",
               "tipoDocumento": "4050007",
               "descricao": "Procuração"
             }
           ]
         }
       ]
     }
   }
   ```

2. **Download de Documento**
   ```
   GET /api/v1/processo/{numero_processo}/documento/{id_documento}
   ```
   Faz download do documento específico. Retorna o arquivo binário com o Content-Type apropriado.

### Exemplos de Uso (Postman)

1. **Consultar Processo**
   ```
   GET http://seu-servidor.repl.co/api/v1/processo/0000000-00.0000.0.00.0000
   ```

2. **Baixar Documento**
   ```
   GET http://seu-servidor.repl.co/api/v1/processo/0000000-00.0000.0.00.0000/documento/123456
   ```

### Notas sobre a API

- Todos os endpoints retornam erro 500 em caso de falha interna
- O download de documentos retorna erro 404 se o documento não for encontrado
- Os documentos são retornados em seu formato original (PDF, HTML, etc)
- A API preserva os tipos MIME originais dos documentos
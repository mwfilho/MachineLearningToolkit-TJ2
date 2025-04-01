# Sistema de Consulta Processual MNI

## Descrição
Sistema avançado de consulta processual judicial, especializado no processamento e análise de documentos judiciais através do Modelo Nacional de Interoperabilidade (MNI), com capacidade de geração e mesclagem de documentos PDF.

## Funcionalidades Principais

- ✅ Consulta de processos via MNI
- ✅ Extração completa de documentos principais e vinculados
- ✅ Visualização hierárquica de documentos do processo
- ✅ Download de documentos processuais
- ✅ Interface de debug para análise detalhada
- ✅ API REST para integração com outros sistemas
- ✅ Suporte a credenciais MNI personalizadas
- ✅ Processamento recursivo de documentos vinculados
- ✅ Suporte a múltiplos formatos de documentos
- ✅ Sistema de autenticação de usuários

## Arquitetura do Sistema

### Estrutura de Diretórios
```
├── app.py                 # Configuração principal do Flask
├── main.py                # Ponto de entrada da aplicação
├── config.py              # Configurações do MNI e outras variáveis
├── core.py                # Funções principais de processamento
├── funcoes_mni.py         # Implementação de integração com o MNI
├── utils.py               # Funções utilitárias
├── models.py              # Modelos de banco de dados
├── controle/              # Funções de controle
│   ├── __init__.py
│   ├── exceptions.py      # Classes de exceção personalizadas
│   └── logger.py          # Configuração de logging
├── routes/                # Rotas da aplicação
│   ├── api.py             # API REST
│   ├── auth.py            # Autenticação de usuários
│   └── web.py             # Interface web
└── templates/             # Templates HTML
    └── base.html          # Template base
    └── debug.html         # Interface de debug
    └── index.html         # Página principal
```

### Componentes Principais

1. **Integração MNI**
   - Comunicação SOAP com o MNI via biblioteca Zeep
   - Autenticação flexível via credenciais personalizadas
   - Processamento de XML complexos do modelo MNI
   
2. **Sistema de Autenticação**
   - Gerenciamento de usuários com Flask-Login
   - Armazenamento seguro de senhas com hash
   - Controle de acesso a áreas restritas

3. **API REST**
   - Endpoints para consulta de processos
   - Suporte a download de documentos
   - Autenticação via headers HTTP
   - Tratamento de erros padronizado

4. **Processamento de Documentos**
   - Extração hierárquica de documentos
   - Suporte a múltiplos tipos MIME
   - Download seguro via arquivos temporários
   - Sistema de classificação por tipo de documento

## Integração com o MNI

### Credenciais MNI

O sistema suporta duas formas de fornecer credenciais MNI:

1. **Variáveis de Ambiente** (para uso geral)
   - `MNI_ID_CONSULTANTE`: CPF/CNPJ do consultante 
   - `MNI_SENHA_CONSULTANTE`: Senha do consultante

2. **Headers HTTP** (para API REST)
   - `X-MNI-CPF`: CPF/CNPJ do consultante
   - `X-MNI-SENHA`: Senha do consultante

**Importante**: O CPF/CNPJ deve ser fornecido apenas com números, sem formatação.
Exemplo: Use `12345678900` ao invés de `123.456.789-00`

### URLs do MNI

As URLs de acesso são configuradas em `config.py`:

```python
MNI_URL = "https://pje.tjce.jus.br/pje1grau/intercomunicacao?wsdl"
MNI_CONSULTA_URL = 'https://pje.tjce.jus.br/pje1grau/ConsultaPJe?wsdl'
```

### Fluxo de Comunicação MNI

1. **Consulta de Processo**
   ```python
   resposta = retorna_processo(num_processo, cpf, senha)
   ```
   - Estabelece conexão SOAP com o servidor MNI
   - Autentica o usuário com as credenciais fornecidas
   - Processa a resposta XML complexa
   - Extrai estrutura completa do processo e seus documentos

2. **Consulta de Documento**
   ```python
   resposta = retorna_documento_processo(num_processo, num_documento, cpf, senha)
   ```
   - Consulta um documento específico dentro do processo
   - Retorna conteúdo binário para download
   - Preserva metadados como tipo MIME e descrição

## Processamento de Documentos

### Hierarquia de Documentos

O sistema implementa uma estrutura hierárquica complexa:

1. **Documentos Principais**
   - Petição Inicial, Decisões, Despachos, Sentenças
   - Identificados pelo atributo `documento` na resposta MNI

2. **Documentos Vinculados**
   - Anexos, Procurações, Documentos de Identificação
   - Identificados pelo atributo `documentoVinculado` na resposta MNI

3. **Algoritmo de Extração**
   ```python
   # Pseudocódigo simplificado do algoritmo de extração
   def procurar_documento(doc_list, target_id):
       for doc in doc_list:
           # Verifica documento atual
           if doc.idDocumento == target_id:
               return doc
               
           # Verifica documentos vinculados (recursivo)
           if hasattr(doc, 'documentoVinculado'):
               result = procurar_documento(doc.documentoVinculado, target_id)
               if result:
                   return result
   ```

### Sistema de Download

1. **Processamento de Tipos MIME**
   ```python
   # Mapeamento de tipos MIME para extensões de arquivo
   mime_to_extension = {
       'application/pdf': '.pdf',
       'image/jpeg': '.jpg',
       'image/png': '.png',
       'text/html': '.html',
       # ...outros tipos
   }
   ```

2. **Criação de Arquivos Temporários**
   ```python
   temp_dir = tempfile.mkdtemp()
   file_path = os.path.join(temp_dir, f'{num_documento}{extensao}')
   with open(file_path, 'wb') as f:
       f.write(resposta['conteudo'])
   ```

3. **Download Seguro via Flask**
   ```python
   return send_file(
       file_path,
       mimetype=resposta['mimetype'],
       as_attachment=True,
       download_name=f'documento_{num_documento}{extensao}'
   )
   ```

## API REST

### Endpoints Principais

1. **Consulta de Processo**
   ```
   GET /api/v1/processo/<num_processo>
   ```
   Exemplo de uso:
   ```bash
   curl -X GET "http://seu-servidor.repl.co/api/v1/processo/0000000-00.0000.0.00.0000" \
     -H "X-MNI-CPF: 12345678900" \
     -H "X-MNI-SENHA: sua_senha"
   ```

2. **Download de Documento**
   ```
   GET /api/v1/processo/<num_processo>/documento/<num_documento>
   ```
   Exemplo de uso:
   ```bash
   curl -X GET "http://seu-servidor.repl.co/api/v1/processo/0000000-00.0000.0.00.0000/documento/123456" \
     -H "X-MNI-CPF: 12345678900" \
     -H "X-MNI-SENHA: sua_senha" \
     --output documento.pdf
   ```

### Tratamento de Erros

O sistema implementa resposta de erros padronizadas:
```json
{
  "erro": "Descrição do erro",
  "mensagem": "Mensagem amigável para o usuário"
}
```

Códigos HTTP retornados:
- 200: Sucesso
- 401: Credenciais não fornecidas ou inválidas
- 404: Documento ou processo não encontrado
- 500: Erro interno do servidor

## Sistema de Autenticação

### Modelo de Usuário
```python
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256))
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
```

### Rotas de Autenticação
- `/login`: Autenticação de usuários
- `/register`: Registro de novos usuários
- `/logout`: Logout de usuários autenticados

## Tratamento de Erros e Logging

### Sistema de Logging
```python
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
```

### Exceções Personalizadas
```python
class ExcecaoConsultaMNI(Exception):
    """Exception raised for errors during MNI consultation."""
    pass
```

### Tratamento de Erros nas Requisições MNI
```python
try:
    client = Client(url)
    response = client.service.consultarProcesso(**request_data)
    # Processamento...
except Fault as e:
    if "loginFailed" in str(e):
        error_msg = "Erro de autenticação no MNI"
    else:
        error_msg = f"Erro na comunicação SOAP: {str(e)}"
    logger.error(error_msg)
    raise ExcecaoConsultaMNI(error_msg)
```

## Validações e Funções Utilitárias

### Validação de Número de Processo
```python
def validate_process_number(num_processo):
    pattern = r'^\d{7}-\d{2}\.\d{4}\.\d{1}\.\d{2}\.\d{4}$'
    return bool(re.match(pattern, num_processo))
```

### Formatação de Número de Processo
```python
def format_process_number(num_processo):
    nums = re.sub(r'\D', '', num_processo)
    if len(nums) != 20:
        raise ValueError("Process number must have 20 digits")
    return f"{nums[:7]}-{nums[7:9]}.{nums[9:13]}.{nums[13]}.{nums[14:16]}.{nums[16:]}"
```

## Interface Web

### Páginas Principais
- **Página Inicial**: Interface simplificada para consulta de processos
- **Debug**: Interface avançada para análise detalhada de processos
- **Autenticação**: Login e registro de usuários

### Funcionalidades da Interface
- Consulta de processos por número
- Visualização hierárquica de documentos
- Download direto de documentos
- Interface administrativa para usuários autorizados

## Próximos Passos

Possíveis melhorias futuras:

1. **Sistema de Cache**
   - Implementar cache para consultas frequentes
   - Reduzir o tráfego com o servidor MNI
   - Melhorar tempo de resposta

2. **Mesclagem de PDFs**
   - Possibilidade de baixar documentos vinculados em um único PDF
   - Adição de índices e marcadores para navegação

3. **Interface Responsiva**
   - Melhorar a experiência em dispositivos móveis
   - Implementar interface com React ou Vue.js

4. **Consulta em Lote**
   - Possibilidade de consultar múltiplos processos simultaneamente
   - Processamento assíncrono com filas

5. **Extração de Dados Avançada**
   - Análise de texto dos documentos usando NLP
   - Extração de informações relevantes como datas, partes, etc.
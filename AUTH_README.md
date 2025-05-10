# Sistema de Autenticação e Controle de Acesso

Este documento descreve o sistema de autenticação e controle de acesso implementado para proteger as rotas de debug da aplicação Consulta MNI.

## Visão Geral

O sistema de autenticação foi desenvolvido para proteger as páginas e endpoints de debug, garantindo que apenas usuários autorizados (administradores) possam acessá-los. Isso é completamente independente da autenticação do MNI (Modelo Nacional de Interoperabilidade), que é utilizada para acessar os serviços do PJe.

## Componentes Principais

### 1. Modelo de Usuário

O modelo `User` (em `models.py`) foi implementado com os seguintes campos:
- `id`: Identificador único do usuário
- `username`: Nome de usuário (único)
- `password_hash`: Senha criptografada usando Werkzeug
- `is_admin`: Flag booleano para controle de permissões de administrador

```python
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256))
    is_admin = db.Column(db.Boolean, default=False)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
```

### 2. Sistema de Login

O sistema de login foi implementado usando o Flask-Login, com rotas para:
- Login (`/login`)
- Registro de usuários (`/register`)
- Logout (`/logout`)

As templates correspondentes estão em `templates/auth/`.

### 3. Proteção de Rotas

Um decorador personalizado `@debug_required` foi criado para proteger as rotas de debug:

```python
def debug_required(f):
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        # Verificar se o usuário está autenticado
        if not current_user.is_authenticated:
            logger.warning(f"Tentativa de acesso não autorizado à rota: {request.path}")
            flash('Por favor, faça login para acessar esta página.', 'warning')
            return redirect(url_for('auth.login', next=request.url))
        
        # Verificar se o usuário é administrador
        if not current_user.is_admin:
            logger.warning(f"Usuário sem permissão de admin tentou acessar: {request.path}, user: {current_user.username}")
            flash('Você não tem permissão para acessar esta página.', 'danger')
            return redirect(url_for('web.index'))
            
        return f(*args, **kwargs)
    return decorated_function
```

Este decorador:
1. Verifica se o usuário está autenticado
2. Verifica se o usuário tem permissões de administrador
3. Registra tentativas de acesso não autorizado nos logs
4. Redireciona usuários não autorizados para a página apropriada

### 4. Configuração do LoginManager

O Flask-Login foi configurado em `app.py`:

```python
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.login'
login_manager.login_message = 'Por favor, faça login para acessar esta página.'
```

## Endpoints Protegidos

Todas as rotas de debug estão protegidas pelo decorador `@debug_required`:

- `/debug` - Página principal de debug
- `/debug/consulta` - Consulta de processos
- `/debug/documento` - Visualização de documentos específicos
- `/debug/peticao-inicial` - Visualização da petição inicial
- `/debug/documentos-ids` - Listagem de IDs de documentos
- `/debug/capa` - Visualização da capa do processo
- `/download_documento/<num_processo>/<num_documento>` - Download de documentos

## Usuário Administrador

Um usuário administrador foi criado com as seguintes credenciais:
- **Username**: admin
- **Senha**: senhasegura

O script `create_admin.py` permite criar ou atualizar o usuário administrador:

```bash
python create_admin.py <username> <password> [force]
```

Exemplo:
```bash
python create_admin.py admin senhasegura force
```

## Interface de Usuário

A barra de navegação foi atualizada para mostrar diferentes opções dependendo do estado de autenticação:
- Usuários não autenticados veem links para Login e Registro
- Usuários autenticados veem uma saudação e um link para Logout

## Segurança

As senhas são armazenadas de forma segura usando o hash SHA-256 do Werkzeug, não sendo possível recuperar a senha original a partir do hash armazenado.

## Logs de Segurança

Tentativas de acesso não autorizado são registradas nos logs da aplicação para fins de auditoria de segurança.

## Fluxo de Acesso

1. Usuário tenta acessar uma rota protegida
2. Se não autenticado, é redirecionado para a página de login
3. Após login bem-sucedido, é redirecionado de volta para a página original
4. Se autenticado mas não administrador, recebe mensagem de erro e é redirecionado para a página inicial

## Notas de Implementação

- As rotas de API (`/api/v1/...`) não foram protegidas por este sistema, pois são projetadas para acesso externo via SOAP/MNI
- O sistema de autenticação é separado do sistema de autenticação MNI, que utiliza CPF/senha para acessar o PJe
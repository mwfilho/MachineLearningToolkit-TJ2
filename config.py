import os

# -------------------------------------------------------------------------
# URLs do MNI (padrão para TJPE). No Railway, defina:
#   MNI_URL="https://pje.tjpe.jus.br/1g/intercomunicacao?wsdl"
#   MNI_CONSULTA_URL="https://pje.tjpe.jus.br/1g/ConsultaPJe?wsdl"
# Caso você queira usar outro tribunal, basta setar a variável de ambiente.
# -------------------------------------------------------------------------
MNI_URL = os.getenv(
    'MNI_URL',
    "https://pje.tjpe.jus.br/1g/intercomunicacao?wsdl"
)

MNI_CONSULTA_URL = os.getenv(
    'MNI_CONSULTA_URL',
    "https://pje.tjpe.jus.br/1g/ConsultaPJe?wsdl"
)

# Credenciais para consulta MNI (CPF e Senha). No Railway configure:
#   MNI_ID_CONSULTANTE="06293234456"
#   MNI_SENHA_CONSULTANTE="Simb@280303"
MNI_ID_CONSULTANTE = os.getenv('MNI_ID_CONSULTANTE', None)
MNI_SENHA_CONSULTANTE = os.getenv('MNI_SENHA_CONSULTANTE', None)

# -------------------------------------------------------------------------
# Configurações do Flask (exemplo):
# -------------------------------------------------------------------------
SECRET_KEY = os.getenv('SECRET_KEY', 'dev')  # redefina em produção
UPLOAD_FOLDER = 'downloads'

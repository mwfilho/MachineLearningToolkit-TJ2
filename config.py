import os

# MNI Configuration
MNI_URL = os.getenv('MNI_URL', "https://pje.tjce.jus.br/pje1grau/intercomunicacao?wsdl")
MNI_CONSULTA_URL = os.getenv('MNI_CONSULTA_URL', 'https://pje.tjce.jus.br/pje1grau/ConsultaPJe?wsdl')
MNI_ID_CONSULTANTE = os.getenv('MNI_ID_CONSULTANTE', "")
MNI_SENHA_CONSULTANTE = os.getenv('MNI_SENHA_CONSULTANTE', "")

# Flask Configuration
SECRET_KEY = os.getenv('SECRET_KEY', 'dev')
UPLOAD_FOLDER = 'downloads'

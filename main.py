import os
import logging
from flask import Flask
from routes.web import web
from routes.api import api

# Configurar logging
logging.basicConfig(level=logging.DEBUG, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('app')

# Criar a aplicação Flask
app = Flask(__name__)
app.secret_key = os.environ.get('SESSION_SECRET', 'chave-secreta-desenvolvimento')

# Registrar blueprints
logger.debug("Registrando blueprint web...")
app.register_blueprint(web)
logger.debug("Registrando blueprint api...")
app.register_blueprint(api)
logger.debug("Blueprints registrados com sucesso")

# Registrar rotas no log
with app.app_context():
    logger.debug("Rotas registradas:")
    for rule in app.url_map.iter_rules():
        logger.debug("%s: %s", rule.endpoint, rule)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
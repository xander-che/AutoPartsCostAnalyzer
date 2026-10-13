import os

from flask import Flask, jsonify
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

from controllers.controller import params
from static.messages import ERROR_INTERNAL

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = int(os.getenv('MAX_UPLOAD_MB', '50')) * 1024 * 1024
app.json.ensure_ascii = False
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

app.register_blueprint(params)


@app.errorhandler(HTTPException)
def handle_http_error(error: HTTPException):
    """Ошибки HTTP отдаём в JSON: фронтенд умеет разбирать только JSON.

    Иначе браузер получает HTML-страницу и показывает «Unexpected token '<'».
    """

    return jsonify({'error': f'{error.code}: {error.description}'}), error.code


@app.errorhandler(Exception)
def handle_unexpected_error(error: Exception):
    """Необработанные исключения тоже превращаем в JSON и пишем в журнал сервера."""

    app.logger.exception('Необработанная ошибка при обработке запроса')

    return jsonify({'error': ERROR_INTERNAL}), 500


if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=int(os.getenv('PORT', '5000')), threaded=True)

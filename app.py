from flask import Flask
from controllers.controller import params

app = Flask(__name__)

app.register_blueprint(params)

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0')
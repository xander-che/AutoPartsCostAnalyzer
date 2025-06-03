from flask import Flask
from controllers.entry_params_controller import params

app = Flask(__name__)

app.register_blueprint(params)

if __name__ == '__main__':
    app.run(debug=True)
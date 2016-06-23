import argparse
from processingManager import ProcessingManager
from flask import Flask, request, jsonify
from flask.ext.socketio import SocketIO

parser = argparse.ArgumentParser(description='Starts the server to process tracks')
parser.add_argument('-p', '--port', dest='port', metavar='p', type=int,
        default=5000,
        help='port to use')
parser.add_argument('--debug', dest='debug', action='store_false',
        help='print server debug information')
parser.add_argument('--verbose', dest='verbose',
        action='store_false',
        help='print debug information of processing stage')
parser.add_argument('--config', '-c', dest='config', metavar='c', type=str,
        help='configuration file')
args = parser.parse_args()



app = Flask(__name__)
socketio = SocketIO(app)

manager = ProcessingManager(args.config)

def setHeaders(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    return response

def sendState():
    response = jsonify(manager.currentState())
    return setHeaders(response)

def undoStep():
    manager.restore()

@app.route('/previous', methods=['GET'])
def previous():
    """Restores a previous state

    Returns:
        A response instance
    """
    manager.restore()
    return sendState()

@app.route('/next', methods=['POST'])
def next():
    """Advances the progress

    Returns:
        A response instance
    """
    payload = request.get_json(force=True)
    manager.process(payload)
    return sendState()

@app.route('/current', methods=['GET'])
def current():
    """Gets the current state of the execution

    Returns:
        A response instance
    """
    return sendState()

@app.route('/completeTrip', methods=['POST'])
def completeTrip():
    """Gets trips already made from one point, to another

    Returns:
        A response instance
    """
    payload = request.get_json(force=True)
    return setHeaders(jsonify(manager.completeTrip(payload)))

@app.route('/config', methods=['POST'])
def setConfiguration():
    payload = request.get_json(force=True)
    manager.config.update(payload)
    return setHeaders(jsonify(manager.config))

@app.route('/config', methods=['GET'])
def getConfiguration():
    return setHeaders(jsonify(manager.config))

if __name__ == '__main__':
    app.run(debug=args.debug, port=args.port)

import argparse
from .ProcessingManager import ProcessingManager
from flask import Flask, request, jsonify
from flask.ext.socketio import SocketIO

parser = argparse.ArgumentParser(description='Starts the server to process tracks')
parser.add_argument('-s', '--source', dest='source', metavar='s', type=str,
        required=True,
        help='folder to extract the tracks from')
parser.add_argument('-b', '--backup', dest='backup', metavar='b', type=str,
        required=True,
        help='backup folder for the original GPX files')
parser.add_argument('-l', '--life', dest='life', metavar='l', type=str,
        required=True,
        help='folder to save the each trip\'s LIFE files')
parser.add_argument('-d', '--dest', dest='dest', metavar='d', type=str,
        default='./temp',
        help='folder to save the processed tracks')
parser.add_argument('-p', '--port', dest='port', metavar='p', type=int,
        default=5000,
        help='port to use')
parser.add_argument('--debug', dest='debug', action='store_false',
        help='print server debug information')
parser.add_argument('--verbose', dest='verbose',
        action='store_false',
        help='print debug information of processing stage')
args = parser.parse_args()

app = Flask(__name__)
socketio = SocketIO(app)

# TODO
manager = ProcessingManager(inputPath=args.source, outputPath=args.dest, lifePath=args.life, backupPath=args.backup)

def setHeaders(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    return response

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

def sendState():
    response = jsonify(manager.currentState())
    return setHeaders(response)

@app.route('/current', methods=['GET'])
def current():
    """Gets the current state of the execution

    Returns:
        A response instance
    """
    return sendState()

if __name__ == '__main__':
    app.run(debug=args.debug, port=args.port)

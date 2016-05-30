import argparse
from processingManager import ProcessingManager
from flask import Flask, request, jsonify
from flask.ext.socketio import SocketIO

parser = argparse.ArgumentParser(description='Starts the server to process tracks')
parser.add_argument('-s', '--source', dest='source', metavar='s', type=str,
        required=True,
        help='folder to extract the tracks from')
parser.add_argument('-b', '--backup', dest='backup', metavar='b', type=str,
        default='./backup',
        help='backup folder for the original GPX files')
parser.add_argument('-l', '--life', dest='life', metavar='l', type=str,
        default='./life',
        help='folder to save the each trip\'s LIFE files')
parser.add_argument('-d', '--dest', dest='dest', metavar='d', type=str,
        default='./dest',
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

manager = ProcessingManager(args.source, args.dest, args.backup, args.life)

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

@app.route('/completeTrip', methods=['GET'])
def completeTrip():
    """Gets trips already made from one point, to another

    Returns:
        A response instance
    """
    payload = request.get_json(force=True)
    return manager.completeTrip(payload)

if __name__ == '__main__':
    app.run(debug=args.debug, port=args.port)

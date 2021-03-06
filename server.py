# -*- coding: utf-8 -*-
"""
Entry point
Spawns a server that coodinates the operations
"""
import argparse
from flask import Flask, request, jsonify
from tracktotrip import Point
from processmysteps.process_manager import ProcessingManager

parser = argparse.ArgumentParser(description='Starts the server to process tracks')
parser.add_argument('-p', '--port', dest='port', metavar='p', type=int,
        default=5000,
        help='port to use')
parser.add_argument('-H', '--host', dest='host', metavar='h', type=str,
        default='0.0.0.0',
        help='host name')
parser.add_argument('--debug', dest='debug', action='store_true',
        default=False,
        help='print server debug information')
parser.add_argument('--verbose', dest='verbose',
        action='store_false',
        help='print debug information of processing stage')
parser.add_argument('--config', '-c', dest='config', metavar='c', type=str,
        help='configuration file')
args = parser.parse_args()

app = Flask(__name__)
# socketio = SocketIO(app)

manager = ProcessingManager(args.config)

def set_headers(response):
    """ Sets appropriate headers

    Args:
        response (:obj:`flask.response`)
    Returns:
        :obj:`flask.response`
    """
    response.headers['Access-Control-Allow-Origin'] = '*'
    return response

def send_state():
    """ Helper function to send state

    Creates a response with the current state, converts it to JSON and sets its headers

    Returns:
        :obj:`flask.response`
    """
    response = jsonify(manager.current_state())
    return set_headers(response)

def undo_step():
    """ Undo current state
    """
    manager.restore()

@app.route('/previous', methods=['GET'])
def previous():
    """Restores a previous state

    Returns:
        :obj:`flask.response`
    """
    manager.restore()
    return send_state()

@app.route('/next', methods=['POST'])
def next():
    """Advances the progress

    Returns:
        :obj:`flask.response`
    """
    payload = request.get_json(force=True)
    manager.process(payload)
    return send_state()

@app.route('/current', methods=['GET'])
def current():
    """Gets the current state of the execution

    Returns:
        :obj:`flask.response`
    """
    return send_state()

@app.route('/completeTrip', methods=['POST'])
def complete_trip():
    """Gets trips already made from one point, to another

    Returns:
        :obj:`flask.response`
    """
    payload = request.get_json(force=True)
    from_point = Point.from_json(payload['from'])
    to_point = Point.from_json(payload['to'])
    return set_headers(jsonify(manager.complete_trip(from_point, to_point)))

@app.route('/config', methods=['POST'])
def set_configuration():
    """ Sets the current configuration, and returns it

    Returns:
        :obj:`flask.response`
    """
    payload = request.get_json(force=True)
    manager.update_config(payload)
    return set_headers(jsonify(manager.config))

@app.route('/config', methods=['GET'])
def get_configuration():
    """ Gets the current configuration, and returns it

    Returns:
        :obj:`flask.response`
    """
    return set_headers(jsonify(manager.config))

@app.route('/changeDay', methods=['POST'])
def change_day():
    """ Changes the current day

    Returns:
        :obj:`flask.response`
    """
    payload = request.get_json(force=True)
    manager.change_day(payload['day'])
    return send_state()

@app.route('/reloadQueue', methods=['GET'])
def reload_queue():
    """ Changes the current day

    Returns:
        :obj:`flask.response`
    """
    manager.reload_queue()
    return send_state()

@app.route('/bulkProcess', methods=['GET'])
def bulk_process():
    """ Starts bulk processing

    Returns:
        :obj:`flask.response`
    """
    manager.bulk_process()
    return send_state()

@app.route('/loadLIFE', methods=['POST'])
def load_life():
    """ Loads a life formated string into the database

    Returns:
        :obj:`flask.response`
    """
    payload = request.data
    manager.load_life(payload)
    return send_state()

@app.route('/location', methods=['GET'])
def location_suggestion():
    """ Gets a location suggestion

    Returns:
        :obj:`list` of :obj:`str`
    """
    lat = float(request.args.get('lat'))
    lon = float(request.args.get('lon'))
    response = jsonify(manager.location_suggestion(Point(lat, lon, None)))
    return set_headers(response)

@app.route('/canonicalTrips', methods=['GET'])
def get_canonical_trips():
    response = jsonify(manager.get_canonical_trips())
    return set_headers(response)

@app.route('/canonicalLocations', methods=['GET'])
def get_canonical_locations():
    response = jsonify(manager.get_canonical_locations())
    return set_headers(response)

@app.route('/transportation', methods=['POST'])
def get_transportation_suggestions():
    payload = request.get_json(force=True)
    points = [Point.from_json(p) for p in payload['points']]
    response = jsonify(manager.get_transportation_suggestions(points))
    return set_headers(response)

@app.route('/removeDay', methods=['POST'])
def remove_day():
    payload = request.get_json(force=True)
    manager.remove_day(payload["day"])
    return send_state()

@app.route('/skipDay', methods=['POST'])
def skip_day():
    manager.next_day(delete=False)
    return send_state()

if __name__ == '__main__':
    app.run(debug=args.debug, port=args.port, host=args.host, threaded=True)

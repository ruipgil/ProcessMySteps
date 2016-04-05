import argparse
import tracktotrip as tt
from flask import Flask, request, jsonify
from flask.ext.socketio import SocketIO

from os import listdir, stat
from os.path import join

parser = argparse.ArgumentParser(description='Starts the server to process tracks')
parser.add_argument('-s', '--source', dest='source', metavar='s', type=str,
        required=True,
        help='folder to extract the tracks from')
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

def mapFileToDetails(f):
    completePath = join(args.source, f)
    (_, _, _, _, _, _, size, _, creationDate, _) = stat(completePath)

    return {
            'name': f,
            'path': completePath,
            'size': size,
            'date': creationDate
            }

def listGpxs():
    files = listdir(args.source)
    files = filter(lambda f: f.split('.')[-1] == 'gpx', files)
    files = map(mapFileToDetails, files)
    files = sorted(files, key=lambda f: f['date'])
    return files


class Step:
    preview = 0
    adjust = 1
    annotate = 2

    N = 3

    @staticmethod
    def next(current):
        return (current + 1) % Step.N

    @staticmethod
    def prev(current):
        return (current - 1) % Step.N

def loadGpx(filePath):
    return tt.Track.fromGPX(filePath)


# queue of files to process
currentQueue = listGpxs()
# current file that is being processed
currentFile = currentQueue[0]
# current step of processing
currentStep = Step.preview
# track history, max size of 3
currentTrackHistory = [loadGpx(currentFile['path'])[0].preprocess()]

app = Flask(__name__)
socketio = SocketIO(app)

def setHeaders(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    return response

def preview(fileName):
    trackFile = join(args.source, fileName)
    track = loadGpx(trackFile)[0]
    return track, None

def adjust(touched, track):
    track = tt.Track.fromJSON(track)
    track = track.preprocess()
    track = track.toTrip()
    return track, None

def annotate(touched, track):
    track = tt.Track.fromJSON(track)
    track.inferLocation()
    return track, None

def store():
    return None, None

def executeStep(data):
    global currentTrackHistory
    global currentStep
    global currentFile

    track = None
    more = None

    next = Step.next(currentStep)
    if next == Step.preview:
        track, more = preview(currentFile['name'])
    elif next == Step.adjust:
        track, more = adjust(data['touched'], data['track'])
    elif next == Step.annotate:
        # TODO annotate
        track, more = annotate(data['touched'], data['track'])
        # TODO load next track?
    else:
        print('Invalid step', currentStep)
        return None, None

    currentStep = next
    currentTrackHistory.append(track)

    return track, more

def undoStep():
    global currentStep
    global currentTrackHistory

    if currentStep == Step.preview:
        # Do nothing
        return currentTrackHistory[0], None
    else:
        currentStep = Step.prev(currentStep)
        track = currentTrackHistory.pop()
        track = currentTrackHistory.pop()
        # TODO: only returns track
        return track, None

@app.route('/previous', methods=['GET'])
def previous():
    track, more = undoStep()
    response = jsonify(
            step=currentStep,
            files = currentQueue,
            remaining = len(currentQueue),
            track=track.toJSON())
    return setHeaders(response)

@app.route('/next', methods=['POST'])
def next():
    payload = request.get_json(force=True)
    track, more = executeStep(payload)
    response = jsonify(
            step=currentStep,
            files = currentQueue,
            remaining = len(currentQueue),
            track=track.toJSON())
    return setHeaders(response)

@app.route('/current', methods=['GET'])
def current():
    track = currentTrackHistory[-1]
    response = jsonify(
            step = currentStep,
            files = currentQueue,
            remaining = len(currentQueue),
            track = track.toJSON()
            )
    return setHeaders(response)

@app.route('/info', methods=['GET'])
def info():
    response = jsonify(
            step = currentStep,
            files = currentQueue,
            remaining = len(currentQueue)
            )
    return setHeaders(response)

if __name__ == '__main__':
    app.run(debug=args.debug, port=args.port)

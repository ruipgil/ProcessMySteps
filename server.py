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
    print('preview will')
    track = loadGpx(trackFile)
    print('preview done')
    return fileName, track, None


def adjust(touched, track):
    track = tt.Track.fromJSON(track)
    track = track.toTrip()
    return track.name, track, None

def annotate():
    # TODO
    return None, None, None

def store():
    return None, None, None

def executeStep(data):
    if currentStep == Step.preview:
        return preview(currentFile['name'])
    elif currentStep == Step.adjust:
        return adjust(data['touched'], data['track'])
    elif currentStep == Step.annotate:
        # TODO annotate
        return annotate(data['semantics'], data['track'])
    else:
        return None

def advanceStep(toStore):
    global currentTrackHistory
    global currentStep
    global currentFile
    currentTrackHistory.append(toStore)

    print(currentStep)
    if currentStep == Step.preview:
        currentStep = Step.adjust
    elif currentStep == Step.adjust:
        currentStep = Step.annotate
    elif currentStep == Step.annotate:
        currentStep = Step.preview
        currentQueue = listGpxs()
        currentFile = currentQueue[0]
        currentTrackHistory = loadGpx(currentFile['path'])
    else:
        currentStep = Step.adjust
    print(currentStep)

@app.route('/next', methods=['POST'])
def next():
    name = None
    track = None

    payload = request.get_json(force=True)
    advanceStep(None)
    name, track, more = executeStep(payload)
    print('exec')
    # advanceStep({
        # 'name': name,
        # 'track': track,
        # 'more': more
        # })
    response = jsonify(
            step=currentStep,
            files = currentQueue,
            remaining = len(currentQueue),
            name=name,
            track=track.toJSON())
    print('json done')
    print('advance')
    return setHeaders(response)

@app.route('/current', methods=['GET'])
def current():
    track = currentTrackHistory[-1]
    print(track.segments)
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

import tracktotrip as tt
from tracktotrip.transportationMode import Classifier
import db
from os import listdir, stat, rename
from os.path import join, expanduser
import json
import re
from collections import OrderedDict
import datetime

default_config = {
    'input_path': None,
    'dest_path': None,
    'backup_path': None,
    'dest_path': None,
    'life_all': None,
    'db': {
        'host': None,
        'port': None,
        'name': None,
        'user': None,
        'pass': None
    },
    'preprocess': {
        'max_acc': tt.preprocess.MAX_ACC
    },
    'smoothing': {
        'use': True,
        'algorithm': 'inverse',
        'noise': 5
    },
    'segmentation': {
        'use': True,
        'epsilon': 0.15,
        'min_samples': 80
    },
    'simplification': {
        'max_distance': 0.01,
        'max_time': 5
    },
    'location': {
        'max_distance': 20,
        'limit': 5,
        'google_key': ''
    },
    'transportation': {
        'remove_stops': False,
        'min_time': 10,
        'classifier_path': None
    },
    'trip_learning': {
        'epsilon': 0.0,
        'classifier_path': None,
    },
    'trip_name_format': '%Y-%m-%d'
}

def saveToFile(path, content):
    with open(path, "w") as f:
        f.write(content)

TIME_RX = re.compile('\<time\>([^\<]+)\<\/time\>')
def predictStartDate(filename):
    f = open(filename, 'r').read()
    result = TIME_RX.search(f)
    return gt(result.group(1))

def gt(dt_str):
    return datetime.datetime.strptime(dt_str, "%Y-%m-%dT%H:%M:%SZ")

class Step:
    preview = 0
    adjust = 1
    annotate = 2
    N = 3
    done = -1
    @staticmethod
    def next(current):
        return (current + 1) % Step.N

    @staticmethod
    def prev(current):
        return (current - 1) % Step.N

class ProcessingManager:
    """Manages the processing phases

    Arguments:
        queue: Array of strings, with the files to be
            processed. Doesn't include the current file
        currentFile: String with the current file being
            processed
        history: Array of TrackToTrip.Track. Must always
            have length greater or equal to ONE. The
            last element is the current state of the system
        INPUT_PATH: String with the path to the input folder
        BACKUP_PATH: String with the path to the backup folder
        OUTPUT_PATH: String with the path to the output folder
        LIFE_PATH: String with the path to the LIFE output
            folder
    """

    def __init__(self, configFile):
        config = json.loads(open(configFile, 'r').read())
        self.config = dict(default_config)
        self.config.update(config)

        clfPath = self.config['transportation']['classifier_path']
        if clfPath:
            self.clf = Classifier.load_from_file(expanduser(clfPath))
        else:
            self.clf = Classifier.create()

        self.queue = {}
        self.currentStep = None
        self.history = []
        self.reset()
        dbc = self.config['db']
        db.checkConn(dbc['host'], dbc['name'], dbc['port'], dbc['user'], dbc['pass'])

    def listGpxs(self):
        """Lists gpx files in the INPUT_PATH, and their details

        Result is sorted by date

        Returns:
            An array of maps. Each of those has a name, (complete)
            path, size and date keys
        """

        input_path = expanduser(self.config['input_path'])
        files = listdir(input_path)
        files = filter(lambda f: f.split('.')[-1] == 'gpx', files)

        def mapFileToDetails(f):
            completePath = join(input_path, f)
            (_, _, _, _, _, _, size, _, _, _) = stat(completePath)

            date = predictStartDate(completePath)
            return {
                    'name': f,
                    'path': completePath,
                    'size': size,
                    'start': date,
                    'date': date.date().isoformat()
                    }

        files = map(mapFileToDetails, files)
        files = sorted(files, key=lambda f: f['date'])
        return files

    def reset(self):
        """Resets all variables and computes the first step

        Returns:
            This instance
        """

        queue = self.listGpxs()
        if len(queue) > 0:
            self.currentStep = Step.preview
            self.loadDays()
        else:
            self.queue = {}
            self.currentDay = None
            self.currentStep = Step.done
            self.history = []

        return self

    def changeDay(self, day):
        if day in self.queue.keys():
            keyToUse = day
            gpxsToUse = self.queue[keyToUse]
            gpxsToUse = map(lambda gpx: self.loadGpx(gpx['path']), gpxsToUse)

            self.currentDay = keyToUse

            segs = []
            for g in gpxsToUse:
                segs.extend(g.segments)

            track = tt.Track(segments=segs)
            self.history = [track]
            self.currentStep = Step.preview
        else:
            print('Cannot find day')

    def reloadQueue(self):
        queue = {}

        gpxs = self.listGpxs()
        for gpx in gpxs:
            day = gpx['date']
            if day in queue:
                queue[day].append(gpx)
            else:
                queue[day] = [gpx]

        self.queue = OrderedDict(sorted(queue.items()))

    def nextDay(self, delete=True):
        if delete:
            del self.queue[self.currentDay]
        self.changeDay(self.queue.keys()[0])

    def loadDays(self):
        """Loads all tracks of the most distant day
        """
        self.reloadQueue()
        self.nextDay(delete=False)

    def restore(self):
        if self.currentStep != Step.done and self.currentStep != Step.preview:
            self.currentStep = Step.prev(self.currentStep)
            self.history.pop()

    def process(self, data):
        """Processes the current step

        Args:
            data: Map with the JSON payload received from the
                client
        Returns:
            A TrackToTrip.Track instance.
        """

        step = self.currentStep
        changes = data['changes']
        life = data['LIFE']
        track = tt.Track.fromJSON(data['track']) if len(changes) > 0 else self.currentTrack().copy()
        if step == Step.preview:
            result = self.previewToAdjust(track, changes)
        elif step == Step.adjust:
            result = self.adjustToAnnotate(track)
        elif step == Step.annotate:
            t = track.inferLocation().inferTransportationMode()
            return self.annotateToNext(t, life)
        else:
            return None

        if result:
            self.currentStep = Step.next(self.currentStep)
            self.history.append(result)

        return result

    def bulkProcess(self):
        while len(self.queue.values()) > 0:
            # preview -> adjust
            self.process({ 'changes': [], 'LIFE': '' })
            # adjust -> annotate
            self.process({ 'changes': [], 'LIFE': '' })
            # annotate -> store
            # TODO: LIFE
            self.process({ 'changes': [], 'LIFE': 'TODO' })
        print('Bulk process')

    def loadGpx(self, f):
        """Loads the current file as a GPX

        Returns:
            A TrackToTrip.Track instance
        """

        return tt.Track.fromGPX(f)[0]

    def previewToAdjust(self, track, changes):
        """Processes a track so that it becomes a trip

        More information in TrackToTrip.Track.toTrip method

        Args:
            track: a TrackToTrip.Track instance. It's the same
                as the current state, if there were no changes
            changes: Array of maps detailing the changes made
                to the track. If empty, no changes were done
                by the client
        Returns:
            A TrackToTrip.Track instance
        """

        # TODO: use changes
        c = self.config
        if not track.preprocessed:
            track.preprocess(max_acc=c['preprocess']['max_acc'])

        return track.toTrip(
            smooth_strategy=c['smoothing']['algorithm'],
            smooth_noise=c['smoothing']['noise'],
            seg_eps=c['segmentation']['epsilon'],
            seg_min_samples=c['segmentation']['min_samples'],
            simplify_max_distance=c['simplification']['max_distance'],
            simplify_max_time=c['simplification']['max_time'],
            file_format=c['trip_name_format']
        )

    def adjustToAnnotate(self, track):
        """Extracts location and transportation modes

        Args:
            track: a TrackToTrip.Track instance. It's the same
                as the current state, if there were no changes
            changes: Array of maps detailing the changes made
                to the track. If empty, no changes were done
                by the client
        Returns:
            A TrackToTrip.Track instance
        """

        # if not track.preprocessed:
        #     track.preprocess(max_acc=self.config['preprocess']['max_acc'])

        c = self.config
        c_loc = self.config['location']

        conn, cur = self.db_connect()

        def get_locations(point, radius):
            if cur:
                return db.queryLocations(cur, point.lat, point.lon, radius)
            else:
                return []

        track.inferLocation(
            get_locations,
            max_distance=c_loc['max_distance'],
            google_key=c_loc['google_key'],
            limit=c_loc['limit']
        )
        track.inferTransportationMode(self.clf, removeStops=c['transportation']['remove_stops'], dt_threshold=c['transportation']['min_time'])

        self.db_dispose(conn, cur)

        return track

    def db_connect(self):
        dbc = self.config['db']
        conn = db.connectDB(dbc['host'], dbc['name'], dbc['port'], dbc['user'], dbc['pass'])
        if conn:
            return conn, conn.cur()
        else:
            return None, None

    def db_dispose(self, conn, cur):
        if conn and cur:
            conn.commit()
            cur.close()
            conn.close()

    def annotateToNext(self, track, life):
        """Stores the track and dequeues another track to be
        processed.

        Moves the current GPX file from the INPUT_PATH to the
        BACKUP_PATH, creates a LIFE file in the LIFE_PATH
        and creates a trip entry in the database. Finally the
        trip is exported as a GPX file to the OUTPUT_PATH.

        The database variables, DB_NAME, DB_HOST, DB_USER and
        DB_PASS, must be passed through environment variables

        Args:
            track: a TrackToTrip.Track instance. It's the same
                as the current state, if there were no changes
            changes: Array of maps detailing the changes made
                to the track. If empty, no changes were done
                by the client
        """

        # Backup
        rename(self.currentFile['path'], join(expanduser(self.config['backup_path']), self.currentFile['name']))

        # Export trip to GPX
        saveToFile(join(expanduser(self.config['output_path']), track.name), track.toGPX())

        # TODO: update classifier

        # To LIFE
        if self.config['life_path']:
            saveToFile(join(expanduser(self.config['life_path']), track.name), life)

            if self.config['life_all']:
                life_all_file = expanduser(self.config['life_all'])
            else:
                life_all_file = join(expanduser(self.config['life_path']), 'all.life')

            with open(life_all_file, 'rw') as f:
                content = f.read()
                content = content + "\n\n"
                content = life
                f.write(content)

        conn, cur = self.db_connect()

        if conn and cur:
            trips_ids = []
            for trip in track.segments:
                # To database
                trip_id = db.insertSegment(cur, trip)
                trips_ids.append(trip_id)

                # Build/learn canonical trip
                canonicalTrips = db.matchCanonicalTrip(cur, trip)
                insertFn = lambda (can_trip, mother_trip_id): db.insertCanonicalTrip(cur, can_trip, mother_trip_id)
                updateFn = lambda (can_id, trip, mother_trip_id): db.updateCanonicalTrip(cur, can_id, trip, mother_trip_id)
                tt.learn_trip(trip, trip_id, canonicalTrips, insertFn, updateFn)

            db.insertStays(cur, trip, trips_ids, life)

            conn.commit()
            cur.close()
            conn.close()

        self.nextDay()
        self.currentStep = Step.preview
        return self.currentTrack()

    def currentTrack(self):
        return self.history[-1]

    def currentState(self):
        return {
                'step': self.currentStep,
                'queue': self.queue.items(), #map(lambda (date, tracks): { 'date': str(date), 'tracks': tracks}, self.queue.items()),
                'track': self.currentTrack().toJSON(),
                'currentDay': self.currentDay
                }

    def completeTrip(self, data):
        """Processes the current step

        Args:
            data: Map with the JSON payload received from the
                client. Requires properties 'from' and 'to',
                which should countain point representations
                with 'lat' and 'lon'.
        Returns:
            An array of TrackToTrip.Track.
        """
        fromPoint = data['from']
        toPoint = data['to']

        bb = (
                min(fromPoint['lat'], toPoint['lat']),
                min(fromPoint['lon'], toPoint['lon']),
                max(fromPoint['lat'], toPoint['lat']),
                max(fromPoint['lon'], toPoint['lon'])
                )

        conn, cur = self.db_connect()
        if conn and cur:
            # get matching canonical trips, based on bounding box
            canonicalTrips = db.matchCanonicalTripBounds(cur, bb)

            conn.commit()
            cur.close()
            conn.close()

        result = []
        weights = []
        totalWeights = 0.0
        fromP = tt.Point(0, fromPoint['lat'], fromPoint['lon'], None)
        toP = tt.Point(0, toPoint['lat'], toPoint['lon'], None)
        # match points in lines
        for (tripId, trip, count) in canonicalTrips:
            fromIndex = trip.closestPointTo(fromP)
            toIndex = trip.closestPointTo(toP)
            if fromIndex != toIndex and fromIndex != -1 and toIndex != -1:
                r = trip.slice(fromIndex, toIndex)
                result.append(map(lambda p: [p.lat, p.lon], r.points))
                weights.append(count)
                totalWeights = totalWeights + count

        return {
                'possibilities': result,
                'weights': map(lambda v: v / totalWeights, weights)
                }


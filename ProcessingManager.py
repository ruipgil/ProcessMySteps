import tracktotrip as tt
import db
from os import listdir, stat #rename,
from os.path import join
import numpy as np

def saveToFile(path, content):
    with open(path, "w") as f:
        f.write(content)

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

    def __init__(self, inputPath, outputPath, backupPath, lifePath):
        self.queue = []
        self.currentFile = None
        self.currentStep = None
        self.history = []
        self.INPUT_PATH = inputPath
        self.OUTPUT_PATH = outputPath
        self.BACKUP_PATH = backupPath
        self.LIFE_PATH = lifePath
        self.reset()
        db.checkConn()

    def listGpxs(self):
        """Lists gpx files in the INPUT_PATH, and their details

        Result is sorted by date

        Returns:
            An array of maps. Each of those has a name, (complete)
            path, size and date keys
        """

        files = listdir(self.INPUT_PATH)
        files = filter(lambda f: f.split('.')[-1] == 'gpx', files)

        def mapFileToDetails(f):
            completePath = join(self.INPUT_PATH, f)
            (_, _, _, _, _, _, size, _, creationDate, _) = stat(completePath)

            return {
                    'name': f,
                    'path': completePath,
                    'size': size,
                    'date': creationDate
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
            self.queue = queue
            self.currentFile = queue.pop()
            self.currentStep = Step.preview
            self.loadDay()
            # state = self.loadGpx().preprocess()
            # self.history = [state]
        else:
            self.queue = []
            self.currentFile = None
            self.currentStep = Step.done
            self.history = []

        return self

    def loadDay(self):
        """Loads all tracks of the most distant day
        """

        gpxs = self.listGpxs()
        gpxsToUse = []
        dayToUse = None
        dateDayToUse = None
        dateOfLastGpxToUse = None
        for gpx in gpxs:
            if dayToUse is None:
                track = self.loadGpx(gpx['path'])
                dayToUse = track.getStartTime()
                dateDayToUse = dayToUse.date()
                # timeOfLastGpxToUse = track.getEndTime()
                gpxsToUse.append(track)
            else:
                track = self.loadGpx(gpx['path'])
                ts = track.getStartTime()
                ts_date = ts.date()
                if ts_date < dateDayToUse:
                    # Reset usage
                    dayToUse = ts
                    dateDayToUse = dayToUse.date()
                    gpxsToUse = [track]
                elif ts_date == dateDayToUse:
                    # Append
                    gpxsToUse.append(track)
                    if ts < dayToUse:
                        dayToUse = ts

        segs = []
        for g in gpxsToUse:
            segs.extend(g.segments)

        track = tt.Track(segments=segs)
        self.history = [track]

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
        touches = [1] # TODO: data['touches']
        track = tt.Track.fromJSON(data['track']) if len(touches) > 0 else self.currentTrack().copy()
        if step == Step.preview:
            result = self.previewToAdjust(track, touches)
        elif step == Step.adjust:
            result = self.adjustToAnnotate(track, touches)
        elif step == Step.annotate:
            t = self.currentTrack().toTrip().inferLocation().inferTransportationMode()
            return self.annotateToNext(t)
        else:
            print('Invalid step', self.currentStep)
            return None

        if result:
            self.currentStep = Step.next(self.currentStep)
            self.history.append(result)

        return result


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

        print("preview to adjust")

        if not track.preprocessed:
            track.preprocess()

        return track.toTrip()

    def adjustToAnnotate(self, track, changes):
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

        print("adjust to annotate")

        if not track.preprocessed:
            track.preprocess()

        track.inferLocation()
        track.inferTransportationMode()

        return track

    def annotateToNext(self, track):
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

        print("annotate to next")

        if not track.preprocessed:
            track.preprocess()

        # Backup
        # rename(self.currentFile['path'], join(self.BACKUP_PATH, self.currentFile['name']))

        # Export trip to GPX
        saveToFile(join(self.OUTPUT_PATH, track.name), track.toGPX())

        # To LIFE
        saveToFile(join(self.LIFE_PATH, track.name), track.toLIFE())

        for trip in track.segments:
            # To database
            trip_id = db.insertSegment(trip)

            # Build/learn canonical trip
            canonicalTrips = db.matchCanonicalTrip(trip)
            tt.learn_trip(trip, trip_id, canonicalTrips, db.insertCanonicalTrip, db.updateCanonicalTrip)

        self.reset()
        return self.currentTrack()

    def currentTrack(self):
        return self.history[-1]

    def currentState(self):
        return {
                'step': self.currentStep,
                'queue': self.queue,
                'track': self.currentTrack().toJSON()
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

        # get matching canonical trips, based on bounding box
        canonicalTrips = db.matchCanonicalTripBounds(bb)

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

        print(weights, totalWeights)
        return {
                'possibilities': result,
                'weights': map(lambda v: v / totalWeights, weights)
                }


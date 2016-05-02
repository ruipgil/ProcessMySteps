import TrackToTrip as tt
from path import join, listdir, stat
import os

def saveToFile(path, content):
    with open(path, "w") as f:
        f.write(content)

def trackToDB(track):
    return

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

    def __init__(self, inputPath, backupPath, lifePath):
        self.queue = []
        self.currentFile = None
        self.currentStep = None
        self.history = []
        self.INPUT_PATH = inputPath
        self.BACKUP_PATH = backupPath
        self.LIFE_PATH = lifePath
        self.reset()

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
            state = self.loadGpx(self.currentFile).preprocess()
            self.history = [state]
        else:
            self.queue = []
            self.currentFile = None
            self.currentStep = Step.done
            self.history = []

        return self

    def process(self, data):
        """Processes the current step

        Args:
            data: Map with the JSON payload received from the
                client
        Returns:
            A TrackToTrip.Track instance.
        """

        step = self.currentStep
        touches = data['touches']
        track = tt.Track.fromJSON(data['track']) if len(touches) > 0 else self.currentTrack()
        if step == Step.preview:
            return self.previewToAdjust(track, touches)
        elif step == Step.adjust:
            return self.adjustToAnnotate(track, touches)
        elif step == Step.annotate:
            return self.annotateToNext(track, touches)
        else:
            print('Invalid step', self.currentStep)
            return None


    def loadGpx(self):
        """Loads the current file as a GPX

        Returns:
            A TrackToTrip.Track instance
        """

        return tt.Track.fromGPX(join(self.INPUT_PATH, self.currentFile))[0]

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

        if not track.isPreprocessed():
            track.preprocess()

        return track.toTrip()

    def adjustToAnnote(self, track, changes):
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

        track.inferLocation()
        track.inferTransportation()

        return track

    def annotateToNext(self, track):
        """Stores the track and dequeues another track to be
        processed.

        Moves the current GPX file from the INPUT_FOLDER to the
        BACKUP_FOLDER, creates a LIFE file in the LIFE_FOLDER
        and creates a trip entry in the database. Finally the
        trip is exported as a GPX file to the OUTPUT_FOLDER.

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
        os.rename(join(self.INPUT_FOLDER, self.currentFile), join(self.BACKUP_FOLDER, self.currentFile))
        # Export trip to GPX
        saveToFile(join(self.OUTPUT_FOLDER, track.name), track.toGPX())
        # To LIFE
        saveToFile(join(self.LIFE_FOLDER, track.name), track.toLIFE())
        # To database
        trackToDB(track)

        self.reset()
        return None

    def currentTrack(self):
        return self.history[-1]

    def currentState(self):
        return self.currentStep, self.currentTrack()


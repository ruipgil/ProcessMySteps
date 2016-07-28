# -*- coding: utf-8 -*-
"""
Contains class that orchestrates processing
"""
import re
import json
from os import listdir, stat, rename
from os.path import join, expanduser
from collections import OrderedDict
import tracktotrip as tt
from tracktotrip.classifier import Classifier
from tracktotrip.learn_trip import learn_trip, complete_trip
from tracktotrip.transportation_mode import learn_transportation_mode
from processmysteps import db

from .default_config import CONFIG

def save_to_file(path, content, mode="w"):
    """ Saves content to file

    Args:
        path (str): filepath, including filename
        content (str): content to write to file
        mode (str, optional): mode to write, defaults to w
    """
    with open(path, mode) as dest_file:
        dest_file.write(content.encode('utf-8'))

TIME_RX = re.compile(r'\<time\>([^\<]+)\<\/time\>')
def predict_start_date(filename):
    """ Predicts the start date of a GPX file

    Reads the first valid date, by matching TIME_RX regular expression

    Args:
        filename (str): file path
    Returns:
        :obj:`datetime.datetime`
    """
    with open(filename, 'r') as opened_file:
        result = TIME_RX.search(opened_file.read())
        return tt.utils.isostr_to_datetime(result.group(1))

def file_details(base_path, filepath):
    """ Returns file details

    Example:
        >>> file_details('/users/username/tracks/', '25072016.gpx')
        {
            'name': '25072016.gpx',
            'path': '/users/username/tracks/25072016.gpx',
            'size': 39083,
            'start': <datetime.datetime>,
            'date': '2016-07-25t07:40:52z'
        }

    Args:
        base_path (str): Base path
        filename (str): Filename
    Returns:
        :obj:`dict`: See example
    """
    complete_path = join(base_path, filepath)
    (_, _, _, _, _, _, size, _, _, _) = stat(complete_path)

    date = predict_start_date(complete_path)
    return {
        'name': filepath,
        'path': complete_path,
        'size': size,
        'start': date,
        'date': date.date().isoformat()
    }


class Step(object):
    """ Step enumeration
    """
    preview = 0
    adjust = 1
    annotate = 2
    done = -1
    _len = 3

    @staticmethod
    def next(current):
        """ Advances from one step to the next

        Args:
            current (int): Current step
        Returns:
            int: next step
        """
        return (current + 1) % Step._len

    @staticmethod
    def prev(current):
        """ Backs one step

        Args:
            current (int): Current step
        Returns:
            int: previous step
        """
        return (current - 1) % Step._len

class ProcessingManager(object):
    """ Manages the processing phases

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

    def __init__(self, config_file):
        with open(expanduser(config_file), 'r') as config_file:
            config = json.loads(config_file.read())
        self.config = dict(CONFIG)
        self.config.update(config)

        clf_path = self.config['transportation']['classifier_path']
        if clf_path:
            self.clf = Classifier.load_from_file(open(expanduser(clf_path), 'rb'))
        else:
            self.clf = Classifier()

        self.is_bulk_processing = False
        self.queue = {}
        self.current_step = None
        self.history = []
        self.current_day = None
        self.reset()
        # dbc = self.config['db']
        # db.checkConn(dbc['host'], dbc['name'], dbc['user'], dbc['port'], dbc['pass'])

    def list_gpxs(self):
        """ Lists gpx files from the input path, and some details

        Result is sorted by start date
        See `file_details`

        Returns:
            :obj:`list` of :obj:`dict`
        """

        input_path = expanduser(self.config['input_path'])
        files = listdir(input_path)
        files = [f for f in files if f.split('.')[-1] == 'gpx']

        files = [file_details(input_path, f) for f in files]
        files = sorted(files, key=lambda f: f['date'])
        return files

    def reset(self):
        """ Resets all variables and computes the first step

        Returns:
            :obj:`ProcessingManager`: self
        """
        queue = self.list_gpxs()
        if len(queue) > 0:
            self.current_step = Step.preview
            self.load_days()
        else:
            self.queue = {}
            self.current_day = None
            self.current_step = Step.done
            self.history = []

        return self

    def change_day(self, day):
        """ Changes current day, and computes first step

        Args:
            day (:obj:`datetime.date`): Only loads if it's an existing key in queue
        """
        if day in self.queue.keys():
            key_to_use = day
            gpxs_to_use = self.queue[key_to_use]
            gpxs_to_use = [tt.Track.from_gpx(gpx['path'])[0] for gpx in gpxs_to_use]

            self.current_day = key_to_use

            segs = []
            for gpx in gpxs_to_use:
                segs.extend(gpx.segments)

            track = tt.Track('', segments=segs)
            self.history = [track]
            self.current_step = Step.preview
        else:
            raise TypeError('Cannot find any track for day: %s' % day)

    def reload_queue(self):
        """ Reloads the current queue, filling it with the current file's details existing
            in the input folder
        """
        queue = {}

        gpxs = self.list_gpxs()
        for gpx in gpxs:
            day = gpx['date']
            if day in queue:
                queue[day].append(gpx)
            else:
                queue[day] = [gpx]

        self.queue = OrderedDict(sorted(queue.items()))

    def next_day(self, delete=True):
        """ Advances a day (to next existing one)

        Args:
            delete (bool, optional): True to delete day from queue, NOT from input folder.
                Defaults to true
        """
        if delete:
            del self.queue[self.current_day]
        self.change_day(list(self.queue.keys())[0])

    def load_days(self):
        """ Reloads queue and sets the current day as the oldest one
        """
        self.reload_queue()
        self.next_day(delete=False)

    def restore(self):
        """ Backs down a pass
        """
        if self.current_step != Step.done and self.current_step != Step.preview:
            self.current_step = Step.prev(self.current_step)
            self.history.pop()

    def process(self, data):
        """ Processes the current step

        Args:
            data (:obj:`dict`): JSON payload received from the client
        Returns:
            :obj:`tracktotrip.Track`
        """
        step = self.current_step
        changes = data['changes']
        life = data['LIFE']

        if len(changes) > 0:
            track = tt.Track.from_json(data['track'])
        else:
            track = self.current_track().copy()

        if step == Step.preview:
            result = self.preview_to_adjust(track)#, changes)
        elif step == Step.adjust:
            result = self.adjust_to_annotate(track)
        elif step == Step.annotate:
            if not life or len(life) == 0:
                life = track.to_life()
            return self.annotate_to_next(track, life)
        else:
            return None

        if result:
            self.current_step = Step.next(self.current_step)
            self.history.append(result)

        return result

    def bulk_process(self):
        """ Starts bulk processing all GPXs queued
        """
        self.is_bulk_processing = True
        while len(self.queue.values()) > 0:
            # preview -> adjust
            self.process({'changes': [], 'LIFE': ''})
            # adjust -> annotate
            self.process({'changes': [], 'LIFE': ''})
            # annotate -> store
            self.process({'changes': [], 'LIFE': ''})
        self.is_bulk_processing = False

    def preview_to_adjust(self, track):
        """ Processes a track so that it becomes a trip

        More information in `tracktotrip.Track`'s `to_trip` method

        Args:
            track (:obj:`tracktotrip.Track`)
            changes (:obj:`list` of :obj:`dict`): Details of, user made, changes
        Returns:
            :obj:`tracktotrip.Track`
        """
        config = self.config

        track.name = track.generate_name(config['trip_name_format'])
        return track.to_trip(
            smooth_strategy=config['smoothing']['algorithm'],
            smooth_noise=config['smoothing']['noise'],
            seg_eps=config['segmentation']['epsilon'],
            seg_min_time=config['segmentation']['min_time'],
            simplify_max_dist_error=config['simplification']['max_dist_error'],
            simplify_max_speed_error=config['simplification']['max_speed_error']
        )

    def adjust_to_annotate(self, track):
        """ Extracts location and transportation modes

        Args:
            track (:obj:`tracktotrip.Track`)
        Returns:
            :obj:`tracktotrip.Track`
        """

        config = self.config
        c_loc = config['location']

        conn, cur = self.db_connect()

        def get_locations(point, radius):
            """ Gets locations within a radius of a point

            See `db.query_locations`

            Args:
                point (:obj:`tracktotrip.Point`)
                radius (float): Radius, in meters
            Returns:
                :obj:`list` of (str, ?, ?)
            """
            if cur:
                return db.query_locations(cur, point.lat, point.lon, radius)
            else:
                return []

        track.infer_location(
            get_locations,
            max_distance=c_loc['max_distance'],
            google_key=c_loc['google_key'],
            limit=c_loc['limit']
        )
        track.infer_transportation_mode(
            self.clf,
            config['transportation']['min_time']
        )

        db.dispose(conn, cur)

        return track

    def db_connect(self):
        """ Creates a connection with the database

        Use `db.dispose` to commit and close cursor and connection

        Returns:
            (psycopg2.connection, psycopg2.cursor): Both are None if the connection is invalid
        """
        dbc = self.config['db']
        conn = db.connect_db(dbc['host'], dbc['name'], dbc['user'], dbc['port'], dbc['pass'])
        if conn:
            return conn, conn.cursor()
        else:
            return None, None

    def annotate_to_next(self, track, life):
        """ Stores the track and dequeues another track to be
        processed.

        Moves the current GPX file from the input path to the
        backup path, creates a LIFE file in the life path
        and creates a trip entry in the database. Finally the
        trip is exported as a GPX file to the output path.

        Args:
            track (:obj:tracktotrip.Track`)
            changes (:obj:`list` of :obj:`dict`): Details of, user made, changes
        """

        # Backup
        if self.config['backup_path']:
            for gpx in self.queue[self.current_day]:
                from_path = gpx['path']
                to_path = join(expanduser(self.config['backup_path']), gpx['name'])
                rename(from_path, to_path)

        # Export trip to GPX
        save_to_file(join(expanduser(self.config['output_path']), track.name), track.to_gpx())

        if not self.is_bulk_processing:
            learn_transportation_mode(track, self.clf)

        # To LIFE
        if self.config['life_path']:
            save_to_file(join(expanduser(self.config['life_path']), track.name), life)
            if self.config['life_all']:
                life_all_file = expanduser(self.config['life_all'])
            else:
                life_all_file = join(expanduser(self.config['life_path']), 'all.life')
            save_to_file(life_all_file, "\n\n%s" % life, mode='a+')

        conn, cur = self.db_connect()

        if conn and cur:

            db.load_from_life(
                cur,
                life,
                self.config['location']['max_distance'],
                self.config['location']['min_samples']
            )

            def insert_can_trip(can_trip, mother_trip_id):
                """ Insert a cannonical trip into the database

                See `db.insert_canonical_trip`

                Args:
                    can_trip (:obj:`tracktotrip.Segment`): Canonical trip
                    mother_trip_id (int): Id of the trip that originated the canonical
                        representation
                Returns:
                    int: Canonical trip id
                """
                return db.insert_canonical_trip(cur, can_trip, mother_trip_id)

            def update_can_trip(can_id, trip, mother_trip_id):
                """ Updates a cannonical trip on the database

                See `db.update_canonical_trip`

                Args:
                    can_id (int): Canonical trip id
                    trip (:obj:`tracktotrip.Segment`): Canonical trip
                    mother_trip_id (int): Id of the trip that originated the canonical
                        representation
                """
                db.update_canonical_trip(cur, can_id, trip, mother_trip_id)

            trips_ids = []
            for trip in track.segments:
                # To database
                trip_id = db.insert_segment(
                    cur,
                    trip,
                    self.config['location']['max_distance'],
                    self.config['location']['min_samples']
                )
                trips_ids.append(trip_id)

                # Build/learn canonical trip
                canonical_trips = db.match_canonical_trip(cur, trip)

                learn_trip(
                    trip,
                    trip_id,
                    canonical_trips,
                    insert_can_trip,
                    update_can_trip,
                    self.config['simplification']['eps']
                )

            # db.insertStays(cur, trip, trips_ids, life)
            db.dispose(conn, cur)

        self.next_day()
        self.current_step = Step.preview
        return self.current_track()

    def current_track(self):
        """ Gets the current trip/track

        It includes all trips/tracks of the day

        Returns:
            :obj:`tracktotrip.Track`
        """
        return self.history[-1]

    def current_state(self):
        """ Gets the current processing/server state

        Returns:
            :obj:`dict`
        """
        return {
            'step': self.current_step,
            'queue': list(self.queue.items()),
            'track': self.current_track().to_json(),
            'life': self.current_track().to_life() if self.current_step is Step.annotate else '',
            'currentDay': self.current_day
        }

    def complete_trip(self, from_point, to_point):
        """ Generates possible ways to complete a set of trips

        Possible completions are only generated between start and end of each pair of
            trips (ordered by the starting time)

        Args:
            data (:obj:`dict`): Requires keys 'from' and 'to', which should countain
                point representations with 'lat' and 'lon'.
            from_point (:obj:`tracktotrip.Point`): with keys lat and lon
            to_point (:obj:`tracktotrip.Point`): with keys lat and lon
        Returns:
            :obj:`tracktotrip.Track`
        """
        b_box = (
            min(from_point.lat, to_point.lat),
            min(from_point.lon, to_point.lon),
            max(from_point.lat, to_point.lat),
            max(from_point.lon, to_point.lon)
        )

        conn, cur = self.db_connect()
        if conn and cur:
            # get matching canonical trips, based on bounding box
            canonical_trips = db.match_canonical_trip_bounds(cur, b_box)
            db.dispose(conn, cur)

        return complete_trip(canonical_trips, from_point, to_point)

    def load_life(self, content):
        """ Adds LIFE content to the database

        See `db.load_from_life`

        Args:
            content (str): LIFE formated string
        """
        conn, cur = self.db_connect()

        if conn and cur:
            db.load_from_life(
                cur,
                content,
                self.config['location']['max_distance'],
                self.config['location']['min_samples']
            )

        db.dispose(conn, cur)

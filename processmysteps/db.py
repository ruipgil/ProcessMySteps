"""
Database related functions
"""
import datetime
import ppygis
import psycopg2
from psycopg2.extensions import AsIs, adapt, register_adapter
from tracktotrip import Segment, Point
from tracktotrip.location import update_location_centroid
from .life import Life

def adapt_point(point):
    """ Adapts a `tracktotrip.Point` to use with `psycopg` methods

    Params:
        points (:obj:`tracktotrip.Point`)
    """
    point = ppygis.Point(point.lon, point.lat, 0, srid=4326)
    return AsIs(adapt(point.write_ewkb()).getquoted())

def to_point(gis_point, time=None):
    """ Creates from raw ppygis representation

    Args:
        gis_point
        timestamp (:obj:`datatime.datetime`, optional): timestamp to use
            Defaults to none (point will have empty timestamp)
    Returns:
        :obj:`tracktotrip.Point`
    """
    gis_point = ppygis.Geometry.read_ewkb(gis_point)
    return Point(gis_point.y, gis_point.x, time)

def to_segment(gis_points, timestamps=None):
    """ Creates from raw ppygis representation

    Args:
        gis_points
        timestamps (:obj:`list` of :obj:`datatime.datetime`, optional): timestamps to use
            Defaults to none (all points will have empty timestamps)
    Returns:
        :obj:`tracktotrip.Segment`
    """
    gis_points = ppygis.Geometry.read_ewkb(gis_points).points
    result = []
    for i, point in enumerate(gis_points):
        tmstmp = timestamps[i] if timestamps is not None else None
        result.append(Point(point.y, point.x, tmstmp))
    return Segment(result)

def adapt_segment(segment):
    """ Adapts a `tracktotrip.Segment` to use with `psycopg` methods

    Args:
        segment (:obj:`tracktotrip.Segment`)
    """
    points = [ppygis.Point(p.lon, p.lat, 0, srid=4326) for p in segment.points]
    return AsIs(adapt(ppygis.LineString(points).write_ewkb()).getquoted())


register_adapter(Point, adapt_point)
register_adapter(Segment, adapt_segment)

def span_date_to_datetime(date, minutes):
    """ Converts date string and minutes to datetime

    Args:
        date (str): Date in the `%Y_%m_%d` format
        minutes (int): Minutes since midnight
    Returns:
        :obj:`datetime.datetime`
    """
    date_format = "%Y_%m_%d %H%M"
    str_date = "%s %02d%02d" % (date, minutes/60, minutes%60)
    return datetime.datetime.strptime(str_date, date_format)

def get_day_from_life(life, track):
    track_time = track.segments[0].points[0].time
    track_day = "%d_%d_%d" % (track_time.year, track_time.month, track_time.day)
    for day in life.days:
        if day == track_day:
            return day
    return None

def life_date(point):
    date = point.time.date()
    return "%d_%02d_%02d" % (date.year, date.month, date.day)

def life_time(point):
    time = point.time.time()
    return "%02d%02d" % (time.hour, time.minute)

def load_from_segments_annotated(cur, track, life_content, max_distance, min_samples):
    """ Uses a LIFE formated string to populate the database

    Args:
        cur (:obj:`psycopg2.cursor`)
        track (:obj:`tracktotrip.Track`)
        content_content (str): LIFE formatted string
        max_distance (float): Max location distance. See
            `tracktotrip.location.update_location_centroid`
        min_samples (float): Minimum samples requires for location.  See
            `tracktotrip.location.update_location_centroid`
    """
    life = Life()
    life.from_string(life_content.encode('utf8').split('\n'))

    def in_loc(points, i):
        point = points[i]
        print('in_loc', i, point.lat, point.lon)
        location = life.where_when(life_date(point), life_time(point))
        print('location', location)
        if location is not None:
            if isinstance(location, basestring):
                insert_location(cur, location, point, max_distance, min_samples)
            else:
                for loc in location:
                    insert_location(cur, loc, point, max_distance, min_samples)

    for segment in track.segments:
        in_loc(segment.points, 0)
        in_loc(segment.points, -1)
        # find trip
        insert_segment(cur, segment, max_distance, min_samples)

    # Insert stays
    for day in life.days:
        date = day.date
        for span in day.spans:
            start = span_date_to_datetime(date, span.start)
            end = span_date_to_datetime(date, span.end)

            if isinstance(span.place, str):
                insert_stay(cur, span.place, start, end)

    # Insert canonical places
    for place, (lat, lon) in life.locations.items():
        insert_location(cur, place, Point(lat, lon, None), max_distance, min_samples)


def load_from_life(cur, content, max_distance, min_samples):
    """ Uses a LIFE formated string to populate the database

    Args:
        cur (:obj:`psycopg2.cursor`)
        content (str): LIFE formatted string
        max_distance (float): Max location distance. See
            `tracktotrip.location.update_location_centroid`
        min_samples (float): Minimum samples requires for location.  See
            `tracktotrip.location.update_location_centroid`
    """
    life = Life()
    life.from_string(content.encode('utf8').split('\n'))

    # Insert canonical places
    for place, (lat, lon) in life.locations.items():
        insert_location(cur, place, Point(lat, lon, None), max_distance, min_samples)

    # Insert stays
    for day in life.days:
        date = day.date
        for span in day.spans:
            start = span_date_to_datetime(date, span.start)
            end = span_date_to_datetime(date, span.end)

            if isinstance(span.place, str):
                insert_stay(cur, span.place, start, end)


def connect_db(host, name, user, port, password):
    """ Connects to database

    Args:
        host (str)
        name (str)
        user (str)
        port (str)
        password (str)
    Returns:
        :obj:`psycopg2.connection` or None
    """
    try:
        if host != None and name != None and user != None and password != None:
            return psycopg2.connect(
                host=host,
                database=name,
                user=user,
                password=password,
                port=port
            )
    except psycopg2.Error:
        pass
    return None

def dispose(conn, cur):
    """ Disposes a connection

    Args:
        conn (:obj:`psycopg2.connection`): Connection
        cur (:obj:`psycopg2.cursor`): Cursor
    """
    if conn:
        conn.commit()
        if cur:
            cur.close()
        conn.close()
    elif cur:
        cur.close()


def gis_bounds(bound):
    """ Converts bounds to its representation
    """
    points = [
        ppygis.Point(bound[0], bound[1], 0, srid=4336),
        ppygis.Point(bound[0], bound[3], 0, srid=4336),
        ppygis.Point(bound[2], bound[1], 0, srid=4336),
        ppygis.Point(bound[2], bound[3], 0, srid=4336)
    ]
    return ppygis.Polygon([ppygis.LineString(points)]).write_ewkb()

def insert_location(cur, label, point, max_distance, min_samples):
    """ Inserts a location into the database

    Args:
        cur (:obj:`psycopg2.cursor`)
        label (str): Location's name
        point (:obj:`Point`): Position marked with current label
        max_distance (float): Max location distance. See
            `tracktotrip.location.update_location_centroid`
        min_samples (float): Minimum samples requires for location.  See
            `tracktotrip.location.update_location_centroid`
    """

    label = unicode(label, 'utf-8')
    print 'Inserting location %s, %f, %f' % (label, point.lat, point.lon)

    cur.execute("""
            SELECT location_id, label, centroid, point_cluster
            FROM locations
            WHERE label=%s
            ORDER BY ST_Distance(centroid, %s)
            """, (label, point))
    if cur.rowcount > 0:
        # Updates current location set of points and centroid
        location_id, _, centroid, point_cluster = cur.fetchone()
        centroid = to_point(centroid)
        point_cluster = to_segment(point_cluster).points

        # print 'Previous point %s, cluster %s' % (point, [p.to_json() for p in point_cluster])
        centroid, point_cluster = update_location_centroid(
            point,
            point_cluster,
            max_distance,
            min_samples
        )
        # print 'Then point %s, cluster %s' % (point, [p.to_json() for p in point_cluster])
        # print 'centroid: %s' % centroid.to_json()

        cur.execute("""
                UPDATE locations
                SET centroid=%s, point_cluster=%s
                WHERE location_id=%s
                """, (centroid, Segment(point_cluster), location_id))
    else:
        # print 'New location'
        # Creates new location
        cur.execute("""
                INSERT INTO locations (label, centroid, point_cluster)
                VALUES (%s, %s, %s)
                """, (label, point, Segment([point])))

def insert_transportation_mode(cur, tmode, trip_id, segment):
    """ Inserts transportation mode in the database

    Args:
        cur (:obj:`psycopg2.cursor`)
        tmode (:obj:`dict`): transportation mode, with keys: label, from and to
        trip_id (int): Id of the trip that generated the current tranportation mode
        segment (:obj:`tracktotrip.Segment`): Segment that generated the current transportation mode
    """
    label = tmode['label']
    from_index = tmode['from']
    to_index = tmode['to']

    cur.execute("""
            INSERT INTO trips_transportation_modes(trip_id, label, start_date, end_date, start_index, end_index, bounds)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                trip_id,
                label,
                segment.points[from_index].time,
                segment.points[to_index].time,
                from_index,
                to_index,
                gis_bounds(segment.bounds(from_index, to_index))
            ))

def insert_stay(cur, label, start_date, end_date):
    """ Inserts stay in the database

    Args:
        cur (:obj:`psycopg2.cursor`)
        label (str): Location
        start_date (:obj:`datetime.datetime`)
        end_date (:obj:`datetime.datetime`)
    """

    cur.execute("""
        INSERT INTO stays(location_label, start_date, end_date)
        VALUES (%s, %s, %s)
        """, (label, start_date, end_date))

def insert_segment(cur, segment, max_distance, min_samples):
    """ Inserts segment in the database

    Args:
        cur (:obj:`psycopg2.cursor`)
        segment (:obj:`tracktotrip.Segment`): Segment to insert
        max_distance (float): Max location distance. See
            `tracktotrip.location.update_location_centroid`
        min_samples (float): Minimum samples requires for location.  See
            `tracktotrip.location.update_location_centroid`
    Returns:
        int: Segment id
    """
    # insert_location(cur, segment.location_from.label, segment.points[0], max_distance, min_samples)
    # insert_location(cur, segment.location_to.label, segment.points[-1], max_distance, min_samples)

    # def toTsmp(d):
    #     return psycopg2.Timestamp(d.year, d.month, d.day, d.hour, d.minute, d.second)

    tstamps = [p.time for p in segment.points]

    cur.execute("""
            INSERT INTO trips (start_date, end_date, bounds, points, timestamps)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING trip_id
            """, (
                segment.points[0].time,
                segment.points[-1].time,
                gis_bounds(segment.bounds()),
                segment,
                tstamps
            ))
    trip_id = cur.fetchone()
    trip_id = trip_id[0]

    for tmode in segment.transportation_modes:
        insert_transportation_mode(cur, tmode, trip_id, segment)

    return trip_id

def match_canonical_trip(cur, trip):
    """ Queries database for canonical trips with bounding boxes that intersect the bounding
        box of the given trip

    Args:
        cur (:obj:`psycopg2.cursor`)
        trip (:obj:`tracktotrip.Segment`): Trip to match
    """
    cur.execute("""
        SELECT canonical_id, points FROM canonical_trips WHERE bounds && ST_MakeEnvelope(%s, %s, %s, %s, 4326)
        """ % trip.bounds())
    results = cur.fetchall()

    can_trips = []
    for (canonical_id, points) in results:
        segment = to_segment(points)
        can_trips.append((canonical_id, segment))

    return can_trips

def match_canonical_trip_bounds(cur, bounds):
    """ Queries database for canonical trips with bounding boxes that intersect the bounding
        box of the given trip

    Args:
        cur (:obj:`psycopg2.cursor`)
        trip (:obj:`tracktotrip.Segment`): Trip to match
    Returns:
        :obj:`list` of (int, :obj:`tracktotrip.Segment`, int): List of tuples with the id of
            the canonical trip, the segment representation and the number of times it appears
    """
    cur.execute("""
        SELECT can.canonical_id, can.points, COUNT(rels.trip)
        FROM canonical_trips AS can
            INNER JOIN canonical_trips_relations AS rels
                ON can.canonical_id = rels.canonical_trip
        WHERE bounds && ST_MakeEnvelope(%s, %s, %s, %s, 4326)
        GROUP BY can.canonical_id
        """ % bounds)
    results = cur.fetchall()

    can_trips = []
    for (canonical_id, points, count) in results:
        segment = to_segment(points)
        can_trips.append((canonical_id, segment, count))

    return can_trips

def insert_canonical_trip(cur, can_trip, mother_trip_id):
    """ Inserts a new canonical trip into the database

    It also creates a relation between the trip that originated
    the canonical representation and the representation

    Args:
        cur (:obj:`psycopg2.cursor`)
        can_trip (:obj:`tracktotrip.Segment`): Canonical trip
        mother_trip_id (int): Id of the trip that originated the canonical representation
    Returns:
        int: Canonical trip id
    """

    cur.execute("""
        INSERT INTO canonical_trips (bounds, points)
        VALUES (%s, %s)
        RETURNING canonical_id
        """, (
            gis_bounds(can_trip.bounds()),
            Segment(can_trip.points)
        ))
    result = cur.fetchone()
    c_trip_id = result[0]

    cur.execute("""
        INSERT INTO canonical_trips_relations (canonical_trip, trip)
        VALUES (%s, %s)
        """, (c_trip_id, mother_trip_id))

    return c_trip_id

def update_canonical_trip(cur, can_id, trip, mother_trip_id):
    """ Updates a canonical trip

    Args:
        cur (:obj:`psycopg2.cursor`)
        can_id (int): canonical trip id to update
        trip (:obj:`tracktotrip.Segment): canonical trip
        mother_trip_id (int): Id of trip that caused the update
    """

    cur.execute("""
        UPDATE canonical_trips
        SET bounds=%s, points=%s
        WHERE canonical_id=%s
        """, (gis_bounds(trip.bounds()), trip, can_id))

    cur.execute("""
        INSERT INTO canonical_trips_relations (canonical_trip, trip)
        VALUES (%s, %s)
        """, (can_id, mother_trip_id))

def query_locations(cur, lat, lon, radius):
    """ Queries the database for location around a point location

    Args:
        cur (:obj:`psycopg2.cursor`)
        lat (float): Latitude
        lon (float): Longitude
        radius (float): Radius from the given point, in meters
    Returns:
        :obj:`list` of (str, ?, ?): List of tuples with the label, the centroid, and the point
            cluster of the location. Centroid and point cluster need to be converted
    """
    # print '%f, %f, %f' % (lat, lon, radius)
    cur.execute("""
        SELECT label, centroid, point_cluster
        FROM locations
        WHERE ST_DWithin(centroid, %s, %s)
        ORDER BY ST_Distance(centroid, %s)
        """, (Point(lat, lon, None), radius * 4, Point(lat, lon, None)))
    # cur.execute("""
    #     SELECT label, centroid, point_cluster
    #     FROM locations
    #     WHERE ST_SetSRID(ST_Point(-71.1043443253471, 42.3150676015829),4326)::geography
    #     WHERE ST_Distance_Sphere(centroid, ST_GeomFromText('POINT(%s %s)', 4326)) >= %s
    #     """, (lat, lon, radius))
    results = cur.fetchall()
    a = [
        (label, to_point(centroid), to_segment(cluster)) for (label, centroid, cluster) in results
    ]
    print a
    return a

def get_canonical_trips(cur):
    """ Gets canonical trips

    Args:
        cur (:obj:`psycopg2.cursor`)
    Returns:
        :obj:`list` of :obj:`dict`:
            [{ 'id': 1, 'points': <tracktotrip.Segment> }, ...]
    """
    cur.execute("SELECT canonical_id, points FROM canonical_trips")
    trips = cur.fetchall()
    return [{'id': t[0], 'points': to_segment(t[1])} for t in trips]

def get_canonical_locations(cur):
    """ Gets canonical trips

    Args:
        cur (:obj:`psycopg2.cursor`)
    Returns:
        :obj:`list` of :obj:`dict`:
            [{ 'id': 1, 'points': <tracktotrip.Segment> }, ...]
    """
    cur.execute("SELECT label, point_cluster FROM locations")
    locations = cur.fetchall()
    return [{'label': t[0], 'points': to_segment(t[1])} for t in locations]

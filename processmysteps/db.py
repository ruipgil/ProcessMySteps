import datetime
import psycopg2
import ppygis
from tracktotrip import Segment, Point
from tracktotrip.location import update_location_centroid
from .life import Life

def load_from_life(cur, content, max_distance, min_samples):
    l = Life()
    l.from_string(content.encode('utf8').split('\n'))
    # Insert places
    for place, (lat, lon) in l.locations.items():
        insertLocation(cur, place, Point(lat, lon, None), max_distance, min_samples)

    # Insert stays
    for day in l.days:
        date = day.date
        for span in day.spans:
            start = datetime.datetime.strptime("%s %02d%02d" % (date, span.start/60, span.start%60), "%Y_%m_%d %H%M")
            end = datetime.datetime.strptime("%s %02d%02d" % (date, span.end/60, span.end%60), "%Y_%m_%d %H%M")

            if type(span.place) is str:
                insertStay(cur, span.place, start, end)


def connectDB(host, name, user, port, password):
    try:
        if host != None and name != None and user != None and password != None:
            return psycopg2.connect("host=%s dbname=%s user=%s password=%s port=%s" % (host, name, user, password, port))
    except:
        return None
    return None

def checkConn(host, name, user, port, password):
    if connectDB(host, name, user, port, password) is not None:
        print("Connected with DB")
    else:
        print("Could not connect with DB")
        print("host=%s dbname=%s user=%s password=%s" % (host, name, user, password))

def dbPoint(point):
    return ppygis.Point(point.lat, point.lon, 0, srid=4326).write_ewkb()

def pointsFromDb(gis_points, timestamps=None):
    gis_points = ppygis.Geometry.read_ewkb(gis_points).points
    result = []
    for i, point in enumerate(gis_points):
        result.append(Point(point.x, point.y, timestamps[i] if timestamps is not None else None))
    return result

def dbPoints(points):
    return ppygis.LineString(map(lambda p: ppygis.Point(p.lat, p.lon, 0, srid=4326), points), 4326).write_ewkb()

def dbBounds(bound):
    return ppygis.Polygon([
        ppygis.LineString(
            [   ppygis.Point(bound[0], bound[1], 0, srid=4336),
                ppygis.Point(bound[0], bound[3], 0, srid=4336),
                ppygis.Point(bound[2], bound[1], 0, srid=4336),
                ppygis.Point(bound[2], bound[3], 0, srid=4336)])]).write_ewkb()

def insertLocation(cur, label, point, max_distance, min_samples):
    cur.execute("""
            SELECT label, centroid, point_cluster
            FROM locations
            WHERE label=%s
            """, (label, ))
    if cur.rowcount > 0:
        # Updates current location set of points and centroid
        _, centroid, point_cluster = cur.fetchone()
        centroid = ppygis.Geometry.read_ewkb(centroid)
        # point_cluster = ppygis.Geometry.read_ewkb(point_cluster)
        point_cluster = pointsFromDb(point_cluster)

        centroid, newCluster = update_location_centroid(point, point_cluster, max_distance, min_samples)

        cur.execute("""
                UPDATE locations
                SET centroid=%s, point_cluster=%s
                WHERE label=%s
                """, (dbPoint(centroid), dbPoints(newCluster), label))
    else:
        # Creates new location
        cur.execute("""
                INSERT INTO locations (label, centroid, point_cluster)
                VALUES (%s, %s, %s)
                """, (label, dbPoint(point), dbPoints([point])))

def insertTransportationMode(cur, tmode, trip_id, segment):
    label = tmode['label']
    fro = tmode['from']
    to = tmode['to']
    cur.execute("""
            INSERT INTO trips_transportation_modes(trip_id, label, start_date, end_date, start_index, end_index, bounds)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (   trip_id, label,
                segment.points[fro].time,
                segment.points[to].time,
                fro, to,
                dbBounds(segment.bounds(fro, to))))

def insertStay(cur, label, start_date, end_date):
    cur.execute("""
        INSERT INTO stays(location_label, start_date, end_date)
        VALUES (%s, %s, %s)
        """, (label, start_date, end_date))


# def insertStays(cur, trip, ids, life):
#     def insert(trip_id, location, start_date, end_date):
#         cur.execute("""
#             INSERT INTO stays(trip_id, location_label, start_date, end_date)
#             VALUES (%s, %s, %s, %s)
#             """, (trip_id, location, start_date, end_date))
#
#     for i, segment in enumerate(trip.segments):
#         trip_id = ids[i]
#         if i == 0:
#             # Start of the day
#             end_date = segment.getStartTime()
#             start_date = datetime.datetime(end_date.year, end_date.month, end_date.day)
#             location = segment.location_from
#         else:
#             start_date = trip.segments[i - 1].getEndTime()
#             end_date = segment.getEndTime()
#             location = segment.location_from
#
#         insert(trip_id, location, start_date, end_date)
#
#         if i == len(trip.segments) - 1:
#             location = segment.location_to
#             start_date = segment.getEndTime()
#             end_date = datetime.datetime(start_date.year, start_date.month, start_date.day, 0, 0, 0, 0)
#             insert(trip_id, location, start_date, end_date)

def insertSegment(cur, segment, loc_max_distance, min_samples):
    insertLocation(cur, segment.location_from.label, segment.points[0], loc_max_distance, min_samples)
    insertLocation(cur, segment.location_to.label, segment.points[-1], loc_max_distance, min_samples)

    def toTsmp(d):
        return psycopg2.Timestamp(d.year, d.month, d.day, d.hour, d.minute, d.second)

    tstamps = map(lambda p: p.time, segment.points)

    cur.execute("""
            INSERT INTO trips (start_location, end_location, start_date, end_date, bounds, points, timestamps)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING trip_id
            """,
            (   segment.location_from.label,
                segment.location_to.label,
                segment.points[0].time,
                segment.points[-1].time,
                dbBounds(segment.bounds()),
                dbPoints(segment.points),
                tstamps
                ))
    trip_id = cur.fetchone()
    trip_id = trip_id[0]

    for tmode in segment.transportation_modes:
        insertTransportationMode(cur, tmode, trip_id, segment)

    return trip_id

def matchCanonicalTrip(cur, trip):
    """Tries to match canonical trips, with
    a bounding box

    Args:
        trip: tracktotrip.Track
    Returns:
        Array of matched tracktotrip.Trip
    """
    cur.execute("""
        SELECT canonical_id, points FROM canonical_trips WHERE bounds && ST_MakeEnvelope(%s, %s, %s, %s, 4326)
        """ % trip.bounds())
    results = cur.fetchall()

    can_trips = []
    for (canonical_id, points) in results:
        can_trips.append((canonical_id, Segment(points=pointsFromDb(points))))

    return can_trips

def matchCanonicalTripBounds(cur, bounds):
    """Tries to match canonical trips, with
    a bounding box

    Args:
        trip: tracktotrip.Track
    Returns:
        Array of matched tracktotrip.Trip
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
        can_trips.append((canonical_id, Segment(points=pointsFromDb(points)), count))

    return can_trips

def insertCanonicalTrip(cur, can_trip, mother_trip_id):
    """Inserts a new canonical trip into the database

    It also creates a relation between the trip that originated
    the canonical representation and the representation

    Args:
        can_trip: tracktotrip.Segment, canonical trip
        mother_trip_id: NUmber, id of the trip that originated
            the canonical representation
    Returns:
        Number, canonical trip id
    """

    cur.execute("""
        INSERT INTO canonical_trips (start_location, end_location, bounds, points)
        VALUES (%s, %s, %s, %s)
        RETURNING canonical_id
        """, (can_trip.location_from.label, can_trip.location_to.label, dbBounds(can_trip.bounds()), dbPoints(can_trip.points)))
    result = cur.fetchone()
    c_trip_id = result[0]

    cur.execute("""
        INSERT INTO canonical_trips_relations (canonical_trip, trip)
        VALUES (%s, %s)
        """, (c_trip_id, mother_trip_id))

    return c_trip_id

def updateCanonicalTrip(cur, can_id, trip, mother_trip_id):
    """Updates a canonical trip

    Args:
        can_id: Number, canonical trip id to update
        trip: tracktotrip.Segment, canonical trip
        mother_trip_id: Number, id of trip that caused
            the update
    """

    cur.execute("""
        UPDATE canonical_trips
        SET bounds=%s, points=%s
        WHERE canonical_id=%s
        """, (dbBounds(trip.bounds()), dbPoints(trip.points), can_id))

    cur.execute("""
        INSERT INTO canonical_trips_relations (canonical_trip, trip)
        VALUES (%s, %s)
        """, (can_id, mother_trip_id))

    return

def queryLocations(cur, lat, lon, dx):
    cur.execute("""
        SELECT label, centroid, point_cluster
        FROM locations
        WHERE ST_DWithin(centroid, %s, %s)
        """, (dbPoint(Point(lat, lon, None)), dx))
    return cur.fetchall()

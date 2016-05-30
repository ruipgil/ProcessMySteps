from os import getenv
import psycopg2
import ppygis
import tracktotrip as tt

def connectDB():
    host = getenv('DB_HOST')
    name = getenv('DB_NAME')
    user = getenv('DB_USER')
    port = getenv('DB_PORT')
    password = getenv('DB_PASS')
    try:
        if host != None and name != None and user != None and password != None:
            return psycopg2.connect("host=%s dbname=%s user=%s password=%s port=%s" % (host, name, user, password, port))
    except:
        return None
    return None

def checkConn():
    if connectDB() is not None:
        print("Connected with DB")
    else:
        print("Could not connect with DB")
        host = getenv('DB_HOST')
        name = getenv('DB_NAME')
        user = getenv('DB_USER')
        password = getenv('DB_PASS')
        print("host=%s dbname=%s user=%s password=%s" % (host, name, user, password))

def dbPoint(point):
    return ppygis.Point(point.lat, point.lon, 0, srid=4326).write_ewkb()

def dbPoints(points):
    return ppygis.LineString(map(lambda p: ppygis.Point(p.lat, p.lon, 0, srid=4326), points), 4326).write_ewkb()

def dbBounds(bound):
    return ppygis.LineString(
            [   ppygis.Point(bound[0], bound[1], 0, srid=4336),
                ppygis.Point(bound[2], bound[3], 0, srid=4336)])

def insertLocation(cur, label, point):
    cur.execute("""
            SELECT label, centroid, point_cluster
            FROM locations
            WHERE locations=%s
            """, (label, ))
    if cur.rowcount > 0:
        # Updates current location set of points and centroid
        _, centroid, point_cluster = cur.fetchone()
        # TODO
        # centroid = computeCentroidWith(point, point_cluster)
        point_cluster.append(point)
        cur.execute("""
                UPDATE locations
                SET centroid=%s, point_cluster=%s
                WHERE label=%s
                """, (centroid, point_cluster, label))
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
                dbBounds(segment.getBounds(fro, to))))

def insertTrip(segment):
    conn = connectDB()
    if conn == None:
        return

    cur = conn.cursor()
    cur.execute("""
            INSERT INTO trips (start_location, end_location, start_date, end_date, bounds, points, timestamps)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING trip_id
            """,
            (   segment.fromLocation,
                segment.toLocation,
                segment.getStartTime(),
                segment.getEndTime(),
                segment.getBounds(),
                dbPoints(segment.points),
                map(lambda p: p.time, segment.points)))
    trip_id = cur.fetchone()

    for tmode in segment.transportationModes:
        insertTransportationMode(cur, tmode, trip_id, segment)

    insertLocation(cur, segment.fromLocation, segment.pointAt(0))
    insertLocation(cur, segment.toLocation, segment.pointAt(-1))

    # TODO
    # cur.execute("""
            # INSERT INTO stays(trip_id, location_label, start_date, end_date)
            # VALUES (%s, %s, %s, %s)
            # """, (trip_id, a))

    cur.commit()
    cur.close()
    conn.close()

def matchCanonicalTrip(trip):
    """Tries to match canonical trips, with
    a bounding box

    Args:
        trip: tracktotrip.Track
    Returns:
        Array of matched tracktotrip.Trip
    """
    conn = connectDB()
    if conn == None:
        return []

    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM canonical_trips WHERE canonical_trips.geom && ST_MakeEnvelope(%s, %s, %s, %s)
        """ % trip)

    can_trips = []
    for row in cur:
        can_trips = (row['id'], row['points'])

    cur.commit()
    cur.close()
    conn.close()
    return can_trips


import unittest
import db
import ppygis
from datetime import datetime, timedelta
from tracktotrip import Segment, Track, Point, Location

schema = open('./schema.sql', 'r').read()
drop = open('./drop.sql', 'r').read()

class TestDB(unittest.TestCase):
    def setUp(self):
        # A and B are similar
        Aps = [[0.5, 0.5], [1, 1.5], [2, 2.5], [3.5, 3.5], [5.2, 4.5], [7.5, 6.5], [7.9, 8]]
        Bps = [[0.6, 0.5], [1.05, 1.45], [2.1, 2.4], [2.8, 4], [3.5, 5.5], [5, 5.7], [7.8, 5.7], [8.1, 6.5], [8.1, 8]]
        # C intersects B sligthly
        Cps = [[7.8, 6.1], [8.5, 5.5], [9.1, 4.5], [9.5, 3.3], [9.8, 1.7]]
        # D's bounding box doesn't intersect
        Dps = [[11, 1], [11, 2], [11, 3], [10.5, 4.5], [10, 5], [10.5, 5.5], [11, 6]]

        time = datetime.now()
        dt = timedelta(1000)

        def pt_arr_to_track(pts):
            seg = Segment(map(lambda p: Point(None, p[0], p[1], time + dt), pts))
            return Track(name="TripA", segments=[seg])

        self.tripA = pt_arr_to_track(Aps)
        self.tripA.toTrip(name="A")

        self.tripB = pt_arr_to_track(Bps)
        self.tripB.toTrip(name="B")

        self.tripC = pt_arr_to_track(Cps)
        self.tripC.toTrip(name="C")

        self.tripD = pt_arr_to_track(Dps)
        self.tripD.toTrip(name="D")

        conn = db.connectDB()
        cur = conn.cursor()

        cur.execute(drop)
        cur.execute(schema)
        conn.commit()

        self.conn = conn
        self.cur = cur

    def tearDown(self):
        self.cur.execute(drop)
        self.conn.commit()
        self.cur.close()
        self.conn.close()

    def test_insert_new_location(self):
        self.cur.execute("SELECT COUNT(label) FROM locations")
        result = self.cur.fetchone()
        self.assertEqual(result[0], 0)

        p = self.tripA.segments[0].points[0]
        db.insertLocation(self.cur, 'PlaceA', p)

        self.cur.execute("SELECT COUNT(label) FROM locations")
        result = self.cur.fetchone()
        self.assertEqual(result[0], 1)

        self.cur.execute("SELECT label, centroid, point_cluster FROM locations")
        label, centroid, point_cluster = self.cur.fetchone()
        centroid = ppygis.Geometry.read_ewkb(centroid)
        point_cluster = ppygis.Geometry.read_ewkb(point_cluster)

        self.assertEqual(label, "PlaceA")

        self.assertEqual(centroid.x, p.lat)
        self.assertEqual(centroid.y, p.lon)

        self.assertEqual(len(point_cluster.points), 1)
        self.assertEqual(point_cluster.points[0].x, p.lat)
        self.assertEqual(point_cluster.points[0].y, p.lon)

        self.conn.commit()

    def test_insert_existing_location(self):
        self.cur.execute("SELECT COUNT(label) FROM locations")
        result = self.cur.fetchone()
        self.assertEqual(result[0], 0)

        p1 = self.tripA.segments[0].points[0]
        p2 = self.tripA.segments[0].points[1]
        db.insertLocation(self.cur, 'PlaceA', p1)
        db.insertLocation(self.cur, 'PlaceA', p2)

        self.cur.execute("SELECT COUNT(label) FROM locations")
        result = self.cur.fetchone()
        self.assertEqual(result[0], 1)

        self.cur.execute("SELECT label, centroid, point_cluster FROM locations")
        label, centroid, point_cluster = self.cur.fetchone()
        centroid = ppygis.Geometry.read_ewkb(centroid)
        point_cluster = ppygis.Geometry.read_ewkb(point_cluster)

        self.assertEqual(label, "PlaceA")

        self.assertEqual(centroid.x, p1.lat)
        self.assertEqual(centroid.y, p1.lon)

        self.assertEqual(len(point_cluster.points), 2)
        self.assertEqual(point_cluster.points[0].x, p1.lat)
        self.assertEqual(point_cluster.points[0].y, p1.lon)

        self.assertEqual(point_cluster.points[1].x, p2.lat)
        self.assertEqual(point_cluster.points[1].y, p2.lon)

        self.conn.commit()

    def test_insert_transportation_mode(self):
        db.insertLocation(self.cur, "Home", self.tripA.segments[0].points[0])
        db.insertLocation(self.cur, "Work", self.tripA.segments[0].points[-1])

        self.cur.execute("""
                INSERT INTO trips (start_location, end_location, start_date, end_date, bounds, points, timestamps)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING trip_id
                """,
                (   "Home",
                    "Work",
                    self.tripA.segments[0].points[0].time,
                    self.tripA.segments[0].points[-1].time,
                    db.dbBounds(self.tripA.getBounds()),
                    db.dbPoints(self.tripA.segments[0].points),
                    []
                    ))
        trip_id = self.cur.fetchone()
        trip_id = trip_id[0]

        self.cur.execute("SELECT COUNT(mode_id) FROM trips_transportation_modes")
        result = self.cur.fetchone()
        self.assertEqual(result[0], 0)

        tmode = {
                'from': 2,
                'to': 4,
                'label': "Walk"
                }
        self.conn.commit()
        db.insertTransportationMode(self.cur, tmode, trip_id, self.tripA.segments[0])

        self.cur.execute("SELECT COUNT(mode_id) FROM trips_transportation_modes")
        result = self.cur.fetchone()
        self.assertEqual(result[0], 1)

        self.cur.execute("SELECT mode_id, trip_id, label, start_date, end_date, start_index, end_index, bounds FROM trips_transportation_modes")
        mode_id, trip_id, label, start_date, end_date, start_index, end_index, bounds = self.cur.fetchone()
        self.assertEqual(mode_id, trip_id)
        self.assertEqual(label, tmode['label'])
        self.assertEqual(start_index, tmode['from'])
        self.assertEqual(end_index, tmode['to'])
        self.assertEqual(start_date, self.tripA.segments[0].points[tmode['from']].time)
        self.assertEqual(end_date, self.tripA.segments[0].points[tmode['to']].time)
        # TODO assert bounds

        self.conn.commit()

    def assert_bounds(self, postgis_bounds, tt_bounds):
        postgis_bounds = ppygis.Geometry.read_ewkb(postgis_bounds)
        postgis_bounds = postgis_bounds.rings[0].points
        self.assertEquals(postgis_bounds[0].x, tt_bounds[0])
        self.assertEquals(postgis_bounds[0].y, tt_bounds[1])
        self.assertEquals(postgis_bounds[3].x, tt_bounds[2])
        self.assertEquals(postgis_bounds[3].y, tt_bounds[3])

    def assert_points(self, postgis_points, tt_points, timestamps=None):
        postgis_points = ppygis.Geometry.read_ewkb(postgis_points).points
        for i, point in enumerate(postgis_points):
            self.assertEquals(point.x, tt_points[i].lat)
            self.assertEquals(point.y, tt_points[i].lon)
            if timestamps is not None:
                self.assertEquals(timestamps[i], tt_points[i].time)

    def test_insert_segment(self):

        self.tripA.segments[0].location_from = Location.Location("Home", self.tripA.segments[0].points[0])
        self.tripA.segments[0].location_to = Location.Location("Gym", self.tripA.segments[0].points[-1])

        self.tripA.segments[0].transportationModes = [
                {
                    'from': 0,
                    'to': len(self.tripA.segments[0].points) / 2,
                    'label': "Walk" },
                {
                    'from': len(self.tripA.segments[0].points) / 2,
                    'to': len(self.tripA.segments[0].points),
                    'label': "Vehicle" }
                ]

        self.cur.execute("SELECT COUNT(trip_id) FROM trips")
        result = self.cur.fetchone()
        self.assertEqual(result[0], 0)

        self.conn.commit()
        db.insertSegment(self.tripA.segments[0])

        self.cur.execute("SELECT COUNT(trip_id) FROM trips")
        result = self.cur.fetchone()

        self.assertEqual(result[0], 1)

        self.cur.execute("SELECT trip_id, start_location, end_location, start_date, end_date, bounds, points, timestamps FROM trips")

        _, start_location, end_location, start_date, end_date, bounds, points, timestamps = self.cur.fetchone()
        tp = self.tripA.segments[0].points
        self.assertEquals(start_location, "Home")
        self.assertEquals(end_location, "Gym")
        self.assertEquals(start_date, tp[0].time)
        self.assertEquals(end_date, tp[-1].time)
        self.assert_points(points, tp, timestamps=timestamps)
        self.assert_bounds(bounds, self.tripA.getBounds())

        # TODO: assert transp mode insertion & location insertion

        self.conn.commit()

    def test_insert_canonical_trip(self):
        self.tripA.segments[0].location_from = Location.Location("Home", self.tripA.segments[0].points[0])
        self.tripA.segments[0].location_to = Location.Location("Work", self.tripA.segments[0].points[-1])

        db.insertLocation(self.cur, "Home", self.tripA.segments[0].points[0])
        db.insertLocation(self.cur, "Work", self.tripA.segments[0].points[-1])

        self.cur.execute("""
                INSERT INTO trips (start_location, end_location, start_date, end_date, bounds, points, timestamps)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING trip_id
                """,
                (   "Home",
                    "Work",
                    self.tripA.segments[0].points[0].time,
                    self.tripA.segments[0].points[-1].time,
                    db.dbBounds(self.tripA.getBounds()),
                    db.dbPoints(self.tripA.segments[0].points),
                    []
                    ))
        trip_id = self.cur.fetchone()
        trip_id = trip_id[0]

        self.cur.execute("SELECT COUNT(canonical_id) FROM canonical_trips")
        result = self.cur.fetchone()
        self.assertEqual(result[0], 0)

        self.cur.execute("SELECT COUNT(*) FROM canonical_trips_relations")
        result = self.cur.fetchone()
        self.assertEqual(result[0], 0)

        self.conn.commit()
        db.insertCanonicalTrip(self.tripA.segments[0], trip_id)

        self.cur.execute("SELECT COUNT(canonical_id) FROM canonical_trips")
        result = self.cur.fetchone()
        self.assertEqual(result[0], 1)

        self.cur.execute("""
            SELECT canonical_id, start_location, end_location, bounds, points
            FROM canonical_trips
            """)
        canonical_id, start_location, end_location, bounds, points = self.cur.fetchone()
        self.assertEqual(start_location, "Home")
        self.assertEqual(end_location, "Work")
        self.assert_bounds(bounds, self.tripA.segments[0].getBounds())
        self.assert_points(points, self.tripA.segments[0].points)

        self.cur.execute("SELECT canonical_trip, trip FROM canonical_trips_relations")
        r_can_trip, r_trip = self.cur.fetchone()
        self.assertEqual(r_can_trip, canonical_id)
        self.assertEqual(r_trip, trip_id)

        self.conn.commit()

    def test_update_canonical_trip(self):
        self.tripA.segments[0].location_from = Location.Location("Home", self.tripA.segments[0].points[0])
        self.tripA.segments[0].location_to = Location.Location("Work", self.tripA.segments[0].points[-1])
        tripA_id = db.insertSegment(self.tripA.segments[0])

        self.tripB.segments[0].location_from = Location.Location("Home", self.tripB.segments[0].points[0])
        self.tripB.segments[0].location_to = Location.Location("Work", self.tripB.segments[0].points[-1])
        tripB_id = db.insertSegment(self.tripB.segments[0])

        can_id = db.insertCanonicalTrip(self.tripA.segments[0], tripA_id)

        self.conn.commit()
        db.updateCanonicalTrip(can_id, self.tripB.segments[0], tripB_id)

        self.cur.execute("""
            SELECT start_location, end_location, bounds, points
            FROM canonical_trips
            WHERE canonical_id=%s
            """, (can_id, ))
        start_location, end_location, bounds, points = self.cur.fetchone()
        self.assertEqual(start_location, "Home")
        self.assertEqual(end_location, "Work")
        self.assert_bounds(bounds, self.tripB.segments[0].getBounds())
        self.assert_points(points, self.tripB.segments[0].points)

        self.cur.execute("""
            SELECT trip
            FROM canonical_trips_relations
            WHERE canonical_trip=%s
            """, (can_id, ))
        results = self.cur.fetchall()
        results = map(lambda r: r[0], results)
        self.assertEqual(len(results), 2)
        self.assertTrue(tripA_id in results)
        self.assertTrue(tripB_id in results)

    def test_match_canonical_trip(self):
        self.tripA.segments[0].location_from = Location.Location("Home", self.tripA.segments[0].points[0])
        self.tripA.segments[0].location_to = Location.Location("Work", self.tripA.segments[0].points[-1])
        tripA_id = db.insertSegment(self.tripA.segments[0])

        self.tripB.segments[0].location_from = Location.Location("Home", self.tripB.segments[0].points[0])
        self.tripB.segments[0].location_to = Location.Location("Work", self.tripB.segments[0].points[-1])
        tripB_id = db.insertSegment(self.tripB.segments[0])

        db.insertCanonicalTrip(self.tripA.segments[0], tripA_id)

        # Exact match
        results = db.matchCanonicalTrip(self.tripA.segments[0])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][0], tripA_id)

        # Similar match
        results = db.matchCanonicalTrip(self.tripB.segments[0])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][0], tripA_id)

        db.insertCanonicalTrip(self.tripB.segments[0], tripB_id)

        # Match two
        results = db.matchCanonicalTrip(self.tripB.segments[0])
        matched_ids = map(lambda r: r[0], results)
        self.assertEqual(len(results), 2)
        self.assertTrue(tripA_id in matched_ids)
        self.assertTrue(tripB_id in matched_ids)

        # Partial match on B
        results = db.matchCanonicalTrip(self.tripC.segments[0])
        matched_ids = map(lambda r: r[0], results)
        self.assertEqual(len(results), 1)
        self.assertTrue(tripB_id in matched_ids)

        # No match
        results = db.matchCanonicalTrip(self.tripD.segments[0])
        matched_ids = map(lambda r: r[0], results)
        self.assertEqual(len(results), 0)

        results = db


if __name__ == '__main__':
    unittest.main()

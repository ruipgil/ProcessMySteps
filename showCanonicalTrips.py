import db
import matplotlib.pyplot as plt

conn = db.connectDB()
cur = conn.cursor()

cur.execute("""
        SELECT points
        FROM canonical_trips
        """)
result = cur.fetchall()


plt.axis('equal')
def plot(data, more=""):
    plt.plot(map(lambda a: a[0], data), map(lambda a: a[1], data), more)
    # plt.plot(data[0][0], data[0][1], more+'o')
    # plt.plot(data[-1][0], data[-1][1], more+'o')

for (points, ) in result:
    points = db.pointsFromDb(points)
    print(len(points))
    plt.plot(map(lambda p: p.lat, points), map(lambda p: p.lon, points))

plt.show()


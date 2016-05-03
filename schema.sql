CREATE EXTENSION postgis;
SELECT postgis_full_version();

CREATE TYPE _timestamp as TIMESTAMP WITHOUT TIME ZONE
CREATE TYPE _bounds as geography(POLYGON, 4326)
CREATE TYPE _line as geography(POINTLINE, 4326)

CREATE TABLE IF NOT EXISTS trips (
  trip_id SERIAL PRIMARY KEY,

  start_location location_id NULL,
  end_location location_id NULL,

  start_date _timestamp NOT NULL,
  end_date _timestamp NOT NULL

  bounds _bounds NOT NULL,
  points _line NOT NULL,
  -- Length of timestamps must be the same as the lenght of points
  timestamps _timestamp[] NOT NULL
);

CREATE TABLE IF NOT EXISTS trips_transportation_modes (
  mode_id SERIAL PRIMARY KEY,
  trip_id SERIAL REFERENCES trips(trip_id) NOT NULL,

  label TEXT NOT NULL,

  start_date _timestamp NOT NULL,
  end_date _timestamp NOT NULL,

  -- Indexes of Trips(point/timestamp)
  start_index INTEGER NOT NULL,
  end_index INTEGER NOT NULL,
  bounds _bounds NOT NULL
);

CREATE TABLE IF NOT EXISTS locations (
  label TEXT PRIMARY KEY,
  -- Point representative of the location
  centroid GEOGRAPHY(POINTZ, 4326) NOT NULL,
  -- Cluster of points that derived the location
  point_cluster geography(MULTIPOINT, 4326) NOT NULL
);

CREATE TABLE IF NOT EXISTS stays (
  stay_id SERIAL PRIMARY KEY,
  trip_id SERIAL REFERENCES trips(trip_id)
  location_label TEXT REFERENCES location(label),
  start_date TIMESTAMP WITHOUT TIME ZONE NOT NULL,
  end_date TIMESTAMP WITHOUT TIME ZONE NOT NULL
);

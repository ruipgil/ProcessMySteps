# START DB
PG_DOCKER_PORT=5432
docker stop pms-postgis
docker rm pms-postgis
echo "Starting container"
docker run --name pms-postgis -p $PMS_DOCKER_PORT:$PG_DOCKER_PORT -e POSTGRES_USER=pmsteps -e POSTGRES_PASSWORD=pmsteps -d mdillon/postgis

echo "Getting container port"
PMS_DOCKER_PORT=$(docker inspect --format='{{(index (index .NetworkSettings.Ports "'$PG_DOCKER_PORT'/tcp") 0).HostPort}}' pms-postgis)

sleep 20
echo "Initializing schema"
env PGPASSWORD=pmsteps psql -h localhost -p $PMS_DOCKER_PORT -d pmsteps -U pmsteps -w -f schema.sql

echo "Container port"
echo $PMS_DOCKER_PORT

# START SERVER
echo "Starting server"
# env DB_PORT=$PMS_DOCKER_PORT DB_HOST=localhost DB_NAME=pmsteps DB_PASS=pmsteps DB_USER=pmsteps python test_db.py
env DB_PORT=$PMS_DOCKER_PORT DB_HOST=localhost DB_NAME=pmsteps DB_PASS=pmsteps DB_USER=pmsteps python server.py --source ~/tracks/ --backup ./backup --life ./life/ --dest ./dest

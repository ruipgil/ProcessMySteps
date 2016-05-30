# ProcessMySteps
Backend for GatherMySteps

## Running

The server is highly parameterable, use

``` python server.py --help ```

to get all the options.

Database access is not mandatory, however some functionalities may not work.
You can set ``` DB_NAME ```, ```DB_PASS```, ```DB_HOST```, ```DB_PORT``` and ```DB_NAME``` with environment variables. All of those must be set so that ```ProcessMySteps``` can connect with the database.

The ```start.sh``` starts a docker container with a valid database setup, and starts the server connected with it.

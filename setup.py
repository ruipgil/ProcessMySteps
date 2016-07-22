"""
Setup script
"""
from distutils.core import setup

REQS = [
    'tracktotrip',
    'flask',
    'psycopg2',
    'ppygis'
]

setup(
    name='processmysteps',
    packages=['processmysteps'],
    version='0.1',
    description='Track processing manager',
    author='Rui Gil',
    author_email='ruipgil@gmail.com',
    url='https://github.com/ruipgil/processmysteps',
    download_url='https://github.com/ruipgil/processmysteps/archive/master.zip',
    keywords=['track', 'trip', 'GPS', 'GPX', 'server'],
    classifiers=[],
    install_requires=REQS
)

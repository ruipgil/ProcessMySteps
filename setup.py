"""
Setup script
"""
import os
from distutils.core import setup

def read(filename):
    return open(os.path.join(os.path.dirname(__file__), filename)).read()
# REQS = [
#     'tracktotrip',
#     'flask',
#     'psycopg2',
#     'ppygis'
# ]

setup(
    name='processmysteps',
    packages=['processmysteps'],
    version='0.2',
    description='Track processing manager',
    author='Rui Gil',
    author_email='ruipgil@gmail.com',
    url='https://github.com/ruipgil/processmysteps',
    download_url='https://github.com/ruipgil/processmysteps/archive/master.zip',
    keywords=['track', 'trip', 'GPS', 'GPX', 'server'],
    classifiers=[],
    install_requires=read('requirements.txt').split('\n')
)

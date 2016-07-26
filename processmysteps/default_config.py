default_config = {
    'input_path': None,
    'dest_path': None,
    'backup_path': None,
    'dest_path': None,
    'life_all': None,
    'db': {
        'host': None,
        'port': None,
        'name': None,
        'user': None,
        'pass': None
    },
    'preprocess': {
        'max_acc': 30.0
    },
    'smoothing': {
        'use': True,
        'algorithm': 'inverse',
        'noise': 5
    },
    'segmentation': {
        'use': True,
        'epsilon': 0.15,
        'min_time': 80
    },
    'simplification': {
        'dist_threshold': 0.3,
        'eps': 0.15
    },
    'location': {
        'max_distance': 20,
        'min_samples': 2,
        'limit': 5,
        'google_key': ''
    },
    'transportation': {
        'remove_stops': False,
        'min_time': 10,
        'classifier_path': 'classifier.data'# None
    },
    'trip_learning': {
        'epsilon': 0.0,
        'classifier_path': None,
    },
    'trip_name_format': '%Y-%m-%d'
}

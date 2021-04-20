"""The Repository Web Service is designed to interact with the repository via HTTP."""

import json
import os

from flask import Flask

from s3repo.model import S3AsyncModel
from s3repo.controller import S3Controller


def load_cfg():
    """Load and parse the config."""
    # Get path to config from env and check if it exists.
    env_cfg_path = os.getenv('RWS_CFG')
    if env_cfg_path is None or not os.path.isfile(env_cfg_path):
        raise RuntimeError('Configuration file does not exist.')

    # Parse config.
    cfg = {}
    with open(env_cfg_path) as cfg_file:
        cfg = json.load(cfg_file)

    return cfg


def update_cfg_by_env(cfg):
    """Update the config with data from environment variables."""
    # Get some configuration parameters from env.
    env_model_settings = {}
    env_model_settings['region'] = os.getenv('S3_REGION')
    env_model_settings['endpoint_url'] = os.getenv('S3_URL')
    env_model_settings['bucket_name'] = os.getenv('S3_BUCKET')
    env_model_settings['base_path'] = os.getenv('S3_BASE_PATH')
    env_model_settings['access_key_id'] = os.getenv('S3_ACCESS_KEY')
    env_model_settings['secret_access_key'] = os.getenv('S3_SECRET_KEY')

    # Populate the config with data from environment variables.
    for item in env_model_settings.items():
        if item[1]:
            cfg['model'][item[0]] = item[1]


def server_prepare():
    """Prepare server for run."""
    # Get configuration.
    cfg = load_cfg()
    update_cfg_by_env(cfg)

    # Configure S3 backend.
    s3_model = S3AsyncModel(cfg['model'])
    # Include after the `sync_all_repos()` will be implemented.
    # s3_model.sync_all_repos()

    # Set the controller to work with S3.
    s3_view = S3Controller.as_view('s3_view', s3_model)
    app.add_url_rule('/<path:subpath>', view_func=s3_view,
        methods=['GET', 'PUT', 'DELETE'])


app = Flask(__name__)
server_prepare()

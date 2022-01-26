"""Controllers for working with S3."""

import logging
import os

from flask import jsonify
from flask import request
from flask.views import MethodView

from helpers.auth_provider import auth_provider
from s3repo.model import ALLOWED_EXTENSIONS
from s3repo.model import S3ModelRequestError
from s3repo.package import Package
from s3repo.repoinfo import RepoAnnotation


class S3Controller(MethodView):
    """Controller for working with S3 according to the REST model."""

    def __init__(self, model):
        self.model = model

    @staticmethod
    def check_filename(filename):
        """Checks if the filename corresponds the model requirements."""
        if filename == '' or not ('.' in filename and
                os.path.splitext(filename)[1] in ALLOWED_EXTENSIONS):
            return False

        return True

    @staticmethod
    def response_message(message, status):
        """Generate response with a message."""
        response = jsonify({'message': message})
        response.status_code = status
        return response

    @auth_provider.login_required
    def put(self, subpath):
        """Generates a Package object from the request and tries
        to upload it to S3 using S3Model.
        """
        package = Package()
        package.product = request.form.get('product', '')
        for _, file in request.files.items():
            if not S3Controller.check_filename(file.filename):
                msg = 'Invalid filename. Allowed file extensions: ' +\
                    ', '.join(ALLOWED_EXTENSIONS)
                logging.warning(msg)
                return S3Controller.response_message(msg, 400)

            package.add_file(file.filename, file)

        try:
            package.repo_annotation = RepoAnnotation(subpath, self.model.get_supported_repos())
        except RuntimeError as err:
            logging.warning(str(err))
            return S3Controller.response_message(str(err), 400)

        try:
            self.model.put_package(package)
        except S3ModelRequestError as err:
            msg = "Can't upload the package to S3: " + str(err)
            logging.warning(msg)
            return S3Controller.response_message(msg, 400)
        except Exception as err:
            msg = "Can't upload the package to S3: " + str(err)
            logging.warning(msg)
            return S3Controller.response_message(msg, 500)

        msg = "Files uploaded: " + ', '.join(file for file in package.files)
        logging.info(msg)
        return S3Controller.response_message('OK', 201)

    @auth_provider.login_required
    def post(self, subpath):
        """Update metainformation of the repository."""
        try:
            repo_annotation = RepoAnnotation(subpath, self.model.get_supported_repos())
        except RuntimeError as err:
            logging.warning(str(err))
            return S3Controller.response_message(str(err), 400)

        try:
            self.model.update_repo(repo_annotation)
        except Exception as err:
            msg = "Can't update repository: " + str(err)
            logging.warning(msg)
            return S3Controller.response_message(msg, 500)

        msg = "Repository (%s) set to queue for update." % (subpath)
        logging.info(msg)
        return S3Controller.response_message('OK', 200)

    def delete(self, subpath):
        """Delete the file or Package according to the "subpath" path."""
        return S3Controller.response_message('Delete has not yet been implemented.',
            501)

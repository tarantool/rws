"""Controllers for working with S3."""

import copy
import logging
import os
import re

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

    def __init__(self, model, anchors):
        self.model = model
        self.anchors = anchors

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

    def _generate_repo_annotations(self, path):
        """Generates a list of repository annotations according to the path."""
        repo_annotations = []
        repo_anchors = {}

        # Find the anchors in the URI.
        path_list = path.split('/')
        for i in range(0, len(path_list)):
            if path_list[i] in self.anchors:
                repo_anchors[i] = self.anchors[path_list[i]]

        # If no anchors are found, we use the passed URI to form the RepoAnnotation.
        if len(repo_anchors) == 0:
            repo_annotations.append(RepoAnnotation(path, self.model.get_supported_repos()))
            return repo_annotations

        # Generate a list of URIs according to the present anchors.
        generated_path_lists = [path_list.copy()]
        for anchor_position, anchor_value_list in repo_anchors.items():
            tmp_generated_path_lists =[]
            for anchor_value in anchor_value_list:
                for generated_path_list in generated_path_lists:
                    tmp_generated_path_list = copy.deepcopy(generated_path_list)
                    tmp_generated_path_list[anchor_position] = anchor_value
                    tmp_generated_path_lists.append(tmp_generated_path_list)
            generated_path_lists = tmp_generated_path_lists

        # Generate the RepoAnnotations list according to the generated URI list.
        for generated_path_list in generated_path_lists:
            generated_path = os.path.normpath('/'.join(generated_path_list))
            repo_annotations.append(RepoAnnotation(generated_path, self.model.get_supported_repos()))

        return repo_annotations

    @auth_provider.login_required
    def put(self, subpath):
        """Generates a Package object from the request and tries
        to upload it to S3 using S3Model.
        """
        package = Package()
        package.product = request.form.get('product', '')
        for _, file in request.files.items():
            if not S3Controller.check_filename(file.filename):
                # Temporary trick to skip the ".ddeb" files.
                if '.' in file.filename and \
                        os.path.splitext(file.filename)[1] == '.ddeb':
                    logging.warning('Skip file: ' + file.filename)
                    continue

                msg = 'Invalid filename. Allowed file extensions: ' +\
                    ', '.join(ALLOWED_EXTENSIONS)
                logging.warning(msg)
                return S3Controller.response_message(msg, 400)

            package.add_file(file.filename, file)

        try:
            package.repo_annotations = self._generate_repo_annotations(subpath)
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
        """Update metainformation of the repositories."""
        try:
            repo_annotations = self._generate_repo_annotations(subpath)
        except RuntimeError as err:
            logging.warning(str(err))
            return S3Controller.response_message(str(err), 400)

        try:
            for repo_annotation in repo_annotations:
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

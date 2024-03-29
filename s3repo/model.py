"""Model for working with the repositories on S3."""

from collections import namedtuple
import logging
from multiprocessing.pool import ThreadPool
import os
import re
import subprocess as sp
import tempfile
import time
from threading import Lock
from threading import Thread

import boto3

from s3repo.repoinfo import RepoInfo


ALLOWED_EXTENSIONS = {'.rpm', '.deb', '.dsc', '.xz', '.gz'}


class S3ModelRequestError(Exception):
    """S3ModelRequestError - exception that is raised when trying to
    use invalid input data when working with any S3Model.
    """


class S3AsyncModel:
    """S3AsyncModel - model for working with repositories
    on S3 in "Async" mode. "Async" means that it has several
    independent steps:
        - add / update / delete a package to the repository
        - update the repository metainformation

    If any other actions are performed on the packages between
    adding the package and updating the metainformation, this
    also will be reflected in the metainformation.

    The "mkrepo" util (https://github.com/knazarov/mkrepo)
    will be used to update metainformation.
    """

    def __init__(self, s3_settings):
        """When the "S3AsyncModel" object is created, a resource
        representing the S3 segment is created and the synchronization
        thread is started. A sync thread is required to update
        metainformation in updated repositories.

        s3_settings - dictionary contains the settings required
        to connect to S3.
        s3_settings:
            - region - S3 region
            - endpoint_url - S3 server URL
            - bucket_name - name of a bucket with repositories
            - base_path - path inside the bucket to repositories
            - access_key_id - S3 access key ID
            - secret_access_key - S3 secret key
            - public_read - set public access to files uploaded to S3
                (True/False)
            - supported_repos - dictionary describing the supported
                repositories, tarantool version, distributions...
        """
        self.s3_settings = s3_settings
        self.s3_resource = boto3.resource(
            service_name='s3',
            region_name=self.s3_settings['region'],
            endpoint_url=self.s3_settings['endpoint_url'],
            aws_access_key_id=self.s3_settings['access_key_id'],
            aws_secret_access_key=self.s3_settings['secret_access_key']
        )
        self.bucket = self.s3_resource.Bucket(self.s3_settings['bucket_name'])
        self.s3_client = self.bucket.meta.client

        # unsync_repos - set of repositories for which metainformation
        # needs to be updated. All actions with "unsync_repos" must
        # be done under the "sync_lock".
        self.sync_lock = Lock()
        self.unsync_repos = set()

        # A sync thread is required to update metainformation
        # in updated repositories.
        self.sync_thread = Thread(target=self.sync, args=(True,))
        self.sync_thread.daemon = True
        self.sync_thread.start()

    @staticmethod
    def _format_paths(dist_path, dist_version, dist_base, filename, product):
        """Formats the file path and repository path according
        to the filename and distribution information.
        Returns an array of tuples (repo_path, path).
        """
        result = []
        file_type_err = 'The "{0}" file does not match the type of files ' +\
            'used in the {1}-based repositories.'
        if dist_base == 'rpm':
            if re.fullmatch(r'.*\.(x86_64|aarch64)\.rpm', filename):
                # Example of the path for x86_64 rpm repository:
                # .../live/1.10/fedora/31/x86_64
                repo_path = '/'.join([
                    dist_path,
                    dist_version,
                    re.match(r'.*\.(?P<arch>(x86_64|aarch64))\.rpm', filename).group('arch')
                ])
                # Example of the path to upload rpm files:
                # .../live/1.10/fedora/31/x86_64/Packages
                path = '/'.join([
                    repo_path,
                    'Packages',
                    filename
                ])

                result.append((repo_path, path))
            elif re.fullmatch(r'.*\.noarch\.rpm', filename):
                # The "noarch" package must be uploaded to all supported architectures.
                supported_arches = ['x86_64', 'aarch64']

                for arch in supported_arches:
                    repo_path = '/'.join([
                        dist_path,
                        dist_version,
                        arch
                    ])

                    path = '/'.join([
                        repo_path,
                        'Packages',
                        filename
                    ])

                    result.append((repo_path, path))
            elif re.fullmatch(r'.*\.src\.rpm', filename):
                # Example of the path for src.rpm repository:
                # .../live/1.10/fedora/31/SRPMS
                repo_path = '/'.join([
                    dist_path,
                    dist_version,
                    'SRPMS'
                ])
                # Example of the path to upload src.rpm files:
                # .../live/1.10/fedora/31/SRPMS/Packages
                path = '/'.join([
                    repo_path,
                    'Packages',
                    filename
                ])

                result.append((repo_path, path))
            else:
                raise S3ModelRequestError(file_type_err.format(
                    filename, dist_base))
        elif dist_base == 'deb':
            if not product:
                error_msg = ('The "product" form is absent in request.'\
                             + ' The "product" form is used to place '\
                             + ' package files in deb repositories.'\
                             + ' Example:'\
                             + ' .../release/series-2/ubuntu/pool/focal/main/p/product_name/...')
                raise S3ModelRequestError(error_msg)
            if re.fullmatch(r'.*\.(deb|dsc|tar\.xz|tar\.gz)', filename):
                # https://wiki.debian.org/DebianRepository/Format
                # Example of the path for deb repository ("archive root"):
                # .../live/1.10/ubuntu
                repo_path = dist_path
                # Example of the path to upload files:
                # .../live/1.10/ubuntu/pool/disco/main/s/small
                path = '/'.join([
                    repo_path,
                    'pool',
                    dist_version,
                    'main',
                    product[:1],
                    product,
                    filename
                ])

                result.append((repo_path, path))
            else:
                raise S3ModelRequestError(file_type_err.format(
                    filename, dist_base))
        else:
            raise RuntimeError('Unknown repository base: {0}.'.format(dist_base))

        return result

    @staticmethod
    def _objects_to_items(objects):
        """Formation of a list of resources (with metainformation)
        located at the specified path on S3 from the information
        received through the "boto3" API.
        """

        fields = ['Type', 'Name', 'LastModified', 'Size']

        # "Item" is tuple with metainfo of file or directory.
        # Fields format:
        # +------+------+--------------+------+
        # | Type | Name | LastModified | Size |
        # +------+------+--------------+------+
        Item = namedtuple('Item', fields, defaults=['', '', '', ''])

        # Actually, S3 doesn't use the term directory/path, it
        # simply maps the objects inside the bucket to a key like
        # "path/to/object", where "/" is used as a delimiter for
        # the common prefix of a group of keys. The result returns
        # each distinct key prefix containing the delimiter in a
        # "CommonPrefixes" element i.e. list of subdirectories.
        common_prefixes = objects.get('CommonPrefixes') or {}
        items = []
        for prefix in common_prefixes:
            directory_name = prefix.get('Prefix').split('/')[-2]
            item = Item('directory', directory_name)
            items.append(item)

        # "Contents" is a metadata about each file returned.
        contents = objects.get('Contents') or {}
        for file_meta in contents:
            file_name = file_meta.get('Key').split('/')[-1]
            # list_objects_v2() paginator returns the current
            # directory, as well as files with the same name
            # (prefix), messing with the current directory,
            # because they are S3 objects too. Ignore these
            # objects.
            if not file_name:
                continue
            last_modified = file_meta.get('LastModified').strftime("%Y-%m-%d %H:%M:%S")
            size = file_meta.get('Size')

            item = Item('file', file_name, last_modified, size)
            items.append(item)

        return items

    def _get_gpg_key_by_series(self, tarantool_series):
        """Returns the GPG key ID according to "tarantool_series" of the repository."""
        gpg_sign_key = ''
        if tarantool_series == 'modules' and self.s3_settings.get('gpg_modules_sign_key'):
            gpg_sign_key = self.s3_settings.get('gpg_modules_sign_key')
        elif self.s3_settings.get('gpg_sign_key'):
            gpg_sign_key = self.s3_settings.get('gpg_sign_key')

        return gpg_sign_key

    def _get_deb_repo_info(self, base_path, gpg_key):
        """Returns the RepoInfo list for a deb-based repository
        for updating metainformation with the 'mkrepo' tool.
        base_path(string) - path to the distribution.
        gpg_key(string) - gpg sign key ID.
        """

        # Actually, S3 doesn't use the term directory/path, it simply maps the
        # objects inside the bucket to a key like "path/to/object", where "/"
        # is used as a delimiter for the common prefix of a group of keys.
        # Here the term "path" is used to analogy with navigation in a local
        # file system such as "ext4". Since we want to known if the repository
        # contains files, we request if objects with this prefix("path") exist
        # (it is enough for us to know that the first level content is exists).
        #
        # See https://github.com/boto/boto3/issues/134 for how to list first
        # level content by a specific prefix.

        path = base_path + '/'
        list_objs = self.bucket.meta.client.list_objects_v2(
            Bucket=self.bucket.name,
            Delimiter='/',
            Prefix=path
        )
        if list_objs.get('CommonPrefixes') is None:
            return []

        # In the case of a deb-base distribution, the meta information about
        # packages in all versions of the distribution is updated together.
        # So we just return the information related with distribution.
        return [RepoInfo(path, gpg_key)]

    def _get_rpm_repo_info(self, base_path, gpg_key, dist_versions):
        """Returns the list of the paths to the rpm-based reposies
        for updating metainformation with the 'mkrepo' tool.
        base_path(string) - path to the distribution.
        dist_versions(list) - list of the distribution versions.
        gpg_key(string) - gpg sign key ID.
        """
        # See the first comment in "_get_deb_repo_info" method.

        # In the case of an rpm-based distribution, one distribution version can
        # include several repositories (for example "x86_64" and "SRPM").
        # We must collect them all.
        repos_list = []
        for ver in dist_versions:
            # Path to all repositories of the distribution version.
            common_path = '/'.join([base_path, ver]) + '/'
            list_objs = self.bucket.meta.client.list_objects_v2(
                Bucket=self.bucket.name,
                Delimiter='/',
                Prefix=common_path
            )
            dist_repos_list = list_objs.get('CommonPrefixes')
            if dist_repos_list is None:
                continue
            for repo in dist_repos_list:
                # In this context, "Prefix" is a path to the repository.
                repos_list.append(RepoInfo(repo['Prefix'], gpg_key))

        return repos_list

    def _get_repository_list(self):
        """Returns a list of paths to repositories in the current bucket."""
        supported_repos = self.get_supported_repos()
        repos_list = []
        result_list = []

        # Since collecting the list of paths to repositories involves a large
        # number of S3 requests through the network, it is recommended to use a
        # thread pool to execute them in parallel (the thread will be idle for a
        # "long" time, waiting for a response from S3).
        #
        # The number of processes = 20 was chosen experimentally.
        with ThreadPool(processes=20) as pool:
            for kind in supported_repos['repo_kind']:
                for series in supported_repos['tarantool_series']:
                    gpg_key = self._get_gpg_key_by_series(series)
                    for dist, dist_description in supported_repos['distrs'].items():
                        path = ''
                        base_path = self.s3_settings.get('base_path', '')
                        if base_path:
                            path = '/'.join([base_path, kind, series, dist])
                        else:
                            path = '/'.join([kind, series, dist])
                        if dist_description['base'] == 'deb':
                            result_list.append(
                                pool.apply_async(self._get_deb_repo_info, (path, gpg_key))
                            )
                        elif dist_description['base'] == 'rpm':
                            result_list.append(
                                pool.apply_async(
                                    self._get_rpm_repo_info,
                                    (path, gpg_key, dist_description['versions'])
                                )
                            )
                        else:
                            raise RuntimeError('Unknown repository base: ' +
                                               dist_description['base'])

            # Collect the information about location of all the
            # repositories from the bucket together.
            for res in result_list:
                repos_list.extend(res.get())

        return repos_list

    def _get_abs_path(self, path):
        """Get absolute (base_path + path) normalized path."""

        base_path = self.s3_settings.get('base_path') or ''
        abs_path = os.path.normpath('/'.join([base_path, path]))
        abs_path = abs_path.strip('/')

        return abs_path

    def determine_type(self, path):
        """Find an object spcified by "path" and determine its
        type. Type can be "directory", "file" or None if object hasn't found.
        """

        abs_path = self._get_abs_path(path)

        # Parameters for list_objects_v2():
        # * "Bucket" is a bucket name.
        # * "Delimiter" is a character you use to group keys.
        # * "Prefix" limits the response to keys that begin with
        # the specified prefix i.e. it allows to get files and
        # subdiectories located only in directory specified by
        # 'abs_path'.
        #
        # See https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3.html#S3.Client.list_objects_v2
        # for more detaied description.
        list_parameters = {'Bucket': self.bucket.name,
                           'Delimiter': '/',
                           'Prefix': abs_path}
        objects = self.s3_client.list_objects_v2(**list_parameters)
        if not objects.get('CommonPrefixes'):
            if objects.get('KeyCount'):
                # If we haven't "CommonPrefixes" then it isn't
                # directory. If "KeyCount" isn't 0 then object
                # spcified by the path exists and it is a file.
                return 'file'
            else:
                return None

        return 'directory'

    def get_supported_repos(self):
        """Get description of the currently supported repos."""
        return self.s3_settings['supported_repos']

    def update_repo(self, repo_annotation):
        """Update all repositories according to the "repository annotation"."""
        repo_list = []

        dist_path = os.path.join(self.s3_settings.get('base_path', ''),
                                 repo_annotation.repo_kind,
                                 repo_annotation.tarantool_series,
                                 repo_annotation.dist)

        dist_base = self.get_supported_repos()['distrs'][repo_annotation.dist]['base']
        gpg_key = self._get_gpg_key_by_series(repo_annotation.tarantool_series)

        if dist_base == 'rpm':
            repo_list = self._get_rpm_repo_info(dist_path, gpg_key, [repo_annotation.dist_version])
        elif dist_base == 'deb':
            repo_list = self._get_deb_repo_info(dist_path, gpg_key)
        else:
            raise RuntimeError('Unknown repository base: {0}.'.format(dist_base))

        if not repo_list:
            raise RuntimeError("Repository {0} doesn't exists".format(str(repo_annotation)))

        # Add the repositories to the unsync list.
        self.sync_lock.acquire()
        self.unsync_repos.update(repo_list)
        self.sync_lock.release()

    def sync_all_repos(self):
        """Update the metainformation of all known repositories."""
        # Get the information about location of all the
        # repositories from the bucket.
        repos_to_update = self._get_repository_list()

        # Add the repositories to the unsync list.
        self.sync_lock.acquire()
        for repo in repos_to_update:
            self.unsync_repos.add(repo)
        self.sync_lock.release()

        # Add additional workers to update metainformation (approximate
        # number of repositories to be synced ~ 600).
        # 20 - the number up on the spot. Perhaps it will be corrected later.
        threads_num = 20
        with ThreadPool(processes=threads_num) as pool:
            result_list = []
            for _ in range(0, threads_num):
                result_list.append(pool.apply_async(self.sync, (False,)))
            for res in result_list:
                # Wait for all additional workers to complete.
                res.wait()

    def sync(self, permanent):
        """Update a metainformation of repositoties from the "unsync_repo" set.
        permanent(bool) - describes whether the function should process data
        permanent or whether it can "return" if all current work has been
        completed.
        """
        logging.info('Start sync thread.')
        while True:
            if self.unsync_repos:
                self.sync_lock.acquire()
                sync_repo = self.unsync_repos.pop()
                self.sync_lock.release()

                with tempfile.TemporaryDirectory(prefix='.rws_', dir='.') as tmpdirname:
                    mkrepo_cmd = [
                        'mkrepo',
                        '--temp-dir',
                        tmpdirname,
                        '--s3-access-key-id',
                        str(self.s3_settings['access_key_id']),
                        '--s3-secret-access-key',
                        str(self.s3_settings['secret_access_key']),
                        '--s3-endpoint',
                        str(self.s3_settings['endpoint_url']),
                        '--s3-region',
                        str(self.s3_settings['region']),
                    ]

                    if self.s3_settings.get('force_sync'):
                        mkrepo_cmd.append('--force')
                    if self.s3_settings.get('public_read'):
                        mkrepo_cmd.append('--s3-public-read')

                    # Set the "Origin", "Label" and "Description" values
                    # that can be used for the deb repository.
                    env = dict(
                        os.environ,
                        MKREPO_DEB_ORIGIN='Tarantool',
                        MKREPO_DEB_LABEL='tarantool.org',
                        MKREPO_DEB_DESCRIPTION='Tarantool DBMS and Tarantool modules')
                    # Include the package metainformation signature
                    # if we have a gpg key.
                    if sync_repo.sign_key:
                        mkrepo_cmd.append('--sign')
                        env = dict(env,
                                   GPG_SIGN_KEY=sync_repo.sign_key)

                    # Set the path to the repository.
                    mkrepo_cmd.append('s3://{0}/{1}'.format(
                        self.s3_settings['bucket_name'],
                        sync_repo.path))

                    with sp.Popen(mkrepo_cmd, env=env) as mkrepo_ps:
                        result = mkrepo_ps.wait()
                        if result != 0:
                            self.sync_lock.acquire()
                            self.unsync_repos.add(sync_repo)
                            self.sync_lock.release()
                            logging.warning('Synchronization failed: ' + sync_repo.path)
                        else:
                            logging.info('Metainformation has been synced: ' + sync_repo.path)
            elif permanent:
                # The "unsync_repos" set is empty.
                # Let's just wait a while.
                time.sleep(5)
            else:
                # This is a temporary "worker" and all current
                # work has been completed.
                logging.info('Stop sync thread.')
                break

    def put_package(self, package):
        """Load the package to S3."""
        # Files already uploaded to S3.
        # Information from this dict is used to copy a file from
        # one repository to another if the file is already uploaded to S3.
        origin_files = {}

        for repo_annotation in package.repo_annotations:
            # self.s3_settings['base_path'] can be None or '', in this case,
            # you do not need to add it to the path.
            dist_path_list = [
                repo_annotation.repo_kind,
                repo_annotation.tarantool_series,
                repo_annotation.dist
            ]
            if self.s3_settings.get('base_path', ''):
                dist_path_list.insert(0, self.s3_settings['base_path'])

            dist_path = '/'.join(dist_path_list)
            dist_base = self.get_supported_repos()['distrs'][repo_annotation.dist]['base']

            # Set the arguments of the uploaded files according to the settings.
            extra_args = {}
            if self.s3_settings.get('public_read'):
                extra_args['ACL'] = 'public-read'

            gpg_sign_key = self._get_gpg_key_by_series(repo_annotation.tarantool_series)

            # List of repositories where the new package has been uploaded,
            # but the metainformation hasn't been updated yet.
            unsync_repos_local = set()
            for filename, file in package.files.items():
                path_list = S3AsyncModel._format_paths(dist_path, repo_annotation.dist_version,
                                                       dist_base, filename, package.product)

                for repo_path, path in path_list:
                    # If a file needs to be uploaded to several repositories:
                    # it is uploaded to one of them, and then copied to others.
                    if filename in origin_files:
                        # In the documentation
                        # (https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3.html#S3.Bucket.copy)
                        # `Bucket.copy` uses `ExtraArgs` which only allow `ALLOWED_DOWNLOAD_ARGS`
                        # (don't include `ACL`). But in fact `ALLOWED_COPY_ARGS` is used for copying
                        # (https://github.com/boto/s3transfer/blob/279f82c6f9d01b19abf69d8fa08441c2064fba7f/s3transfer/manager.py#L381).
                        # So, we can use `ACL` in `ExtraArgs`.
                        self.bucket.copy(origin_files[filename], path, ExtraArgs=extra_args)
                    else:
                        obj = self.bucket.Object(path)
                        obj.upload_fileobj(file, ExtraArgs=extra_args)
                        origin_files[filename] = {
                            'Bucket': self.bucket.name,
                            'Key': path
                        }

                    # Several files can be uploaded to the same repo.
                    # Let's add the repo to the local "unsync_repos" set
                    # and merge it with the global one after the end of
                    # the iteration.
                    unsync_repos_local.add(RepoInfo(repo_path, gpg_sign_key))

            self.sync_lock.acquire()
            self.unsync_repos.update(unsync_repos_local)
            self.sync_lock.release()

    def get_package(self, package):
        """Download a package from S3."""
        NotImplementedError("get_package hasn't been implemented yet.")

    def delete_package(self, package):
        """Delete a package from S3."""
        NotImplementedError("delete_package hasn't been implemented yet.")

    def get_directory(self, path):
        """Get lists and metadata of directories and files within
        directory from S3.
        """

        abs_path = self._get_abs_path(path)

        # Parameters for list_objects_v2():
        # * "Bucket" is a bucket name.
        # * "Delimiter" is a character you use to group keys.
        # * "MaxKeys" sets the maximum number of keys returned in
        # the response. By default the action returns up to 1,000
        # key names. The response might contain fewer keys but will
        # never contain more.
        # * "Prefix" limits the response to keys that begin with
        # the specified prefix i.e. it allows to get files and
        # subdiectories located only in directory specified by
        # 'abs_path'.
        #
        # See https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3.html#S3.Client.list_objects_v2
        # for more detaied description.
        list_parameters = {'Bucket': self.bucket.name,
                           'Delimiter': '/',
                           'MaxKeys': 1,
                           'Prefix': abs_path}

        # Check the existence of the directory.
        # https://stackoverflow.com/a/68910145
        objects = self.s3_client.list_objects_v2(**list_parameters)
        if not 'CommonPrefixes' in objects:
            raise RuntimeError('No such directory.')

        # Get all objects from the directory.
        list_parameters['MaxKeys'] = 1000
        # To get the "content" of the directory, we must add "/" at the end of the path.
        if abs_path != '':
            abs_path = abs_path + '/'
        list_parameters['Prefix'] = abs_path

        paginator = self.s3_client.get_paginator('list_objects_v2')

        items = []
        for objects in paginator.paginate(**list_parameters):
            items.extend(S3AsyncModel._objects_to_items(objects))

        return items

    def get_file(self, path):
        """Get a file from S3 as a "StreamingBody" object.
        See https://botocore.amazonaws.com/v1/documentation/api/latest/reference/response.html#botocore.response.StreamingBody
        """

        try:
            # We suppose that files which we deal with are not
            # large enough and the fit in RAM.
            response = self.s3_client.get_object(Bucket=self.bucket.name,
                                                 Key=self._get_abs_path(path))
        except self.s3_client.exceptions.NoSuchKey:
            raise RuntimeError("No such key.")
        except self.s3_client.exceptions.InvalidObjectState:
            raise RuntimeError("Invalid object state.")

        # "Body" is a data or a requested file itself.
        #
        # See https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3.html#S3.Client.get_object
        # for more detaied description.
        return response.get('Body')

    def delete_file(self, path):
        """Delete a file from S3."""
        NotImplementedError("delete_file hasn't been implemented yet.")

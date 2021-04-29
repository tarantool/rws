"""Model for working with the repositories on S3."""

import re
import subprocess as sp
import time
from threading import Lock
from threading import Thread

import boto3


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
    def _format_paths(dist_path, dist_version, dist_base, filename):
        """Formats the file path and repository path according
        to the filename and distribution information.
        Returns a tuple (repo_path, path).
        """
        path = ''
        repo_path = ''
        file_type_err = 'The "{0}" file does not match the type of files ' +\
            'used in the {1}-based repositories.'
        if dist_base == 'rpm':
            if re.fullmatch(r'.*\.(x86_64|noarch)\.rpm', filename):
                # Example of the path for x86_64, noarch rpm repository:
                # .../live/1.10/fedora/31/x86_64
                repo_path = '/'.join([
                    dist_path,
                    dist_version,
                    'x86_64'
                ])
                # Example of the path to upload rpm files:
                # .../live/1.10/fedora/31/x86_64/Packages
                path = '/'.join([
                    repo_path,
                    'Packages',
                    filename
                ])
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
            else:
                raise S3ModelRequestError(file_type_err.format(
                    filename, dist_base))
        elif dist_base == 'deb':
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
                    filename[:1],
                    filename.partition('_')[0],
                    filename
                ])
            else:
                raise S3ModelRequestError(file_type_err.format(
                    filename, dist_base))
        else:
            raise RuntimeError('Unknown repository base: {0}.'.format(dist_base))

        return (repo_path, path)

    def _upload_files(self, package, tarantool_series, origin_files):
        """Upload files to one repo on S3."""
        # self.s3_settings['base_path'] can be None or '', in this case,
        # you do not need to add it to the path.
        dist_path_list = [package.repo_kind, tarantool_series, package.dist]
        if self.s3_settings.get('base_path', ''):
            dist_path_list.insert(0, self.s3_settings['base_path'])

        dist_path = '/'.join(dist_path_list)
        dist_base = self.get_supported_repos()['distrs'][package.dist]['base']

        # List of repositories where the new package has been uploaded,
        # but the metainformation hasn't been updated yet.
        unsync_repos_local = set()
        for filename, file in package.files.items():
            repo_path, path = S3AsyncModel._format_paths(
                dist_path, package.dist_version, dist_base, filename)

            # If a file needs to be uploaded to several repositories:
            # it is uploaded to one of them, and then copied to others.
            if filename in origin_files:
                self.bucket.copy(origin_files[filename], path)
            else:
                obj = self.bucket.Object(path)
                obj.upload_fileobj(file)
                origin_files[filename] = {
                    'Bucket': self.bucket.name,
                    'Key': path
                }

            # Several files can be uploaded to the same repo.
            # Let's add the repo to the local "unsync_repos" set
            # and merge it with the global one after the end of
            # the iteration..
            unsync_repos_local.add(repo_path)

        self.sync_lock.acquire()
        self.unsync_repos.update(unsync_repos_local)
        self.sync_lock.release()

    def get_supported_repos(self):
        """Get description of the currently supported repos."""
        return self.s3_settings['supported_repos']

    def sync_all_repos(self):
        """Update the metainformation of all known repositories."""
        NotImplementedError("sync_all_repos hasn't been implemented yet.")

    def sync(self, permanent):
        """Update a metainformation of repositoties from the "unsync_repo" set.
        permanent(bool) - describes whether the function should process data
        permanent or whether it can "return" if all current work has been
        completed.
        """
        while True:
            if self.unsync_repos:
                self.sync_lock.acquire()
                sync_repo = self.unsync_repos.pop()
                self.sync_lock.release()

                mkrepo_cmd = [
                    'mkrepo',
                    '--s3-access-key-id',
                    str(self.s3_settings['access_key_id']),
                    '--s3-secret-access-key',
                    str(self.s3_settings['secret_access_key']),
                    '--s3-endpoint',
                    str(self.s3_settings['endpoint_url']),
                    '--s3-region',
                    str(self.s3_settings['region']),
                    's3://' + self.s3_settings['bucket_name'] + '/' + sync_repo
                ]
                with sp.Popen(mkrepo_cmd) as mkrepo_ps:
                    result = mkrepo_ps.wait()
                    if result != 0:
                        self.sync_lock.acquire()
                        self.unsync_repos.add(sync_repo)
                        self.sync_lock.release()
            elif permanent:
                # The "unsync_repos" set is empty.
                # Let's just wait a while.
                time.sleep(5)
            else:
                # This is a temporary "worker" and all current
                # work has been completed.
                break

    def put_package(self, package):
        """Load the package to S3."""
        tarantool_series_to_upload = []
        if package.tarantool_series == 'enabled':
            tarantool_series_to_upload = self.get_supported_repos()['enabled']
        else:
            tarantool_series_to_upload.append(package.tarantool_series)

        # Files already uploaded to S3.
        # Information from this dict is used to copy a file from
        # one repository to another if the file is already uploaded to S3.
        origin_files = {}

        for tarantool_series in tarantool_series_to_upload:
            self._upload_files(package, tarantool_series, origin_files)

    def get_package(self, package):
        """Download a package from S3."""
        NotImplementedError("get_package hasn't been implemented yet.")

    def delete_package(self, package):
        """Delete a package from S3."""
        NotImplementedError("delete_package hasn't been implemented yet.")

    def get_file(self, path):
        """Download a file from S3."""
        NotImplementedError("get_file hasn't been implemented yet.")

    def delete_file(self, path):
        """Delete a file from S3."""
        NotImplementedError("delete_file hasn't been implemented yet.")

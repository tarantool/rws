"""Description of the uploaded / downloaded package."""

class Package:
    """Description of the uploaded / downloaded package."""

    def __init__(self):
        # Distribution (ubuntu, debian, fedora ...).
        self.dist = ''
        # Version of distribution (trusty, xenial, bionic ...).
        self.dist_version = ''
        # This parameter refers to the series of the tarantool
        # (1.10, 2.5, 2.6 ...).
        self.tarantool_series = ''
        # Repo kind (live, release...).
        self.repo_kind = ''
        # Files to upload.
        self.files = {}

    def add_file(self, file_type, file):
        """Add a file to Package."""
        self.files[file_type] = file

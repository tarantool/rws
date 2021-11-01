"""Information about repository."""

class RepoInfo:
    """Information about repository."""

    def __init__(self, path='', sign_key=''):
        # Path to the repository.
        self.path = path
        # THe the GPG sign key ID that should be used to sign
        # of the repository.
        self.sign_key = sign_key

    def __hash__(self):
        return hash(self.path)

    def __eq__(self, other):
        return self.path == self.path

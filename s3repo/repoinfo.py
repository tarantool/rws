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


class RepoAnnotation:
    """Annotation of the repository.

    This is a more common repository description than "RepoInfo".
    What does it mean:
    When I want to add something (or just update the metainformation)
    of repository "release/1.10/el/7", in fact the three repositories
    will be updated (x86_64, SRPMS, aarch64), but it's not interesting for
    me. Or, when I update something in the repository "release/1.10/debian/jessie"
    the metainformation for all existing version of the distribution
    will be updated (bullseye, jessie, stretch, ...).
    So, the "RepoAnnotation" describes the repository from the user's point of
    view. And in fact, it can include more than one repository.
    """

    def __init__(self, path, supported_repos):
        # Parse path.
        path_list = path.split('/')
        RepoAnnotation.check_path(path_list, supported_repos)

        # Repo kind (live, release...).
        self.repo_kind = path_list[0]
        # This parameter refers to the series of the tarantool
        # (1.10, 2.5, 2.6 ...).
        self.tarantool_series = path_list[1]
        # Distribution (ubuntu, debian, fedora ...).
        self.dist = path_list[2]
        # Version of distribution (trusty, xenial, bionic ...).
        self.dist_version = path_list[3]

    @staticmethod
    def check_path(path, supported_repos):
        """Checks if the given distribution is supported for
        uploading packages.
        """
        # Correct path = repo_kind/tarantool_series/dist/dist_ver
        # Example: live/1.10/el/7
        if len(path) != 4:
            raise RuntimeError('Invalid URL.')

        if path[0] not in supported_repos['repo_kind']:
            raise RuntimeError('Repo kind "' + path[0] + '" is not supported.')
        if path[1] not in supported_repos['tarantool_series']:
            raise RuntimeError('Tarantool series "' + path[1] + '"" is not supported.')
        if path[2] not in supported_repos['distrs']:
            raise RuntimeError('Distribution "' + path[2] + '" is not supported.')
        if path[3] not in supported_repos['distrs'][path[2]]['versions']:
            raise RuntimeError('Distribution version "' + path[3] + '" is not supported.')

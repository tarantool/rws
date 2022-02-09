"""An auth_provider (Singleton) is created in the module, which will be used
in the application to authenticate users.
"""

from typing import Dict
from typing import Union

from flask_httpauth import HTTPBasicAuth
from werkzeug.security import check_password_hash


class HTTPAuthProvider(HTTPBasicAuth):
    """User authentication provider class(Singleton)."""
    def __init__(self) -> None:
        HTTPBasicAuth.__init__(self)
        self.verify_password(self._verify_password)
        self.credentials: Dict[str, str] = {}

    def _verify_password(self, username: str, password: str) -> Union[str, bool]:
        """Verify credentials."""
        if username in self.credentials and \
                check_password_hash(self.credentials.get(username), password):
            return username

        return False

    def set_credentials(self, credential_dict: Dict[str, str]) -> None:
        """Set the credential dictionary."""
        self.credentials = credential_dict


auth_provider = HTTPAuthProvider()

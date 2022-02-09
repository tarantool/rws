"""Description of the uploaded / downloaded package."""

from typing import Dict
from typing import Optional

from s3repo.repoinfo import RepoAnnotation


class Package:
    """Description of the uploaded / downloaded package."""

    def __init__(self) -> None:
        # Annotation of the repository.
        self.repo_annotation: Optional[RepoAnnotation] = None
        # The name of the product to be used in the deb repositories.
        # Example: .../release/series-2/ubuntu/pool/focal/main/p/product_name/...
        self.product = ''
        # Files to upload.
        self.files: Dict[str, str] = {}

    def add_file(self, file_type: str, file: str) -> None:
        """Add a file to Package."""
        self.files[file_type] = file

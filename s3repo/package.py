"""Description of the uploaded package."""

class Package:
    """Description of the uploaded package."""

    def __init__(self):
        # Annotation of the repository.
        self.repo_annotation = None
        # The name of the product to be used in the deb repositories.
        # Example: .../release/series-2/ubuntu/pool/focal/main/p/product_name/...
        self.product = ''
        # Files to upload.
        self.files = {}

    def add_file(self, file_type, file):
        """Add a file to Package."""
        self.files[file_type] = file

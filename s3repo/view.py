"""View for working with the repositories on S3."""

import os
from typing import List

from flask import Response
from flask import render_template
from flask import request
from flask.views import View

from s3repo.model import Item
from s3repo.model import S3AsyncModel


class S3View(View):
    """View for working with S3 according to the REST model."""

    def __init__(self, model: S3AsyncModel) -> None:
        self.model = model

    @staticmethod
    def _readable_size(size: float) -> str:
        """Convert "size" (number of bytes) into a readable
        string.
        """

        readable_size = ''
        for unit in ['', 'Ki', 'Mi', 'Gi']:
            if abs(size) < 1024.0:
                readable_size = "%3.1f %sB" % (size, unit)
                return readable_size
            size /= 1024.0

        return "%3.1f B" % size

    @staticmethod
    def _get_directory(path: str, items: List) -> render_template:
        """Display directory content as a HTML page."""
        displayed_path = path
        parent_path = '/'.join(path.split('/')[:-2])

        # Make size human readable.
        readable_items: List[Item] = []
        for item in items:
            if item.Size != '':
                item = item._replace(Size=S3View._readable_size(item.Size))
            readable_items.append(item)

        list_parameters = {
            'displayed_path': '/' + displayed_path,
            'path': path,
            'parent_path': parent_path,
            'items': readable_items
        }

        return render_template('index.html', **list_parameters)

    @staticmethod
    def _get_file(path: str, response) -> Response:
        """Download a file to user's machine."""
        filename = path.split('/')[-1]

        return Response(
            response.read(),
            mimetype='application/octet-stream',
            headers={"Content-Disposition": "attachment; filename=" + filename}
        )

    def dispatch_request(self, subpath='/') -> Response:
        """Show a directory or download a file according to the
        "subpath" path.
        """
        path = os.path.normpath(subpath.strip('/'))
        if path == '.' or path == 'index':
            path = ''
        obj_type = self.model.determine_type(path)
        obj_type = request.args.get('type') or obj_type

        err_msg = ''
        try:
            if obj_type == 'directory':
                items = self.model.get_directory(path)
                err_msg = "Can't show the directory in S3."
                if path != '':
                    path = path + '/'
                return S3View._get_directory(path, items)
            elif obj_type == 'file':
                response = self.model.get_file(path)
                err_msg = "Can't download file from S3."
                return S3View._get_file(path, response)
            else:
                return render_template('404.html')
        except RuntimeError:
            return render_template('500.html', {'err_msg': err_msg})

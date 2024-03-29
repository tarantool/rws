"""View for working with the repositories on S3."""

import logging
import os

from flask import render_template
from flask import Response
from flask import request
from flask.views import View


class S3View(View):
    """View for working with S3 according to the REST model."""

    def __init__(self, model):
        self.model = model

    @staticmethod
    def _readable_size(size):
        """Convert "size" (number of bytes) into a readable
        string.
        """

        readable_size = ''
        for unit in ['', 'Ki', 'Mi', 'Gi']:
            if abs(size) < 1024.0:
                readable_size = "%3.1f %sB" % (size, unit)
                return readable_size
            size /= 1024.0

        return "%3.1f B" % (size)

    @staticmethod
    def _get_directory(path, items):
        """Display directory content as a HTML page."""
        displayed_path = path
        parent_path = '/'.join(path.split('/')[:-2])

        # Make size human readable.
        readable_items = []
        for item in items:
            if item.Size != '':
                item = item._replace(Size=S3View._readable_size(item.Size))
            readable_items.append(item)

        list_parameters = {'displayed_path': '/' + displayed_path,
                           'path': path,
                           'parent_path': parent_path,
                           'items': readable_items}

        return render_template('index.html', **list_parameters)

    @staticmethod
    def _get_file(path, response):
        """Download a file to user's machine."""
        filename = path.split('/')[-1]

        return Response(
            response.read(),
            mimetype='application/octet-stream',
            headers={"Content-Disposition": "attachment; filename=" + filename}
            )

    def dispatch_request(self, subpath='/'):
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
                err_msg = "Can't show the directory in S3."
                items = self.model.get_directory(path)
                if path != '':
                    path = path + '/'
                return S3View._get_directory(path, items)
            elif obj_type == 'file':
                err_msg = "Can't download file from S3."
                response = self.model.get_file(path)
                return S3View._get_file(path, response)
            else:
                return render_template('404.html')
        except RuntimeError as err:
            logging.warning(
                'An error occurred while displaying the object({0}): "{1}"'.format(path ,err))
            return render_template('500.html', err_msg=err_msg)

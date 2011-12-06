#!/usr/bin/env python
import os
import urllib

import webapp2
import jinja2
from google.appengine.api import users
from google.appengine.ext import db
from google.appengine.ext import blobstore
from google.appengine.ext.webapp import blobstore_handlers

import gncreports

class Gncfile(db.Model):
    """Models a Gnucash file."""
    user = db.UserProperty()
    blob_key = blobstore.BlobReferenceProperty()

jinja_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(os.path.dirname(__file__)))

class BaseHandler(webapp2.RequestHandler):
    @webapp2.cached_property
    def jinja2(self):
        return jinja2.get_jinja2(app=self.app)

    def render_templates(self, filename, **args):
        self.response.write(self.jinja2.render_template(filename, **args))

class IndexHandler(BaseHandler):
    def get(self):
        self.render_template('index.html', name=self.request.get('name'))

class MainHandler(webapp2.RequestHandler):
    def get(self):
        upload_url = blobstore.create_upload_url('/upload')
        template_values = {
            'upload_url': upload_url,
        }

        template = jinja_env.get_template('index.html')
        self.response.write(template.render(template_values))

class UploadHandler(blobstore_handlers.BlobstoreUploadHandler):
    def post(self):
        try:
            upload_files = self.get_uploads('file')
            blob_info = upload_files[0]
            self.redirect('/serve/%s' % blob_info.key())
        except:
            self.error(404)

class ServeHandler(blobstore_handlers.BlobstoreDownloadHandler):
    def get(self, resource):
        resource = str(urllib.unquote(resource))
        blob_info = blobstore.BlobInfo.get(resource)
        blob_reader = blobstore.BlobReader(blob_info.key())
        gncbook = gncreports.gncopen(blob_reader)

        years = []
        stms = []
        for year, stm in gncbook.monthly_income_stms():
            years.append(year)
            stms.append(stm.tohtml())
        template_values = {
            'balance_sheet': gncbook.balance_sheet().tohtml(),
            'years': years,
            'monthly_income_stms': stms
        }

        # Deletes the BlobInfo entity and the corresponding Blobstore value
        # from the datastore.
        blob_info.delete()

        template = jinja_env.get_template('reports.html')
        self.response.write(template.render(template_values))

app = webapp2.WSGIApplication([
    ('/', MainHandler),
    ('/upload', UploadHandler),
    ('/serve/([^/]+?)', ServeHandler),
    ], debug=True)

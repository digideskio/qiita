from tornado.web import authenticated, HTTPError

from os.path import isdir, join, exists
from os import makedirs, remove

from shutil import rmtree, move

from .study_handlers import check_access
from .base_handlers import BaseHandler

from qiita_core.qiita_settings import qiita_config

from qiita_db.util import (get_files_from_uploads_folders,
                           get_mountpoint)
from qiita_db.study import Study
from qiita_db.user import User
from qiita_db.exceptions import QiitaDBUnknownIDError


class StudyUploadFileHandler(BaseHandler):
    @authenticated
    def display_template(self, study_id, msg):
        """Simple function to avoid duplication of code"""
        study_id = int(study_id)
        study = Study(study_id)
        check_access(User(self.current_user), study, no_public=True,
                     raise_error=True)

        # getting the ontologies
        self.render('upload.html', user=self.current_user,
                    study_title=study.title, study_info=study.info,
                    study_id=study_id,
                    extensions=','.join(qiita_config.valid_upload_extension),
                    max_upload_size=qiita_config.max_upload_size,
                    files=get_files_from_uploads_folders(str(study_id)))

    @authenticated
    def get(self, study_id):
        try:
            study = Study(int(study_id))
        except QiitaDBUnknownIDError:
            raise HTTPError(404, "Study %s does not exist" % study_id)
        check_access(User(self.current_user), study, no_public=True,
                     raise_error=True)
        self.display_template(study_id, "")


class UploadFileHandler(BaseHandler):
    # """ main upload class
    # based on
    # https://github.com/23/resumable.js/blob/master/samples/Backend%20on%20PHP.md
    # """
    def validate_file_extension(self, filename):
        """simple method to avoid duplication of code

        This validation is server side in case they can go around the client
        side validation
        """
        if not filename.endswith(tuple(qiita_config.valid_upload_extension)):
            self.set_status(415)
            raise HTTPError(415, "User %s is trying to upload %s" %
                                 (self.current_user, filename))

    @authenticated
    def post(self):
        resumable_identifier = self.get_argument('resumableIdentifier')
        resumable_filename = self.get_argument('resumableFilename')
        resumable_chunk_number = int(self.get_argument('resumableChunkNumber'))
        resumable_total_chunks = int(self.get_argument('resumableTotalChunks'))
        study_id = self.get_argument('study_id')
        data = self.request.files['file'][0]['body']

        check_access(User(self.current_user), Study(int(study_id)),
                     no_public=True, raise_error=True)

        self.validate_file_extension(resumable_filename)

        _, base_fp = get_mountpoint("uploads")[0]

        # creating temporal folder for upload of the file
        temp_dir = join(base_fp, study_id, resumable_identifier)
        if not isdir(temp_dir):
            makedirs(temp_dir)

        # location of the file as it is transmitted
        temporary_location = join(temp_dir, resumable_filename)

        # this is the result of a failed upload
        if resumable_chunk_number == 1 and exists(temporary_location):
            remove(temporary_location)

        # append every transmitted chunk
        with open(temporary_location, 'ab') as final_file:
            final_file.write(bytes(data))

        if resumable_chunk_number == resumable_total_chunks:
            final_location = join(base_fp, study_id, resumable_filename)

            if exists(final_location):
                remove(final_location)

            move(temporary_location, final_location)
            rmtree(temp_dir)
            self.set_status(200)

    @authenticated
    def get(self):
        """ this is the first point of entry into the upload service

        this should either set the status as 400 (error) so the file/chunk is
        sent via post or 200 (valid) to not send the file
        """
        study_id = self.get_argument('study_id')
        resumable_filename = self.get_argument('resumableFilename')
        resumable_chunk_number = self.get_argument('resumableChunkNumber')

        check_access(User(self.current_user), Study(int(study_id)),
                     no_public=True, raise_error=True)

        self.validate_file_extension(resumable_filename)

        # temporaly filename or chunck
        _, fp = get_mountpoint("uploads")[0]
        tfp = join(fp, study_id,
                   resumable_filename + '.part.' + resumable_chunk_number)

        if exists(tfp):
            self.set_status(200)
        else:
            self.set_status(400)

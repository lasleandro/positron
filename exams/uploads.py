from django.conf import settings
from django.core.files.uploadhandler import FileUploadHandler, StopUpload


class PDFSizeLimit(FileUploadHandler):
    def receive_data_chunk(self, raw_data, start):
        if (start == 0 and not raw_data.startswith(b"\x01")) or (
            start + len(raw_data) > settings.SEALED_PDF_MAX_BYTES
        ):
            raise StopUpload(connection_reset=True)
        return raw_data

    def file_complete(self, file_size):
        return None

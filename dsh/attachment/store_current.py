"""Explicit rc.3 attachment capability, pending the coordinated profile switch."""
import base64
import binascii

from dsh.attachment.error import AttachmentError, IMAGE_ADMISSION_ERROR_CODES
from dsh.attachment.store import AttachmentStore
from dsh.attachment.local import LocalAttachmentStore
from dsh.attachment.immutable_current import check_abort, disk
from dsh.attachment.files_current import (
    read_file_stream_verbatim, save_file_stream_verbatim, save_file_verbatim, stored_file_path,
)

ATTACHMENT_ERROR_CODES = frozenset(IMAGE_ADMISSION_ERROR_CODES + (
    'INVALID_FILE_BASE64', 'INVALID_ATTACHMENT_REF', 'ATTACHMENT_CORRUPT',
    'ATTACHMENT_WRITE_FAILED', 'ATTACHMENT_NOT_FOUND', 'ATTACHMENT_READ_FAILED',
    'ATTACHMENT_PROJECTION_UNSUPPORTED', 'ATTACHMENT_FILES_UNSUPPORTED',
))


def is_attachment_error(error):
    code = getattr(error, 'code', None)
    return isinstance(error, Exception) and isinstance(code, str) and code in ATTACHMENT_ERROR_CODES


def decode_upload(data, image=False):
    code = 'INVALID_IMAGE_BASE64' if image else 'INVALID_FILE_BASE64'
    message = ('Image' if image else 'File') + ' upload is not canonical base64.'
    try:
        decoded = base64.b64decode(data, validate=True)
        if (image and not data) or base64.b64encode(decoded).decode('ascii') != data:
            raise ValueError('non-canonical base64')
        return decoded
    except (ValueError, TypeError, binascii.Error):
        raise AttachmentError(message, code) from None


class CurrentAttachmentAPI:
    @property
    def imageLimits(self):
        return self.image_limits

    async def validateImage(self, input_data):
        await disk(self.validate_image, input_data)

    async def saveImage(self, input_data):
        return await disk(self.save_image, input_data)

    async def saveImages(self, inputs):
        return await disk(self.save_images, inputs)

    async def admitPromptContent(self, content):
        images = [part for part in content if part['type'] == 'image']
        refs = iter(await self.admitEncodedImages(images)) if images else iter(())
        return [dict(type='text', text=part['text']) if part['type'] == 'text' else
                dict(type=part['type'], attachment=next(refs) if part['type'] == 'image' else part['attachment'])
                for part in content]

    async def admitEncodedImages(self, images):
        inputs = [dict(data=decode_upload(image['data'], image=True), mediaType=image['mediaType'],
                       **({'name': image['name']} if 'name' in image else {})) for image in images]
        return await self.saveImages(inputs)

    async def admitEncodedFile(self, input_data):
        return await self.saveFile(dict(data=decode_upload(input_data['data']),
            **({'name': input_data['name']} if 'name' in input_data else {})))

    isAttachmentError = staticmethod(is_attachment_error)

    def fileHostPath(self, ref):
        return None

    def imageHostPath(self, ref):
        return None

    async def saveFile(self, input_data):
        raise AttachmentError('The mounted attachment provider cannot store verbatim files.', 'ATTACHMENT_FILES_UNSUPPORTED')

    async def saveFileStream(self, input_data):
        raise AttachmentError('The mounted attachment provider cannot stream verbatim files.', 'ATTACHMENT_FILES_UNSUPPORTED')

    async def readFileStream(self, ref, signal=None):
        check_abort(signal)
        raise AttachmentError('The mounted attachment provider cannot read verbatim files.', 'ATTACHMENT_FILES_UNSUPPORTED')
        yield  # The failure is deferred until iteration, as for an async generator.


class CurrentAttachmentStore(CurrentAttachmentAPI, AttachmentStore):
    pass


class CurrentLocalAttachmentStore(CurrentAttachmentAPI, LocalAttachmentStore):
    async def saveFile(self, input_data):
        return await save_file_verbatim(self.root, input_data)

    async def saveFileStream(self, input_data):
        return await save_file_stream_verbatim(self.root, input_data)

    def readFileStream(self, ref, signal=None):
        return read_file_stream_verbatim(self.root, ref, signal)

    def fileHostPath(self, ref):
        return stored_file_path(self.root, ref)

    def imageHostPath(self, ref):
        return self.image_host_path(ref)

"""Verbatim file references and bounded local streams for the rc.3 candidate."""
import hashlib
import os
import re

from dsh.attachment.error import AttachmentError
from dsh.attachment.immutable_current import check_abort, disk, publish_alias, publish_object, publish_stream
from dsh.cordis.text import trim_js
from dsh.cordis.utils import js_to_string

_DIGEST = re.compile(r'^sha256:([a-f0-9]{64})\Z')
_DEVICE = re.compile(r'^(con|prn|aux|nul|com[1-9]|lpt[1-9])\Z', re.IGNORECASE)


def file_leaf_name(value=None):
    if value is None:
        return 'file'
    leaf = value[max(value.rfind('/'), value.rfind('\\')) + 1:]
    clean = re.sub(r'[\x00-\x1f\x7f]', '', leaf)
    clean = trim_js(re.sub(r'[<>:"|?*]', '_', clean)).rstrip('. ')
    if _DEVICE.fullmatch(clean.split('.', 1)[0].rstrip('. ')):
        clean = '_' + clean
    # Buffer.from replaces lone UTF-16 surrogates, and never cuts a UTF-8 codepoint.
    clean = clean.encode('utf-16-le', 'surrogatepass').decode('utf-16-le', 'replace')
    clean = clean.encode('utf-8')[:255].decode('utf-8', 'ignore').rstrip('. ')
    return clean if clean not in ('', '.', '..') else 'file'


def ensure_file_reference(ref):
    match = _DIGEST.fullmatch(js_to_string(ref.get('attachmentId')))
    name = ref.get('name')
    if match is None or name is None or name != file_leaf_name(name):
        raise AttachmentError('File attachment reference is invalid.', 'INVALID_ATTACHMENT_REF')
    return match.group(1)


def stored_file_path(root, ref):
    digest = ensure_file_reference(ref)
    return os.path.join(root, 'files', digest[:2], digest, ref['name'])


def stored_file_object_path(root, digest):
    return os.path.join(root, 'file-objects', digest[:2], digest)


async def save_file_verbatim(root, input_data):
    data = input_data['data']
    digest = hashlib.sha256(data).hexdigest()
    ref = dict(attachmentId='sha256:' + digest, name=file_leaf_name(input_data.get('name')), bytes=len(data))
    source = stored_file_object_path(root, digest)
    await publish_object(root, source, data, digest)
    await disk(publish_alias, root, source, stored_file_path(root, ref), digest)
    return ref


async def save_file_stream_verbatim(root, input_data):
    name = file_leaf_name(input_data.get('name'))
    signal = input_data.get('signal')
    stored = await publish_stream(root, input_data['data'],
        lambda digest, count: stored_file_object_path(root, digest), signal)
    digest = stored['sha256']
    ref = dict(attachmentId='sha256:' + digest, name=name, bytes=stored['bytes'])
    check_abort(signal)
    await disk(publish_alias, root, stored_file_object_path(root, digest), stored_file_path(root, ref), digest)
    check_abort(signal)
    return ref


async def read_file_stream_verbatim(root, ref, signal=None):
    check_abort(signal)
    digest = ensure_file_reference(ref)
    path = stored_file_path(root, ref)
    handle = None
    hashed, count = hashlib.sha256(), 0
    try:
        handle = open(path, 'rb', buffering=0)
        while True:
            check_abort(signal)
            chunk = await disk(handle.read, 65536)
            if not chunk:
                break
            check_abort(signal)
            hashed.update(chunk)
            count += len(chunk)
            yield chunk
    except Exception as error:
        check_abort(signal)
        if isinstance(error, FileNotFoundError):
            raise AttachmentError('File attachment object is missing.', 'ATTACHMENT_NOT_FOUND')
        raise AttachmentError('Unable to read file attachment.', 'ATTACHMENT_READ_FAILED', cause=error)
    finally:
        if handle is not None:
            handle.close()
    check_abort(signal)
    if count != ref.get('bytes') or hashed.hexdigest() != digest:
        raise AttachmentError('Stored file attachment failed integrity verification.', 'ATTACHMENT_CORRUPT')

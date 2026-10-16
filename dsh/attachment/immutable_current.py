"""rc.3 immutable publication; Win7 uses NTFS hard links and read-only bits.

Disk operations finish before cancellation unwinds their owning descriptor. The
stream stays pull based and never collects the complete upload in memory.
"""
import asyncio
import hashlib
import os
import uuid

from dsh.attachment.error import AttachmentError


async def disk(function, *args):
    future = asyncio.get_running_loop().run_in_executor(None, function, *args)
    try:
        return await asyncio.shield(future)
    except asyncio.CancelledError:
        # Do not close, unlink, or reuse a descriptor while a worker owns it.
        await asyncio.shield(future)
        raise


def check_abort(signal):
    if signal is not None:
        signal.throwIfAborted()


def sync_directory(path):
    if os.name == 'nt':
        return  # Same NTFS durability boundary as the upstream Windows host.
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def ensure_directory(path, boundary):
    path, boundary = os.path.abspath(path), os.path.abspath(boundary)
    os.makedirs(path, mode=0o700, exist_ok=True)
    os.chmod(path, 0o700)
    while path != boundary:
        parent = os.path.dirname(path)
        sync_directory(parent)
        if parent == path:
            break
        path = parent


def prepare_staging(root):
    boundary = os.path.dirname(os.path.dirname(os.path.abspath(root)))
    volume = os.path.abspath(boundary)
    while os.path.dirname(volume) != volume:
        volume = os.path.dirname(volume)
    # Repeat the durability proof. This also covers removed/recreated homes.
    ensure_directory(boundary, volume)
    staging = os.path.join(root, 'tmp')
    ensure_directory(staging, boundary)
    return boundary, os.path.join(staging, str(uuid.uuid4()))


def remove_temporary(path):
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass


def digest_file(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(65536), b''):
            digest.update(chunk)
    return digest.hexdigest()


def sync_parents(parent, root):
    stop = os.path.abspath(root)
    while parent != stop:
        sync_directory(parent)
        next_parent = os.path.dirname(parent)
        if next_parent == parent:
            break
        parent = next_parent


def link_verified(source, target, digest):
    try:
        os.link(source, target)
    except FileExistsError:
        if digest_file(target) != digest:
            raise AttachmentError('Stored attachment failed integrity verification.', 'ATTACHMENT_CORRUPT')


def publish_staged(root, target, staged):
    try:
        parent = os.path.dirname(target)
        ensure_directory(parent, staged['boundary'])
        link_verified(staged['path'], target, staged['sha256'])
        # NTFS shares read-only attributes across names: unlink staging first.
        os.unlink(staged['path'])
        os.chmod(target, 0o400)
        sync_parents(parent, root)
    except BaseException as error:
        remove_temporary(staged['path'])
        if isinstance(error, (AttachmentError, asyncio.CancelledError)):
            raise
        raise AttachmentError('Unable to persist attachment.', 'ATTACHMENT_WRITE_FAILED', cause=error)


def publish_alias(root, source, target, digest):
    try:
        boundary = os.path.dirname(os.path.dirname(os.path.abspath(root)))
        parent = os.path.dirname(target)
        ensure_directory(parent, boundary)
        link_verified(source, target, digest)
        os.chmod(target, 0o400)
        sync_parents(parent, root)
    except AttachmentError:
        raise
    except Exception as error:
        raise AttachmentError('Unable to persist attachment.', 'ATTACHMENT_WRITE_FAILED', cause=error)


def write_chunk(handle, chunk):
    view = memoryview(chunk)
    while view:
        written = handle.write(view)
        if not written:
            raise OSError('attachment write made no progress')
        view = view[written:]


async def stage(root, data, signal=None):
    boundary, path = await disk(prepare_staging, root)
    handle = None
    try:
        # Opening synchronously avoids losing a newly opened descriptor when
        # cancellation is delivered at the executor await boundary.
        handle = open(path, 'xb', buffering=0)
        digest, count = hashlib.sha256(), 0
        async for chunk in data:
            check_abort(signal)
            await disk(write_chunk, handle, chunk)
            digest.update(chunk)
            count += len(chunk)
        check_abort(signal)
        await disk(os.fsync, handle.fileno())
        check_abort(signal)
        handle.close()
        handle = None
        return dict(path=path, boundary=boundary, sha256=digest.hexdigest(), bytes=count)
    except BaseException as error:
        if handle is not None:
            try:
                handle.close()
            except OSError:
                pass
        await disk(remove_temporary, path)
        if isinstance(error, (AttachmentError, asyncio.CancelledError)) or (signal is not None and signal.aborted):
            raise
        raise AttachmentError('Unable to persist attachment.', 'ATTACHMENT_WRITE_FAILED', cause=error)


async def publish_stream(root, data, target_for, signal=None):
    staged = await stage(root, data, signal)
    try:
        target = target_for(staged['sha256'], staged['bytes'])
    except BaseException:
        await disk(remove_temporary, staged['path'])
        raise
    await disk(publish_staged, root, target, staged)
    return dict(sha256=staged['sha256'], bytes=staged['bytes'])


async def publish_object(root, target, data, digest):
    async def chunks():
        yield data
    staged = await stage(root, chunks())
    if staged['sha256'] != digest:
        await disk(remove_temporary, staged['path'])
        raise AttachmentError('Attachment bytes do not match their publication digest.', 'ATTACHMENT_CORRUPT')
    await disk(publish_staged, root, target, staged)

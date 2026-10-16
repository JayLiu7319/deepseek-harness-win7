"""Kernel-owned cross-process write exclusion, including native Win7 support.

Windows uses a named semaphore without holding a directory/file handle. POSIX
uses flock and verifies the locked inode is still installed at the lock path.
There is no timeout, stale-file deletion or ownership stealing.
"""
import errno
import hashlib
import os

from dsh.session.file_io import filesystem_path
from dsh.session.persistence import SessionAlreadyOwnedError

LEASE_FILENAME = 'session.lock'


def _windows_api():
    import ctypes
    from ctypes import wintypes
    api = ctypes.WinDLL('kernel32', use_last_error=True, winmode=0)
    api.CreateSemaphoreW.argtypes = [ctypes.c_void_p, wintypes.LONG, wintypes.LONG, wintypes.LPCWSTR]
    api.CreateSemaphoreW.restype = wintypes.HANDLE
    api.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    api.WaitForSingleObject.restype = wintypes.DWORD
    api.ReleaseSemaphore.argtypes = [wintypes.HANDLE, wintypes.LONG, ctypes.c_void_p]
    api.ReleaseSemaphore.restype = wintypes.BOOL
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    api.CloseHandle.restype = wintypes.BOOL
    return api


def acquireLockHandleWin32(path):
    import ctypes
    api = _windows_api()
    name = 'Local\\dsh-session-lock-' + hashlib.sha256(os.path.abspath(path).lower().encode('utf-8')).hexdigest()
    handle = api.CreateSemaphoreW(None, 1, 1, name)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    status = api.WaitForSingleObject(handle, 0)
    if status == 0:
        return handle
    failure = ctypes.get_last_error()
    api.CloseHandle(handle)
    if status == 0x102:
        raise BlockingIOError(errno.EBUSY, 'session write lock is busy', path)
    raise ctypes.WinError(failure)


def releaseLockHandleWin32(handle):
    import ctypes
    api = _windows_api()
    released = api.ReleaseSemaphore(handle, 1, None)
    failure = ctypes.get_last_error()
    closed = api.CloseHandle(handle)
    if not released or not closed:
        raise ctypes.WinError(failure if not released else ctypes.get_last_error())


class SessionWriteLease:
    def __init__(self, kind, handle):
        self.kind, self.handle, self.released = kind, handle, False

    @classmethod
    async def acquire(cls, directory, session_id):
        path = os.path.join(directory, LEASE_FILENAME)
        os.makedirs(filesystem_path(directory), mode=0o700, exist_ok=True)
        if os.name == 'nt':
            try:
                return cls('win32', acquireLockHandleWin32(path))
            except BlockingIOError:
                raise SessionAlreadyOwnedError(session_id) from None
        import fcntl
        for attempt in range(3):
            handle = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o666)
            try:
                try:
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError as error:
                    if error.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
                        raise SessionAlreadyOwnedError(session_id) from None
                    raise
                held = os.fstat(handle)
                try:
                    current = os.stat(path)
                except FileNotFoundError:
                    current = None
                if current is not None and current.st_ino == held.st_ino and current.st_dev == held.st_dev:
                    return cls('posix', handle)
            except BaseException:
                os.close(handle)
                raise
            os.close(handle)
        raise SessionAlreadyOwnedError(session_id)

    async def release(self):
        if self.released:
            return
        self.released = True
        if self.kind == 'win32':
            releaseLockHandleWin32(self.handle)
        else:
            os.close(self.handle)

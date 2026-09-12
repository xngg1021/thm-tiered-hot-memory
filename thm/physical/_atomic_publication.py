"""Kernel-protected create-only publication for an owned transport worker.

POSIX publication requires kernel file leases (Darwin additionally requires the
OS file-leases entitlement). Windows uses a handle denying write/delete sharing.
Unsupported filesystems/permissions fail closed; advisory locks are insufficient.
"""
import ctypes as c
import os
from pathlib import Path
import signal
import sys


def _windows_create(path):
    from ctypes import wintypes as w
    import msvcrt
    kernel = c.WinDLL('kernel32', use_last_error=True)
    kernel.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, c.c_void_p,
                                  w.DWORD, w.DWORD, w.HANDLE]
    kernel.CreateFileW.restype = w.HANDLE
    kernel.CloseHandle.argtypes = [w.HANDLE]
    # Read/write/delete authority, share reads only, CREATE_NEW. No other handle
    # can acquire write/delete access until publication and this handle closes.
    handle = kernel.CreateFileW(str(path), 0xC0010000, 1, None, 1, 0x80, None)
    if handle == w.HANDLE(-1).value:
        raise c.WinError(c.get_last_error())
    try:
        return msvcrt.open_osfhandle(handle, os.O_RDWR | os.O_BINARY)
    except BaseException:
        kernel.CloseHandle(handle)
        raise


def _publish_fd(fd, destination, directory_fd, *, destination_fd=None):
    """Publish the protected descriptor, never resolve the mutable source name."""
    if os.name == 'nt':
        from ctypes import wintypes as w
        import msvcrt
        name = str(Path(destination).absolute()); encoded_name = name.encode('utf-16-le')
        class Rename(c.Structure):
            _fields_ = [('replace', c.c_ubyte), ('root', w.HANDLE),
                        ('length', w.DWORD), ('name', w.WCHAR * (len(encoded_name)//2 + 1))]
        info = Rename(); info.length = len(encoded_name); info.name = name
        kernel = c.WinDLL('kernel32', use_last_error=True)
        kernel.SetFileInformationByHandle.argtypes = [w.HANDLE, c.c_int, c.c_void_p, w.DWORD]
        if not kernel.SetFileInformationByHandle(w.HANDLE(msvcrt.get_osfhandle(fd)), 3,
                                                 c.byref(info), c.sizeof(info)):
            error = c.get_last_error()
            if error in (80, 183):
                raise FileExistsError(str(destination))
            raise c.WinError(error)
    elif sys.platform.startswith('linux'):
        # Passing dir_fd forces linkat(AT_SYMLINK_FOLLOW); /proc/self/fd resolves
        # the already-open protected inode even if its old name was replaced.
        os.link('/proc/self/fd/' + str(fd), Path(destination).name if destination_fd is not None else destination,
                src_dir_fd=directory_fd, dst_dir_fd=destination_fd, follow_symlinks=True)
    elif sys.platform == 'darwin':
        libc = c.CDLL(None, use_errno=True)
        clone = libc.fclonefileat
        clone.argtypes = [c.c_int, c.c_int, c.c_char_p, c.c_uint32]
        clone.restype = c.c_int
        if clone(fd, destination_fd if destination_fd is not None else -2,
                 os.fsencode(Path(destination).name if destination_fd is not None else destination), 0):
            error = c.get_errno()
            if error == 17:
                raise FileExistsError(str(destination))
            raise OSError(error, 'protected descriptor clone unavailable')
    else:
        raise OSError('protected mounted publication unavailable on this platform')


def publish_bytes(path, data, destination, directory_fd, *, destination_fd=None):
    """Validate and publish under a retained kernel exclusion boundary.

StorageBackend bounds the whole mounted commit callback to one second. Linux
lease conflicts terminate the owned worker through SIGIO before a writer gains
access. Darwin's kernel lease-break interval is 60 seconds, above that parent
deadline; ordinary Python processes lacking its entitlement fail before publish.
"""
    if os.name == 'nt':
        fd = _windows_create(path)
    else:
        fd = os.open('payload', os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=directory_fd)
    with os.fdopen(fd, 'w+b') as stream:
        if stream.write(data) != len(data):
            raise OSError('short storage publication write')
        stream.flush(); os.fsync(fd)
        if os.name == 'posix':
            import fcntl
            if sys.platform.startswith('linux'):
                if signal.getsignal(signal.SIGIO) != signal.SIG_DFL or signal.SIGIO in signal.pthread_sigmask(signal.SIG_BLOCK, []):
                    raise OSError('protected publication requires default unblocked SIGIO in owned worker')
                command = fcntl.F_SETLEASE
            elif sys.platform == 'darwin':
                command = 106  # public XNU F_SETLEASE; entitlement enforced by OS
            else:
                raise OSError('protected mounted publication unavailable')
            try:
                if sys.platform.startswith('linux'):
                    fcntl.fcntl(fd, fcntl.F_SETOWN, os.getpid())
                fcntl.fcntl(fd, command, fcntl.F_WRLCK)
            except OSError as exc:
                raise OSError('kernel-protected mounted publication unavailable') from exc
        stream.seek(0)
        if stream.read(len(data) + 1) != data:
            raise ValueError('owned publication changed')
        _publish_fd(fd, destination, directory_fd, destination_fd=destination_fd)

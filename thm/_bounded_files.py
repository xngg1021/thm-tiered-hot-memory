"""Open and validate the same non-link descriptor before bounded file reads."""
from contextlib import contextmanager
import os
import stat


def _open_fd(path, *, directory=False, dir_fd=None):
    if os.name == 'nt':
        import ctypes as c
        from ctypes import wintypes as w
        import msvcrt
        kernel = c.WinDLL('kernel32', use_last_error=True)
        kernel.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, c.c_void_p,
                                      w.DWORD, w.DWORD, w.HANDLE]
        kernel.CreateFileW.restype = w.HANDLE
        kernel.CloseHandle.argtypes = [w.HANDLE]
        kernel.GetFileType.argtypes = [w.HANDLE]
        class AttributeTag(c.Structure):
            _fields_ = [('attributes', w.DWORD), ('tag', w.DWORD)]
        kernel.GetFileInformationByHandleEx.argtypes = [w.HANDLE, c.c_int, c.c_void_p, w.DWORD]
        kernel.GetFileInformationByHandleEx.restype = w.BOOL
        # OPEN_REPARSE_POINT | BACKUP_SEMANTICS; share read/write, never delete.
        handle = kernel.CreateFileW(os.fspath(path), 0x80000000, 3, None, 3,
                                    0x00200000 | 0x02000000, None)
        if handle == w.HANDLE(-1).value:
            raise OSError(c.get_last_error(), 'cannot open validated artifact')
        try:
            if kernel.GetFileType(handle) != 1:  # FILE_TYPE_DISK
                raise ValueError('regular disk artifact required')
            tag = AttributeTag()
            if not kernel.GetFileInformationByHandleEx(handle, 9, c.byref(tag), c.sizeof(tag)) or tag.attributes & 0x400:
                raise ValueError('non-reparse artifact required')
            fd = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
        except BaseException:
            kernel.CloseHandle(handle)
            raise
        return fd
    else:
        flags = os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW
        if directory:
            flags |= os.O_DIRECTORY
        return os.open(path, flags, dir_fd=dir_fd)


@contextmanager
def validated_descriptor(path, *, directory=False, expected=None, dir_fd=None):
    """Reject links/special files, including replacements between stat and open.

    POSIX uses nonblocking/no-follow opens so a substituted FIFO cannot hang.
    Windows opens the reparse point itself and denies delete sharing while the
    handle is owned; callers never reopen an already validated file pathname.
    """
    fd = _open_fd(path, directory=directory, dir_fd=dir_fd)
    try:
        info = os.fstat(fd)
        wanted = stat.S_ISDIR if directory else stat.S_ISREG
        if not wanted(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise ValueError('non-link regular artifact required')
        if expected is not None and (info.st_dev, info.st_ino, info.st_size,
                                     info.st_mtime_ns) != (
                expected.st_dev, expected.st_ino, expected.st_size, expected.st_mtime_ns):
            raise ValueError('artifact changed before descriptor validation')
        yield fd, info
    finally:
        os.close(fd)


def bounded_file_bytes(path, maximum):
    with validated_descriptor(path) as (fd, info):
        if info.st_size > maximum:
            raise ValueError('bounded memory snapshot required')
        chunks, length = [], 0
        while True:
            block = os.read(fd, min(1024 * 1024, maximum - length + 1))
            if not block:
                break
            length += len(block)
            if length > maximum:
                raise ValueError('bounded memory snapshot required')
            chunks.append(block)
        if length != info.st_size:
            raise ValueError('snapshot changed while reading')
        return b''.join(chunks)


@contextmanager
def open_regular(path, *, maximum_bytes, expected_identity=None):
    with validated_descriptor(path) as (fd, info):
        if info.st_size > maximum_bytes:
            raise ValueError('bounded regular file required')
        if expected_identity is not None and (info.st_dev, info.st_ino) != expected_identity:
            raise ValueError('file identity changed before open')
        with os.fdopen(os.dup(fd), 'rb') as stream:
            yield stream, info


def read_regular(path, *, maximum_bytes):
    return bounded_file_bytes(path, maximum_bytes)

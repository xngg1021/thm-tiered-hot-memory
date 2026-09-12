"""Descriptor-bound, non-following regular-file reads with explicit byte ceilings."""
from contextlib import contextmanager
import os
import stat


def _open_fd(path):
    if os.name != 'nt':
        return os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    import ctypes as c
    from ctypes import wintypes as w
    import msvcrt
    class AttributeTag(c.Structure):
        _fields_=[('attributes',w.DWORD),('tag',w.DWORD)]
    kernel=c.WinDLL('kernel32',use_last_error=True)
    kernel.CreateFileW.argtypes=[w.LPCWSTR,w.DWORD,w.DWORD,c.c_void_p,w.DWORD,w.DWORD,w.HANDLE]
    kernel.CreateFileW.restype=w.HANDLE
    kernel.GetFileInformationByHandleEx.argtypes=[w.HANDLE,c.c_int,c.c_void_p,w.DWORD]
    kernel.GetFileInformationByHandleEx.restype=w.BOOL
    kernel.GetFileType.argtypes=[w.HANDLE];kernel.GetFileType.restype=w.DWORD
    kernel.CloseHandle.argtypes=[w.HANDLE]
    handle=kernel.CreateFileW(str(path),0x80000000,7,None,3,0x00200000,None)
    if handle==c.c_void_p(-1).value:raise OSError(c.get_last_error(),'cannot open regular file')
    try:
        tag=AttributeTag()
        if kernel.GetFileType(handle)!=1 or not kernel.GetFileInformationByHandleEx(handle,9,c.byref(tag),c.sizeof(tag)) or tag.attributes & 0x400:
            raise ValueError('regular non-reparse file required')
        fd=msvcrt.open_osfhandle(int(handle),os.O_RDONLY|os.O_BINARY)
        handle=None
        return fd
    finally:
        if handle is not None:kernel.CloseHandle(handle)


@contextmanager
def open_regular(path, *, maximum_bytes, expected_identity=None):
    fd=_open_fd(path)
    try:
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size>maximum_bytes:
            raise ValueError('bounded regular file required')
        if expected_identity is not None and (info.st_dev,info.st_ino)!=expected_identity:
            raise ValueError('file identity changed before open')
        stream=os.fdopen(fd,'rb');fd=None
        with stream:yield stream,info
    finally:
        if fd is not None:os.close(fd)


def read_regular(path, *, maximum_bytes):
    with open_regular(path,maximum_bytes=maximum_bytes) as (stream,info):
        data=stream.read(maximum_bytes+1)
        if len(data)>maximum_bytes:raise ValueError('file grew beyond byte bound')
        return data

"""Install descendant restrictions inside an owned worker before user callbacks.

Linux descendants inherit a filter that prevents session/group and namespace
escape. Darwin workers forbid process creation through Seatbelt. Windows workers
are released by the parent only after attachment to a no-breakaway Job Object.
This is process lifetime containment, not a general filesystem/network sandbox.
"""
import ctypes as c
import errno
import os
import platform
import sys


def install_descendant_containment():
    if os.name == 'nt':
        return 'windows-job-no-breakaway'
    if sys.platform.startswith('linux'):
        _linux_filter()
        return 'linux-inherited-seccomp-pgid'
    if sys.platform == 'darwin':
        _darwin_no_fork()
        return 'darwin-seatbelt-no-fork'
    raise OSError('owned descendant containment unavailable')


def _linux_filter():
    # Public Linux syscall ABI: arch/{x86,arm64}/include/uapi/asm.
    abi = {
        'x86_64': (0xc000003e, 56, 109, 112, 272, 308),
        'aarch64': (0xc00000b7, 220, 154, 157, 97, 268),
    }.get(platform.machine().lower())
    if abi is None:
        raise OSError('Linux containment ABI unavailable')
    arch, clone, setpgid, setsid, unshare, setns = abi
    allow, deny = 0x7fff0000, 0x00050000 | errno.EPERM
    unavailable = 0x00050000 | errno.ENOSYS
    instructions = [(0x20, 0, 0, 4), (0x15, 1, 0, arch), (0x06, 0, 0, 0x80000000),
                    (0x20, 0, 0, 0)]
    if arch == 0xc000003e:
        instructions += [(0x45, 0, 1, 0x40000000), (0x06, 0, 0, unavailable)]
    for syscall in (setpgid, setsid, unshare, setns):
        instructions += [(0x15, 0, 1, syscall), (0x06, 0, 0, deny)]
    # clone3 has pointer arguments that classic BPF cannot inspect. ENOSYS lets
    # ordinary libc thread/process creation fall back to inspectable clone.
    instructions += [(0x15, 0, 1, 435), (0x06, 0, 0, unavailable),
                     (0x15, 0, 3, clone), (0x20, 0, 0, 16),
                     (0x45, 0, 1, 0x7e020000), (0x06, 0, 0, deny),
                     (0x06, 0, 0, allow)]
    class Filter(c.Structure):
        _fields_ = [('code', c.c_ushort), ('jt', c.c_ubyte), ('jf', c.c_ubyte), ('k', c.c_uint)]
    class Program(c.Structure):
        _fields_ = [('length', c.c_ushort), ('filters', c.POINTER(Filter))]
    filters = (Filter * len(instructions))(*(Filter(*row) for row in instructions))
    program = Program(len(filters), filters)
    libc = c.CDLL(None, use_errno=True)
    libc.prctl.argtypes = [c.c_int, c.c_ulong, c.c_ulong, c.c_ulong, c.c_ulong]
    libc.prctl.restype = c.c_int
    if libc.prctl(38, 1, 0, 0, 0) or libc.prctl(22, 2, c.addressof(program), 0, 0):
        raise OSError(c.get_errno(), 'Linux descendant containment unavailable')


def _darwin_no_fork():
    library = c.CDLL('/usr/lib/libsandbox.dylib', use_errno=True)
    library.sandbox_init.argtypes = [c.c_char_p, c.c_uint64, c.POINTER(c.c_char_p)]
    library.sandbox_init.restype = c.c_int
    library.sandbox_free_error.argtypes = [c.c_char_p]
    error = c.c_char_p()
    result = library.sandbox_init(b'(version 1)(allow default)(deny process-fork)', 0, c.byref(error))
    try:
        if result:
            raise OSError('Darwin descendant containment unavailable')
    finally:
        if error:
            library.sandbox_free_error(error)

"""Pure Python bounded I/O worker; no optional SDK or model dependency."""
import os
import struct
import sys
from thm._bounded_files import bounded_file_bytes


def main():
    header=sys.stdin.buffer.read(4)
    if len(header)!=4:return 2
    length=struct.unpack('<I',header)[0]
    if not 2<=length<=4098:return 2
    request=sys.stdin.buffer.read(length)
    if len(request)!=length or request[:2]!=bytes((1,1)):return 2
    from thm._process_containment import install_descendant_containment
    install_descendant_containment()
    try:
        data=bounded_file_bytes(os.fsdecode(request[2:]),1048576)
        status=0
    except Exception as exc:
        status=1;data=(type(exc).__name__+':'+str(exc)).encode()[:1024]
    sys.stdout.buffer.write(struct.pack('<I',len(data)+1)+bytes((status,))+data)
    return 0


if __name__=='__main__':raise SystemExit(main())

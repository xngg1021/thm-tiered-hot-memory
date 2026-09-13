/* Public native async I/O. Runs only inside the deadline-owned SysCore process.
 * Cancellation terminates/reaps that process before caller-owned buffers expire.
 * No direct/zero-copy claims; each request owns all ring/port/queue resources. */
#define _GNU_SOURCE
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#ifdef _WIN32
#include <windows.h>
int64_t thm_native_read(const char *path, unsigned char *data, size_t capacity) {
    WCHAR name[4096]; OVERLAPPED ov; DWORD bytes=0; ULONG_PTR key=0; OVERLAPPED *done=NULL;
    memset(&ov,0,sizeof(ov));
    if (!MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,path,-1,name,4096)) return -1;
    HANDLE file=CreateFileW(name,GENERIC_READ,FILE_SHARE_READ,NULL,OPEN_EXISTING,FILE_FLAG_OVERLAPPED,NULL);
    if(file==INVALID_HANDLE_VALUE) return -2;
    HANDLE port=CreateIoCompletionPort(file,NULL,1,1);
    if(!port) { CloseHandle(file); return -3; }
    BOOL started=ReadFile(file,data,(DWORD)capacity,NULL,&ov);
    if(!started && GetLastError()!=ERROR_IO_PENDING) { CloseHandle(file); CloseHandle(port); return -4; }
    BOOL ok=GetQueuedCompletionStatus(port,&bytes,&key,&done,INFINITE);
    CloseHandle(file); CloseHandle(port);
    return ok && done==&ov ? (int64_t)bytes : -5;
}
#elif defined(__linux__)
#include <errno.h>
#include <fcntl.h>
#include <linux/io_uring.h>
#include <stdatomic.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <unistd.h>
int64_t thm_native_read(const char *path, unsigned char *data, size_t capacity) {
    struct io_uring_params p; memset(&p,0,sizeof(p));
    int file=open(path,O_RDONLY|O_CLOEXEC|O_NONBLOCK); if(file<0) return -errno;
    struct stat st;
    if(fstat(file,&st) || !S_ISREG(st.st_mode)) { close(file); return -22; }
    int ring=(int)syscall(__NR_io_uring_setup,2,&p);
    if(ring<0) { int e=errno; close(file); return -e; }
    size_t sqsize=p.sq_off.array+p.sq_entries*sizeof(unsigned);
    size_t cqsize=p.cq_off.cqes+p.cq_entries*sizeof(struct io_uring_cqe);
    int single=(p.features&IORING_FEAT_SINGLE_MMAP)!=0;
    if(single && cqsize>sqsize) sqsize=cqsize;
    void *sq=mmap(NULL,sqsize,PROT_READ|PROT_WRITE,MAP_SHARED,ring,IORING_OFF_SQ_RING);
    void *cq=single?sq:mmap(NULL,cqsize,PROT_READ|PROT_WRITE,MAP_SHARED,ring,IORING_OFF_CQ_RING);
    struct io_uring_sqe *entries=mmap(NULL,p.sq_entries*sizeof(*entries),PROT_READ|PROT_WRITE,MAP_SHARED,ring,IORING_OFF_SQES);
    int64_t result=-12;
    if(sq!=MAP_FAILED && cq!=MAP_FAILED && entries!=MAP_FAILED) {
        unsigned *array=(unsigned *)((char *)sq+p.sq_off.array);
        _Atomic unsigned *tail=(_Atomic unsigned *)((char *)sq+p.sq_off.tail);
        unsigned *mask=(unsigned *)((char *)sq+p.sq_off.ring_mask);
        unsigned position=atomic_load_explicit(tail,memory_order_relaxed)&*mask;
        struct io_uring_sqe *entry=&entries[position]; memset(entry,0,sizeof(*entry));
        entry->opcode=IORING_OP_READ; entry->fd=file; entry->addr=(uintptr_t)data;
        entry->len=(unsigned)capacity; entry->off=0; entry->user_data=1;
        array[position]=position;
        atomic_fetch_add_explicit(tail,1,memory_order_release);
        int rc;
        do { rc=(int)syscall(__NR_io_uring_enter,ring,1,1,IORING_ENTER_GETEVENTS,NULL,0); } while(rc<0 && errno==EINTR);
        if(rc>=0) {
            _Atomic unsigned *head=(_Atomic unsigned *)((char *)cq+p.cq_off.head);
            _Atomic unsigned *ctail=(_Atomic unsigned *)((char *)cq+p.cq_off.tail);
            unsigned h=atomic_load_explicit(head,memory_order_relaxed);
            unsigned t=atomic_load_explicit(ctail,memory_order_acquire);
            unsigned cmask=*(unsigned *)((char *)cq+p.cq_off.ring_mask);
            struct io_uring_cqe *completion=(struct io_uring_cqe *)((char *)cq+p.cq_off.cqes);
            if(t!=h && completion[h&cmask].user_data==1) result=completion[h&cmask].res;
            atomic_store_explicit(head,h+1,memory_order_release);
        } else result=-errno;
    }
    close(ring); close(file);
    if(entries!=MAP_FAILED) munmap(entries,p.sq_entries*sizeof(*entries));
    if(cq!=MAP_FAILED && !single) munmap(cq,cqsize);
    if(sq!=MAP_FAILED) munmap(sq,sqsize);
    return result;
}
#elif defined(__APPLE__)
#include <aio.h>
#include <errno.h>
#include <fcntl.h>
#include <sys/event.h>
#include <sys/stat.h>
#include <unistd.h>
int64_t thm_native_read(const char *path, unsigned char *data, size_t capacity) {
    int file=open(path,O_RDONLY|O_NONBLOCK); if(file<0) return -errno;
    struct stat st; if(fstat(file,&st) || !S_ISREG(st.st_mode)) {close(file); return -22;}
    struct aiocb cb; memset(&cb,0,sizeof(cb)); cb.aio_fildes=file; cb.aio_buf=data; cb.aio_nbytes=capacity;
    int queue=kqueue(); if(queue<0) {close(file); return -errno;}
    cb.aio_sigevent.sigev_notify=SIGEV_KEVENT; cb.aio_sigevent.sigev_signo=queue;
    if(aio_read(&cb)) {int e=errno; close(queue); close(file); return -e;}
    struct kevent event; int rc;
    do {rc=kevent(queue,NULL,0,&event,1,NULL);} while(rc<0 && errno==EINTR);
    /* Never return while the kernel owns the request buffer. Parent deadline
       kills the process if a failed event queue cannot retire the request. */
    const struct aiocb *list[1]={&cb};
    while(aio_error(&cb)==EINPROGRESS) aio_suspend(list,1,NULL);
    int64_t result=(int64_t)aio_return(&cb); close(queue); close(file); return result;
}
#else
int64_t thm_native_read(const char *path, unsigned char *data, size_t capacity) {
    (void)path; (void)data; (void)capacity; return -38;
}
#endif

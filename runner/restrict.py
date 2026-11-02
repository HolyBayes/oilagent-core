"""Deny networking and namespace/process escape before loading candidate Python."""

import ctypes
import errno


def restrict_syscalls():
    lib = ctypes.CDLL("libseccomp.so.2", use_errno=True)
    lib.seccomp_init.restype = ctypes.c_void_p
    lib.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
    lib.seccomp_rule_add.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_uint]
    lib.seccomp_load.argtypes = [ctypes.c_void_p]
    lib.seccomp_release.argtypes = [ctypes.c_void_p]
    context = lib.seccomp_init(0x7FFF0000)
    if not context:
        raise RuntimeError("Cannot create syscall filter")
    try:
        for name in [
            "socket",
            "socketpair",
            "connect",
            "bind",
            "listen",
            "accept",
            "accept4",
            "sendto",
            "sendmsg",
            "sendmmsg",
            "recvfrom",
            "recvmsg",
            "recvmmsg",
            "ptrace",
            "process_vm_readv",
            "process_vm_writev",
            "pidfd_open",
            "pidfd_getfd",
            "unshare",
            "setns",
            "setsid",
            "setpgid",
            "mount",
            "umount2",
            "pivot_root",
            "open_by_handle_at",
            "bpf",
            "io_uring_setup",
            "io_uring_enter",
            "io_uring_register",
        ]:
            number = lib.seccomp_syscall_resolve_name(name.encode())
            if (
                number >= 0
                and lib.seccomp_rule_add(context, 0x00050000 | errno.EPERM, number, 0) != 0
            ):
                raise RuntimeError("Cannot install syscall rule")
        if lib.seccomp_load(context) != 0:
            raise RuntimeError("Cannot load syscall filter")
    finally:
        lib.seccomp_release(context)

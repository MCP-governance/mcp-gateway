"""Windows OpenSSL verification and a kill-on-close job, with no third party Python modules."""
import base64
import ctypes as C
from ctypes import wintypes as W
from pathlib import Path
import subprocess
import sys
import time


def signed(body, signature, pem):
    der = base64.b64decode(''.join(line for line in pem.splitlines() if not line.startswith('---')), validate=True)
    if len(der) != 44 or der[:12] != bytes.fromhex('302a300506032b6570032100'):
        return False
    sig = base64.b64decode(signature, validate=True)
    if len(sig) != 64:
        return False
    dll = C.CDLL(str(Path(sys.executable).with_name('libcrypto-3.dll')))
    dll.EVP_PKEY_new_raw_public_key_ex.argtypes = [C.c_void_p, C.c_char_p, C.c_char_p, C.c_char_p, C.c_size_t]
    dll.EVP_PKEY_new_raw_public_key_ex.restype = C.c_void_p
    dll.EVP_MD_CTX_new.restype = C.c_void_p
    dll.EVP_DigestVerifyInit.argtypes = [C.c_void_p, C.c_void_p, C.c_void_p, C.c_void_p, C.c_void_p]
    dll.EVP_DigestVerify.argtypes = [C.c_void_p, C.c_char_p, C.c_size_t, C.c_char_p, C.c_size_t]
    dll.EVP_MD_CTX_free.argtypes = [C.c_void_p]
    dll.EVP_PKEY_free.argtypes = [C.c_void_p]
    key = dll.EVP_PKEY_new_raw_public_key_ex(None, b'ED25519', None, der[12:], 32)
    context = dll.EVP_MD_CTX_new()
    try:
        return bool(key and context and dll.EVP_DigestVerifyInit(context, None, None, None, key) == 1
                    and dll.EVP_DigestVerify(context, sig, len(sig), body, len(body)) == 1)
    finally:
        if context:
            dll.EVP_MD_CTX_free(context)
        if key:
            dll.EVP_PKEY_free(key)


class BasicLimits(C.Structure):
    _fields_ = [('ProcessTime', C.c_longlong), ('JobTime', C.c_longlong), ('Flags', W.DWORD),
                ('MinWorking', C.c_size_t), ('MaxWorking', C.c_size_t), ('ActiveLimit', W.DWORD),
                ('Affinity', C.c_size_t), ('Priority', W.DWORD), ('Scheduling', W.DWORD)]


class IO(C.Structure):
    _fields_ = [(name, C.c_ulonglong) for name in ('ReadOps', 'WriteOps', 'OtherOps', 'ReadBytes', 'WriteBytes', 'OtherBytes')]


class ExtendedLimits(C.Structure):
    _fields_ = [('Basic', BasicLimits), ('IO', IO), ('ProcessMemory', C.c_size_t),
                ('JobMemory', C.c_size_t), ('PeakProcess', C.c_size_t), ('PeakJob', C.c_size_t)]


class Accounting(C.Structure):
    _fields_ = [('User', C.c_longlong), ('Kernel', C.c_longlong), ('PeriodUser', C.c_longlong),
                ('PeriodKernel', C.c_longlong), ('Faults', W.DWORD), ('Total', W.DWORD),
                ('Active', W.DWORD), ('Terminated', W.DWORD)]


class Job:
    def __init__(self, name=None):
        self.kernel = C.WinDLL('kernel32', use_last_error=True)
        self.kernel.CreateJobObjectW.argtypes = [C.c_void_p, W.LPCWSTR]
        self.kernel.CreateJobObjectW.restype = W.HANDLE
        for api_name, args in [('SetInformationJobObject', [W.HANDLE, C.c_int, C.c_void_p, W.DWORD]),
                           ('AssignProcessToJobObject', [W.HANDLE, W.HANDLE]),
                           ('TerminateJobObject', [W.HANDLE, W.UINT]),
                           ('QueryInformationJobObject', [W.HANDLE, C.c_int, C.c_void_p, W.DWORD, C.c_void_p]),
                           ('CloseHandle', [W.HANDLE])]:
            getattr(self.kernel, api_name).argtypes = args
        C.set_last_error(0)
        self.handle = self.kernel.CreateJobObjectW(None, name)
        if self.handle and C.get_last_error() == 183:
            self.kernel.CloseHandle(self.handle)
            raise OSError('Windows 작업 개체 이름 충돌')
        limits = ExtendedLimits()
        limits.Basic.Flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.handle or not self.kernel.SetInformationJobObject(self.handle, 9, C.byref(limits), C.sizeof(limits)):
            if self.handle:
                self.kernel.CloseHandle(self.handle)
            raise OSError('Windows 작업 개체 생성 실패')

    def start(self, args, **kwargs):
        process = subprocess.Popen(args, creationflags=0x4 | subprocess.CREATE_NO_WINDOW, **kwargs)
        try:
            if not self.kernel.AssignProcessToJobObject(self.handle, int(process._handle)):
                raise OSError('Windows 프로세스 결속 실패')
            native = C.WinDLL('ntdll')
            native.NtResumeProcess.argtypes = [W.HANDLE]
            if native.NtResumeProcess(int(process._handle)) != 0:
                raise OSError('Windows 프로세스 시작 실패')
            return process
        except BaseException:
            process.kill(); process.wait(timeout=3)
            self.close()
            raise

    @classmethod
    def recover(cls, name):
        instance = cls()
        if not instance.close():
            raise OSError('Windows 복구 작업 개체 초기화 실패')
        instance.kernel.OpenJobObjectW.argtypes = [W.DWORD, W.BOOL, W.LPCWSTR]
        instance.kernel.OpenJobObjectW.restype = W.HANDLE
        instance.handle = instance.kernel.OpenJobObjectW(0x8 | 0x4, False, name)
        if not instance.handle:
            if C.get_last_error() == 2:
                return True
            raise OSError('Windows 작업 개체 복구 실패')
        return instance.close()

    def close(self):
        if self.handle is None:
            return True
        if not self.kernel.TerminateJobObject(self.handle, 1):
            return False
        end = time.monotonic() + 3
        while time.monotonic() < end:
            info = Accounting()
            if not self.kernel.QueryInformationJobObject(self.handle, 1, C.byref(info), C.sizeof(info), None):
                return False
            if info.Active == 0:
                self.kernel.CloseHandle(self.handle)
                self.handle = None
                return True
            time.sleep(.02)
        return False

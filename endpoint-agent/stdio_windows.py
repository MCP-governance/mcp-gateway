"""Windows OpenSSL verification and a kill-on-close job, with no third party Python modules."""
import base64
import ctypes as C
from ctypes import wintypes as W
from pathlib import Path
import subprocess
import sys
import time
import os
import re


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


class SessionInfo(C.Structure):
    _fields_ = [('id', W.DWORD), ('station', W.LPWSTR), ('state', C.c_int)]


class Startup(C.Structure):
    _fields_ = [('cb', W.DWORD), ('reserved', W.LPWSTR), ('desktop', W.LPWSTR), ('title', W.LPWSTR),
                *[(n, W.DWORD) for n in ('x', 'y', 'xs', 'ys', 'xc', 'yc', 'fill', 'flags')],
                ('show', W.WORD), ('reserved_size', W.WORD), ('reserved_bytes', C.c_void_p),
                ('stdin', W.HANDLE), ('stdout', W.HANDLE), ('stderr', W.HANDLE)]


class StartupEx(C.Structure):
    _fields_ = [('startup', Startup), ('attributes', C.c_void_p)]


class ProcessInfo(C.Structure):
    _fields_ = [('process', W.HANDLE), ('thread', W.HANDLE), ('pid', W.DWORD), ('tid', W.DWORD)]


def user_token(sid, kernel, security, sessions):
    if not re.fullmatch(r'S-1-5-21-\d+-\d+-\d+-\d+', sid or ''):
        raise ValueError('직원 SID가 없습니다')
    entries, count = C.POINTER(SessionInfo)(), W.DWORD()
    if not sessions.WTSEnumerateSessionsW(None, 0, 1, C.byref(entries), C.byref(count)):
        raise OSError('직원 로그온 세션 조회 실패')
    try:
        for entry in entries[:count.value]:
            token = W.HANDLE()
            if not sessions.WTSQueryUserToken(entry.id, C.byref(token)):
                continue
            try:
                size = W.DWORD()
                security.GetTokenInformation(token, 1, None, 0, C.byref(size))
                if not size.value:
                    raise OSError('로그온 토큰 신원 확인 실패')
                data = C.create_string_buffer(size.value)
                if not security.GetTokenInformation(token, 1, data, size, C.byref(size)):
                    raise OSError('로그온 토큰 신원 확인 실패')
                text = W.LPWSTR()
                if not security.ConvertSidToStringSidW(C.cast(data, C.POINTER(C.c_void_p))[0], C.byref(text)):
                    raise OSError('로그온 토큰 SID 확인 실패')
                try:
                    matches = text.value == sid
                finally:
                    kernel.LocalFree(text)
                if matches:
                    primary = W.HANDLE()
                    if not security.DuplicateTokenEx(token, 0x02000000, None, 2, 1, C.byref(primary)):
                        raise OSError('직원 실행 토큰 복제 실패')
                    return primary
            finally:
                kernel.CloseHandle(token)
    finally:
        sessions.WTSFreeMemory(entries)
    raise OSError('등록된 직원의 로그온 세션이 없습니다')


class UserProcess:
    def __init__(self, kernel, handle, pid, streams):
        self.kernel, self.handle, self.pid = kernel, handle, pid
        self.stdin, self.stdout, self.stderr = streams
        self.returncode = None

    def poll(self):
        state = self.kernel.WaitForSingleObject(self.handle, 0) if self.returncode is None else 0
        if state == 0xFFFFFFFF:
            raise OSError('직원 프로세스 상태 확인 실패')
        if self.returncode is None and state == 0:
            code = W.DWORD()
            if not self.kernel.GetExitCodeProcess(self.handle, C.byref(code)):
                raise OSError('직원 프로세스 종료 확인 실패')
            self.returncode = code.value
            self.kernel.CloseHandle(self.handle)
            self.handle = None
        return self.returncode

    def wait(self, timeout=None):
        end = None if timeout is None else time.monotonic() + timeout
        while self.poll() is None:
            if end is not None and time.monotonic() >= end:
                raise subprocess.TimeoutExpired('직원 프로세스', timeout)
            time.sleep(.01)
        return self.returncode

    def kill(self):
        if self.poll() is None and not self.kernel.TerminateProcess(self.handle, 1):
            raise OSError('직원 프로세스 정지 실패')

    def __del__(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)


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

    def start(self, args, *, sid, cwd, env, **kwargs):
        import msvcrt
        kernel = self.kernel
        security = C.WinDLL('advapi32', use_last_error=True)
        sessions = C.WinDLL('wtsapi32', use_last_error=True)
        for dll, name, types, result in (
            (sessions, 'WTSEnumerateSessionsW', [W.HANDLE, W.DWORD, W.DWORD, C.c_void_p, C.c_void_p], W.BOOL),
            (sessions, 'WTSQueryUserToken', [W.ULONG, C.c_void_p], W.BOOL),
            (sessions, 'WTSFreeMemory', [C.c_void_p], None),
            (security, 'GetTokenInformation', [W.HANDLE, C.c_int, C.c_void_p, W.DWORD, C.c_void_p], W.BOOL),
            (security, 'ConvertSidToStringSidW', [C.c_void_p, C.c_void_p], W.BOOL),
            (security, 'DuplicateTokenEx', [W.HANDLE, W.DWORD, C.c_void_p, C.c_int, C.c_int, C.c_void_p], W.BOOL),
            (security, 'CreateProcessAsUserW', [W.HANDLE, W.LPCWSTR, W.LPWSTR, C.c_void_p, C.c_void_p,
                                             W.BOOL, W.DWORD, C.c_void_p, W.LPCWSTR, C.c_void_p, C.c_void_p], W.BOOL),
            (kernel, 'LocalFree', [C.c_void_p], C.c_void_p),
            (kernel, 'InitializeProcThreadAttributeList', [C.c_void_p, W.DWORD, W.DWORD, C.c_void_p], W.BOOL),
            (kernel, 'UpdateProcThreadAttribute', [C.c_void_p, W.DWORD, C.c_size_t, C.c_void_p,
                                                C.c_size_t, C.c_void_p, C.c_void_p], W.BOOL),
            (kernel, 'DeleteProcThreadAttributeList', [C.c_void_p], None),
            (kernel, 'ResumeThread', [W.HANDLE], W.DWORD),
            (kernel, 'TerminateProcess', [W.HANDLE, W.UINT], W.BOOL),
            (kernel, 'WaitForSingleObject', [W.HANDLE, W.DWORD], W.DWORD),
            (kernel, 'GetExitCodeProcess', [W.HANDLE, C.c_void_p], W.BOOL),
        ):
            function = getattr(dll, name)
            function.argtypes, function.restype = types, result
        token, descriptors, streams, attributes = None, [], [], None
        initialized, created = False, False
        info = ProcessInfo()
        try:
            token = user_token(sid, kernel, security, sessions)
            child = []
            for index in range(3):
                read, write = os.pipe()
                descriptors.extend((read, write))
                own, inherited = (write, read) if index == 0 else (read, write)
                os.set_inheritable(inherited, True)
                child.append(msvcrt.get_osfhandle(inherited))
                streams.append(os.fdopen(own, 'wb' if index == 0 else 'rb', buffering=0))
                descriptors.remove(own)
            size = C.c_size_t()
            kernel.InitializeProcThreadAttributeList(None, 1, 0, C.byref(size))
            if not size.value:
                raise OSError('표준 입출력 핸들 목록 크기 확인 실패')
            attributes = C.create_string_buffer(size.value)
            if not kernel.InitializeProcThreadAttributeList(attributes, 1, 0, C.byref(size)):
                raise OSError('표준 입출력 핸들 목록 초기화 실패')
            initialized = True
            handles = (W.HANDLE * 3)(*child)
            if not kernel.UpdateProcThreadAttribute(attributes, 0, 0x20002, handles, C.sizeof(handles), None, None):
                raise OSError('표준 입출력 핸들 상속 제한 실패')
            startup = StartupEx()
            startup.startup.cb = C.sizeof(startup)
            startup.startup.flags = 0x100
            startup.startup.desktop = 'winsta0\\default'
            startup.startup.stdin, startup.startup.stdout, startup.startup.stderr = child
            startup.attributes = C.cast(attributes, C.c_void_p)
            environment = C.create_unicode_buffer('\0'.join(f'{k}={v}' for k, v in sorted(env.items())) + '\0\0')
            command = C.create_unicode_buffer(subprocess.list2cmdline([str(a) for a in args]))
            # The inherited handles are the three pipes only; no service credentials or ambient environment.
            if not security.CreateProcessAsUserW(token, str(args[0]), command, None, None, True,
                    0x4 | 0x80000 | 0x400 | subprocess.CREATE_NO_WINDOW, environment, str(cwd),
                    C.byref(startup), C.byref(info)):
                raise OSError('직원 권한 프로세스 생성 실패: ' + str(C.get_last_error()))
            created = True
            if not kernel.AssignProcessToJobObject(self.handle, info.process):
                raise OSError('Windows 프로세스 결속 실패')
            if kernel.ResumeThread(info.thread) == 0xFFFFFFFF:
                raise OSError('Windows 프로세스 시작 실패')
            return UserProcess(kernel, info.process, info.pid, streams)
        except BaseException:
            if created:
                kernel.TerminateProcess(info.process, 1)
                kernel.WaitForSingleObject(info.process, 3000)
                kernel.CloseHandle(info.process)
            for stream in streams:
                stream.close()
            self.close()
            raise
        finally:
            if info.thread:
                kernel.CloseHandle(info.thread)
            if initialized:
                kernel.DeleteProcThreadAttributeList(attributes)
            for descriptor in descriptors:
                os.close(descriptor)
            if token:
                kernel.CloseHandle(token)

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

"""Unicode shell links via IShellLinkW/IPersistFile (no ANSI WScript path loss)."""
from contextlib import contextmanager
import ctypes
from pathlib import Path
import uuid


class GUID(ctypes.Structure):
    _fields_ = [('data1', ctypes.c_uint32), ('data2', ctypes.c_uint16),
                ('data3', ctypes.c_uint16), ('data4', ctypes.c_ubyte * 8)]

    @classmethod
    def parse(cls, value):
        return cls.from_buffer_copy(uuid.UUID(value).bytes_le)


def check(code):
    if code < 0:
        raise OSError('Windows 快捷方式接口失败：0x%08X' % (code & 0xffffffff))


def method(obj, index, *types):
    table = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    return ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *types)(table[index])


@contextmanager
def interfaces():
    ole = ctypes.OleDLL('ole32')
    ole.CoInitializeEx.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    ole.CoInitializeEx.restype = ctypes.c_long
    ole.CoCreateInstance.argtypes = [ctypes.POINTER(GUID), ctypes.c_void_p, ctypes.c_uint32,
                                    ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)]
    ole.CoCreateInstance.restype = ctypes.c_long
    code = ole.CoInitializeEx(None, 2)
    check(code)
    link, persist = ctypes.c_void_p(), ctypes.c_void_p()
    try:
        clsid = GUID.parse('00021401-0000-0000-c000-000000000046')
        iid = GUID.parse('000214f9-0000-0000-c000-000000000046')
        check(ole.CoCreateInstance(ctypes.byref(clsid), None, 1, ctypes.byref(iid), ctypes.byref(link)))
        persist_id = GUID.parse('0000010b-0000-0000-c000-000000000046')
        check(method(link, 0, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p))(
            link, ctypes.byref(persist_id), ctypes.byref(persist)))
        yield link, persist
    finally:
        if persist:
            method(persist, 2)(persist)
        if link:
            method(link, 2)(link)
        ole.CoUninitialize()


def create(path, target, arguments, working_directory):
    with interfaces() as (link, persist):
        for index, value in ((20, target), (11, arguments), (9, working_directory),
                             (7, '打开 Codex 对话整理工作台')):
            check(method(link, index, ctypes.c_wchar_p)(link, str(value)))
        check(method(link, 15, ctypes.c_int)(link, 7))
        check(method(persist, 6, ctypes.c_wchar_p, ctypes.c_int)(persist, str(Path(path)), 1))


def read(path):
    with interfaces() as (link, persist):
        check(method(persist, 5, ctypes.c_wchar_p, ctypes.c_uint32)(persist, str(Path(path)), 0))
        target = ctypes.create_unicode_buffer(32768)
        check(method(link, 3, ctypes.c_wchar_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32)(
            link, target, len(target), None, 0))
        arguments = ctypes.create_unicode_buffer(32768)
        check(method(link, 10, ctypes.c_wchar_p, ctypes.c_int)(link, arguments, len(arguments)))
        return {'target': target.value, 'args': arguments.value}

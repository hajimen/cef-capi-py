import typing as ty
import sys
import ctypes
import sysconfig
from pathlib import Path

NON_GC_DEPOT = {}

match sys.byteorder:
    case 'little':
        UTF16_ENCODING = 'utf-16-le'
    case 'big':
        UTF16_ENCODING = 'utf-16-be'
    case _:
        raise Exception('unknown byteorder')


RUNTIME_DIR = (Path(__file__).parent / 'runtime').absolute()
if not RUNTIME_DIR.exists():
    RUNTIME_DIR = (Path(__file__).parent.parent / 'cef_binary/client/Release').absolute()
    if not RUNTIME_DIR.exists():
        raise Exception('Prepare cef_binary/client/Release directory from CEF Automated Builds tar.bz2.')

match sysconfig.get_platform():
    case 'win-amd64':
        if sys.platform == 'win32':  # Helps Pylance
            LIBCEF_PATH = RUNTIME_DIR / 'libcef.dll'
            import cef_capi.win_amd64.header as header  # noqa
            import cef_capi.win_amd64.struct as struct  # noqa
    case 'linux-aarch64':
        if sys.platform == 'linux':  # Helps Pylance
            LIBCEF_PATH = RUNTIME_DIR / 'libcef.so'
            import cef_capi.linux_aarch64.header as header  # noqa
            import cef_capi.linux_aarch64.struct as struct  # noqa
    case 'linux-x86_64':
        if sys.platform == 'linux':  # Helps Pylance
            LIBCEF_PATH = RUNTIME_DIR / 'libcef.so'
            import cef_capi.linux_x86_64.header as header  # noqa
            import cef_capi.linux_x86_64.struct as struct  # noqa
    case _:
        es = sysconfig.get_platform().split('-')
        if es[0] == 'macosx':
            if sys.platform == 'darwin':  # Helps Pylance
                LIBCEF_PATH = RUNTIME_DIR / 'cefclient.app/Contents/Frameworks/Chromium Embedded Framework.framework/Chromium Embedded Framework'
                match es[2]:
                    case 'x86_64':
                        import cef_capi.macosx_x86_64.header as header  # noqa
                        import cef_capi.macosx_x86_64.struct as struct  # noqa
                    case 'arm64':
                        import cef_capi.macosx_arm64.header as header  # noqa
                        import cef_capi.macosx_arm64.struct as struct  # noqa
                    case _:
                        raise Exception(f'unknown architecture: {es[2]}')
        else:
            raise Exception(f'unknown platform: {es}')


def _init():
    from cef_capi import version

    global __version__
    global __version_info__
    __version_info__ = tuple(header.cef_version_info(i) for i in range(3))
    __version__ = '.'.join(map(str, __version_info__))

    dll_ver_inf = (version.CEF_VERSION_MAJOR, version.CEF_VERSION_MINOR, version.CEF_VERSION_PATCH)
    dll_ver = '.'.join(map(str, dll_ver_inf))
    if dll_ver_inf != __version_info__:
        print(f'cef-capi-py: warning: libcef runtime version is {__version__} but ctypes thunk version is {dll_ver}.')


_init()

cef_string_t = struct.cef_string_utf16_t


def cef_string_ctor(s: str, u: cef_string_t | None = None):
    '''
    Converts str to cef_string_utf16_t.
    '''
    if u is None:
        u = cef_string_t()

    # Why don't use ctypes.create_unicode_buffer()? In macOS, ctypes.sizeof(ctypes.c_wchar) == 4.
    # CEF requires 2-byte UTF-16.
    buf = s.encode(UTF16_ENCODING)
    u.str = ctypes.cast(ctypes.c_char_p(buf), type(u.str))
    u.length = len(buf) // 2
    return u


def cef_pointer_to_struct(v, cef_struct_t: type):
    '''
    Converts pointer to struct. If |v| is struct itself, checks the type.
    '''
    if isinstance(v, int):
        ret = ctypes.cast(
            ctypes.c_void_p(v),
            ctypes.POINTER(cef_struct_t)
        ).contents
    elif isinstance(v, ctypes.POINTER(cef_struct_t)):
        ret = v.contents
    elif isinstance(v, cef_struct_t):
        ret = v
    else:
        raise Exception(f'cef_pointer_to_struct() got wrong arg: {v}')
    return ret


def decode_cef_string(
        cs: cef_string_t | ctypes._Pointer | int,
        free_after_decode=False):
    '''
    Converts `cef_string_utf16_t` instance to str. |free_after_decode| is good for userfree instance.
    '''
    cef_string: cef_string_t = cef_pointer_to_struct(cs, cef_string_t)
    buf_p = ctypes.cast(cef_string.str, ctypes.POINTER(ctypes.c_byte * cef_string.length * 2))
    if not bool(buf_p):
        raise Exception('NULL pointer.')
    ret = bytes(buf_p.contents).decode(UTF16_ENCODING)

    if free_after_decode:
        if isinstance(cs, int):
            p = ctypes.cast(
                ctypes.c_void_p(cs),
                ctypes.POINTER(cef_string_t)
            )
        else:
            p = cs
        header.cef_string_userfree_utf16_free(p)

    return ret


def _register_callback(
        struct_obj: ctypes.Structure,
        name: str,
        handler_func: ty.Callable | None = None,
        ignore_arg_indices: set[int] = {0},
        raw_arg_indices: set[int] = set(),
        additional_args: tuple = tuple(),
        additional_kwargs: dict = dict()):
    '''
    Registers event handler to |struct_obj|.

    kwarg |ignore_arg_indices| is for ignoring unused handler arg.
    Index 0 (self) is ignored by default.

    Be careful of auto dereferencing of decorated function args.
    To disable auto dereferencing, use |raw_arg_indices|.

    |additional_args| and |additional_kwargs| are for cef_task_t.
    '''
    p = getattr(struct_obj, name)
    is_first_call = True

    # print(f'{str(struct_obj)}.{name} registered.')

    def cb(*args):
        nonlocal is_first_call
        if is_first_call:
            is_first_call = False
            # print(f'{str(struct_obj)}.{name} called.')

        if handler_func is None:
            if p.restype is not None:
                if p.restype is ctypes.c_void_p:
                    return None
                else:
                    return 0
        else:
            call_args = [
                # Auto dereferencing
                (a.contents if bool(a) else None) if (i not in raw_arg_indices) and isinstance(a, ctypes._Pointer) else a
                for i, a in enumerate(args) if i not in ignore_arg_indices
            ]
            ret = handler_func(*call_args, *additional_args, **additional_kwargs)

            if ret is None or isinstance(ret, int):
                return ret
            if isinstance(ret, ctypes.Structure):
                to_check = ret
            elif isinstance(ret, ctypes._Pointer):
                to_check = ret.contents
            else:
                raise Exception(f'Callback should return only None, int, or cef_base_ref_counted_t-ed struct. The return value {ret} looks wrong.')
            if hasattr(to_check, 'base') and isinstance(to_check.base, struct.cef_base_ref_counted_t):
                return ctypes.addressof(ret)  # automatic int conversion. See ReadMe.md.
            raise Exception('Python GC may remove the return value!')

    cf = p.__class__(cb)
    setattr(struct_obj, name, cf)


def _init_cef_base_ref_counted(o):
    '''
    CEF ref count and Python GC are a bit esoteric both.
    '''
    ref_count = 1
    base: struct.cef_base_ref_counted_t = o.base

    @handler(base)
    def add_ref():
        '''
        Increment the reference count.
        '''
        nonlocal ref_count
        if ref_count == 0:
            print(f'cef-capi-py ERROR: cef_base_ref_counted_t access to released instance. o: {o}')
        ref_count += 1

    @handler(base)
    def release():
        '''
        Decrement the reference count.  Delete this object when no references
        remain.
        '''
        nonlocal ref_count
        if ref_count == 0:
            print(f'cef-capi-py ERROR: cef_base_ref_counted_t underrun. o: {o}')
        else:
            ref_count -= 1
            if ref_count == 0:
                # print(f'delete {o}')
                del NON_GC_DEPOT[id(o)]
        return 1 if ref_count == 0 else 0

    @handler(base)
    def has_one_ref():
        '''
        Returns the current number of references.
        '''
        return 1 if ref_count == 1 else 0

    @handler(base)
    def has_at_least_one_ref():
        '''
        Returns the current number of references.
        '''
        return 1 if ref_count > 1 else 0

    NON_GC_DEPOT[id(o)] = o


def base_ctor(struct_t: type):
    '''
    Many structs have "base" member. It requires initialization.
    '''
    o = struct_t()
    o.base.size = ctypes.sizeof(struct_t)
    _init_cef_base_ref_counted(o)
    return o


def size_ctor(struct_t: type):
    '''
    Many structs are mandatory to set the "size" member.
    '''
    _size = struct_t()
    _size.size = ctypes.sizeof(struct_t)
    return _size


def task_factory(func: ty.Callable) -> ty.Callable[..., struct.cef_task_t]:
    '''
    Decorator to make `cef_task_t` ctor.

    CEF deletes `cef_task_t` instance after its `execute()` call.
    You have to construct `cef_task_t` instance every task post.

    You can pass kwargs from ctor to `execute()`.
    '''
    def factory(*additional_args, **additional_kwargs) -> struct.cef_task_t:
        task = base_ctor(struct.cef_task_t)
        _register_callback(task, 'execute', func,
                           additional_args=additional_args, additional_kwargs=additional_kwargs)
        return task

    return factory


def handler(struct_obj: ctypes.Structure, **kwargs):
    '''
    Decorator to register event handler.
    The decorated function's name becomes event name.

    kwarg |ignore_arg_indices| is for ignoring unused handler arg.
    Index 0 (self) is ignored by default.

    Be careful of auto dereferencing of decorated function args.
    To disable auto dereferencing, use |raw_arg_indices|.
    '''
    def decorator(func: ty.Callable) -> None:
        _register_callback(struct_obj, func.__name__, func, **kwargs)
        return

    return decorator

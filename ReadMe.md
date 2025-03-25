# cef-capi-py

**cef-capi-py** is Chromium Embedded Framework (CEF) C API wrapper for Python without C extension, with ctypes.

cef-capi-py wheel contains CEF runtime, of course.

## Introduction

I need newer Python but I don't need newer CEF!

Python C extension is a good thing but it has a severe drawback: ABI instability.
Almost everyone ignores [Limited API](https://docs.python.org/3/c-api/stable.html#limited-c-api),
e.g. [pybind11](https://github.com/pybind/pybind11).
Yes, [cefpython](https://github.com/cztomczak/cefpython) ignores too.
So we have to build C extension every year, 3.7, 3.8, 3.9, 3.10...
I deeply understand why cefpython has stopped to update.

I need newer Python but I don't need newer CEF,
because I just want to embed a local web app in my Python app.
The local web app never requires newer CEF.

**cef-capi-py** is the resolution. It does not use C extension. So we don't have to build C extension every year anymore.
Instead of C extension, cef-capi-py uses [ctypes](https://docs.python.org/3/library/ctypes.html).

Without type hints, using CEF is a big pain. I have tried PyObjC for Mac GUI, and abandoned for the reason
(this is why cef-capi-py lacks Chromium-like window app example for Mac).
No problem, [ctypeslib](https://github.com/trolldbois/ctypeslib) and mypy does great jobs for cef-capi-py.
They are not perfect, but good enough.

## Design policy

I have hacked cefpython and [made it work with Python 3.12 for Windows x86-64](https://github.com/hajimen/cefpython).
I feel it is not maintainable. cefpython's codebase and documents are too big, and I need just a part of it.
For example, I don't need Python 2.7 support.

The primary target of cef-capi-py is maintainability. It means minimal codebase and document.
Every non-essential thing is abandoned.

- No document of CEF: See original CEF documents. cef-capi-py is a thin wrapper of [CEF C API](https://github.com/chromiumembedded/cef/tree/master/include/capi). You should get **userfree** idea of CEF from CEF documents, and keep it in your code, for example.
- Little document of cef-capi-py itself: This ReadMe.md is almost everything. Learn with touching the example codes.
- No comprehensive test: Just a simple smoke test for safeguard. Run `python -m cef_capi.smoke_test`.
- No automated build: In Python, everything changes rapidly. CEF also changes rapidly. Automated build requires much cost to maintain.
- No frequent update: I will not update cef-capi-py while it works. I predict that someday OSes can block old CEF, someday Python can break some ctypes features. Except such cases, I will not update cef-capi-py.
- No optimization: Optimization makes codebase unmaintainable.
- Single process mode for V8 extension (JavaScript interaction): CEF usually creates **render process** as subprocess. V8 extension code should be written in render process, but it is extremely hard for Python. I just go with single process mode.

## Set up to learn / build

CEF is a gigantic codebase, so it is not very kind to newbies.
cef-capi-py is quite small except generated codes, but it has little document.
Learn from examples. We are going to set up for touching the examples.

### All platforms

First of all, `git clone` this repository, and set up venv or something.

Run `pip install -r requirements.txt` in repo root.

Extract tar.bz2 file of [CEF Automated Builds](https://cef-builds.spotifycdn.com/index.html)
to `cef_binary/client` and `cef_binary/minimal`.
If you are just going to learn the behavior of cef-capi-py, leave `cef_binary/minimal` untouched.
See the `ReadMe.md` files of each directory.

In Windows, `cef_binary/client/Release/cefclient.exe` should be found.

### Linux

CEF depends on libgtk-3, libnss3, and libasound2.
For Ubuntu, `sudo apt install libgtk-3-dev libnss3 libasound2t64`.
Even just running windowless, CEF requires X11.
In the case, `sudo apt install xorg xvfb x11-xkb-utils`.

If you don't have dbus, CEF reports errors, but you can ignore them.

### Linux aarch64 (ARM64)

Run `export LD_PRELOAD=/{somewhere}/libcef.so` before running CEF.
It comes from a bug of CEF Automated Builds: [Dynamic loading of libcef.so on Linux ARM64 not possible anymore due to TLS size increase](https://github.com/chromiumembedded/cef/issues/3803).

### macOS

Run `xattr -cr cef_binary` in repo root. Ignore permission error.

### Shell

- Linux and macOS: bash
- Windows: PowerShell

## Running examples

### Chromium-like window app

You should see a Chromium-like window app with:

- Windows: `python -m examples.window_win`.
- Linux: `python -m examples.window_linux`. **CAUTION**: In Linux, you need to hit a key of your keyboard before closing the app window.
Without hitting a key, the app does not exit. Maybe a bug somewhere.
- Mac: I don't have it yet.

### Screenshot

You should have `screenshot.png` with `python -m examples.screenshot`.

### V8 extension (JavaScript interaction)

Run `python -m examples.javascript` and look at the stdout of it.
You should see `Foo() called with right arg "x from javascript.py:execute_bar()".` in it.

## Commentary of odd things

### `cef_capi.{platform tag}.header` and `cef_capi.{platform tag}.struct`

`header.py` is generated by ctypeslib. But it lacks C struct field name hint when we use it with VSCode.
`struct.py` can do hinting. But `struct.py` cannot find function declaration with F12 in VSCode.
For CEF functions, use `cef_capi.{platform tag}.header`. For CEF structs, use `cef_capi.{platform tag}.struct`.

`cef_capi.header` and `cef_capi.struct` are for platform independent code.

### Decorators `@handler()` and `@task_factory`

Look at `examples/screenshot.py`.

CEF C API uses C-style OOP. `@handler()` decorator is for member function overriding.
`@handler()` gets the decorated function's name and uses the name as member function's name.
Very odd usage but good for simplicity.

`@handler()` decorator has four odd features. Look at `cef_capi/__init__.py` until
you get the meaning of them:

- **Auto dereferencing** of `ctypes._Pointer` instances of args
- kwarg `raw_arg_indices: set[int]` to disable auto dereferencing.
- kwarg `ignore_arg_indices: set[int]` to ignore namely `self` arg. If you need `self` for handler arg, write `ignore_arg_indices=set()` in `@handler()` arg.
- If the return value is `cef_base_ref_counted_t`-ed struct instance or its pointer, it is converted to `int`. (see `cef_pointer_to_struct()` subsection below)

`@task_factory` decorator converts the decorated function to `cef_task_t` ctor.
CEF deletes `cef_task_t` instance after `execute()` call.
You have to construct `cef_task_t` every task post.
The ctor can pass args to `execute()`.

### `cef_pointer_to_struct()`

Look at `examples/javascript.py`.

It's a long story; It comes from 15-year bug of Python ctypes: [Python ctypes callback function gives "TypeError: invalid result type for callback function"](https://stackoverflow.com/questions/33005127/python-ctypes-callback-function-gives-typeerror-invalid-result-type-for-callba).

CEF C API uses C-style OOP. For the bug, the member function cannot return a pointer to struct.
So we have to use `int` instead of `ctypes._Pointer` in the case.

`cef_pointer_to_struct()` converts the `int` to `ctypes.Structure`.

### `import faulthandler; faulthandler.enable()`

CEF easily raises segmentation fault. Python does not show any error message for segmentation fault without
`import faulthandler; faulthandler.enable()`.

### CEF can hang up

Sometimes CEF hangs up. You should have a timeout / retry mechanism in your products.
See the example of timeout / retry mechanism in `cef_capi/smoke_test.py`.

### Error reports from CEF

You can ignore them for most usage.
`settings.log_severity = struct.LOGSEVERITY_DISABLE` stops most CEF error reporting. Not all.

### Memory management?

Note the possibility of memory leaks. Python and CEF memory management style mismatch is too notorious for us.

## Integrating to your product

Use wheel. It contains CEF runtime, of course. You can find it in [PyPI](https://pypi.org/project/cef-capi-py/).

The version of wheel is CEF runtime's.

## Generating ctypes thunk and type hint stub

I don't want to update cef-capi-py frequently, but sooner or later the day will come.
This section is for the day.

CEF changes rapidly, including its API header files. Once API header files have been changed,
we need to re-generate ctypes thunk (`cef_capi/*/header.py`) and its type hint stub (`cef_capi/*/struct.pyi`).

### All platforms

ctypes thunk generation depends on `ctypeslib2==2.3.4`. Before generation, we need to fix the bugs of it.

- Windows: ```python -m patch -d (python -c 'import sysconfig; print(sysconfig.get_path("purelib"))') tool/ctypeslib.patch```
- Others (bash): ```python -m patch -d `python -c 'import sysconfig; print(sysconfig.get_path("purelib"))'` tool/ctypeslib.patch```

### Windows

Install LLVM 15. [LLVM Download Page](https://releases.llvm.org/download.html)

The ctypeslib2 command is:

```powershell
# start from repo root
cd cef_binary/minimal
clang2py -c -o ../../cef_capi/win_amd64/header.py -i -k cdefstu (Get-Item include/capi/*.h) include/cef_version.h -r cef.* -r CEF.* --clang-args="-I."
```

Generated `cef_capi/win_amd64/header.py` should regex replace: `CFUNCTYPE\(ctypes\.POINTER\(\w*\)` to `CFUNCTYPE(ctypes.c_uint64` for 15-year bug of Python ctypes: [Python ctypes callback function gives "TypeError: invalid result type for callback function"](https://stackoverflow.com/questions/33005127/python-ctypes-callback-function-gives-typeerror-invalid-result-type-for-callba)

In `cef_capi/win_amd64/header.py`, replace:

```python
_libraries['FIXME_STUB'] = FunctionFactoryStub() #  ctypes.CDLL('FIXME_STUB')
```

to

```python
from cef_capi import LIBCEF_PATH
_libraries['FIXME_STUB'] = ctypes.WinDLL(str(LIBCEF_PATH))
```

And mypy command:

```powershell
# start from repo root
stubgen -m cef_capi.win_amd64.header -o . --inspect-mode
Remove-Item ./cef_capi/win_amd64/struct.pyi
Rename-Item cef_capi/win_amd64/header.pyi struct.pyi
```

### Linux

clang-15 is required. For Ubuntu, `sudo apt install clang-15`.

The ctypeslib2 command is:

```bash
# start from repo root
cd cef_binary/minimal
clang2py -c -o ../../cef_capi/linux_`uname -m`/header.py -i -k cdefstu include/capi/*.h include/cef_version.h -r cef.* -r CEF.* --clang-args="-I."
clang2py -c -o ../../examples/linux_`uname -m`/gtk_x_header.py -i -k cdefstu /usr/include/X11/Xlib.h /usr/include/gtk-3.0/gtk/gtk.h /usr/include/gtk-3.0/gdk/gdkx.h -r "^X.*" -r "^gtk.*" -r "^Gtk.*" -r "^g_.*" -r "^G_.*" -r "^gdk_.*" -r "^Gdk.*" --clang-args="-I. -I/usr/include/gtk-3.0 -I/usr/include/glib-2.0 -I/usr/lib/`uname -m`-linux-gnu/glib-2.0/include -I/usr/include/pango-1.0 -I/usr/include/harfbuzz -I/usr/include/cairo -I/usr/include/gdk-pixbuf-2.0 -I/usr/include/atk-1.0" -l gtk-3
```

Generated `cef_capi/linux_{machine hardware name}/header.py` and `examples/linux_{machine hardware name}/gtk_x_header.py` should be regex replaced: `CFUNCTYPE\(ctypes\.POINTER\(\w*\)` to `CFUNCTYPE(ctypes.c_uint64` for 15-year bug of Python ctypes: [Python ctypes callback function gives "TypeError: invalid result type for callback function"](https://stackoverflow.com/questions/33005127/python-ctypes-callback-function-gives-typeerror-invalid-result-type-for-callba)

In `cef_capi/linux_{machine hardware name}/header.py`, replace:

```python
_libraries['FIXME_STUB'] = FunctionFactoryStub() #  ctypes.CDLL('FIXME_STUB')
```

to

```python
from cef_capi import LIBCEF_PATH
_libraries['FIXME_STUB'] = ctypes.CDLL(str(LIBCEF_PATH))
```

In `examples/linux_{machine hardware name}/gtk_x_header.py`, add after `_libraries = {}` and `FunctionFactoryStub` class def both:

```python
import ctypes.util
_libraries['FIXME_STUB'] = FunctionFactoryStub() #  ctypes.CDLL('FIXME_STUB')
_libraries['libgtk-3.so.0'] = ctypes.CDLL(ctypes.util.find_library('gtk-3'))
```

And mypy command:

```bash
# start from repo root
stubgen -m cef_capi.linux_`uname -m`.header -o . --inspect-mode
rm cef_capi/linux_`uname -m`/struct.pyi
mv cef_capi/linux_`uname -m`/header.pyi cef_capi/linux_`uname -m`/struct.pyi
```

### macOS

Assuming Apple Silicon.

clang-15 is required. Set up Homebrew and `brew install llvm@15`. If you are going to generate x86_64 too,
`arch -x86_64 /opt/homebrew-x86_64/bin/brew install llvm@15`. Each arch requires different `cef_binary`.

The ctypeslib2 command is:

```bash
# start from repo root
export MHN="arm64" # or x86_64
source tool/macosx-clang-15-${MHN}.sh
cd cef_binary/minimal
clang2py -c -o ../../cef_capi/macosx_${MHN}/header.py -i -k cdefstu include/capi/*.h include/cef_version.h -r cef.* -r CEF.* --clang-args="-I."
```

Generated `cef_capi/macosx_{machine hardware name}/header.py` should regex replace: `CFUNCTYPE\(ctypes\.POINTER\(\w*\)` to `CFUNCTYPE(ctypes.c_uint64` for 15-year bug of Python ctypes: [Python ctypes callback function gives "TypeError: invalid result type for callback function"](https://stackoverflow.com/questions/33005127/python-ctypes-callback-function-gives-typeerror-invalid-result-type-for-callba)

In `cef_capi/macosx_{machine hardware name}/header.py`, add after `_libraries = {}` and `FunctionFactoryStub` class def both:

```python
from cef_capi import LIBCEF_PATH
_libraries['FIXME_STUB'] = ctypes.CDLL(str(LIBCEF_PATH))
```

And mypy command:

```bash
# start from repo root
export MHN="arm64" # or x86_64
stubgen -m cef_capi.macosx_${MHN}.header -o . --inspect-mode
rm cef_capi/macosx_${MHN}/struct.pyi
mv cef_capi/macosx_${MHN}/header.pyi cef_capi/macosx_${MHN}/struct.pyi
```

### Any platform

Generate version info of CEF in any platform:

```
# start from repo root
cd cef_binary/minimal
clang2py -c -o ../../cef_capi/version.py -x -k m include/cef_version.h -r cef.* -r CEF.* --clang-args="-I."
```

## Build wheel

Set up `cef_binary/client` as above. Then:

- Windows: `python -m build --wheel --config-setting=--build-option=--plat-name=win_amd64`
- Linux:

```bash
# start from repo root
strip cef_binary/client/Release/*.so cef_binary/client/Release/cefsimple
python -m build --wheel --config-setting=--build-option=--plat-name=manylinux2014_`uname -m`
```
- macOS:

```bash
# start from repo root
export MHN="arm64" # or x86_64
python -m build --wheel --config-setting=--build-option=--plat-name=macosx_11_0_${MHN}
```

Do not forget to check the wheel by `python -m cef_capi.smoke_test`.

## License

MIT License.

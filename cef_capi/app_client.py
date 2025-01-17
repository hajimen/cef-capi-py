import sys
import sysconfig
import ctypes
from cef_capi import base_ctor, struct, header, cef_string_ctor, handler, size_ctor, RUNTIME_DIR, cef_string_t


def client_ctor():
    '''
    Returns appropriate `cef_client_t` instance for most usage.
    '''
    client = base_ctor(struct.cef_client_t)

    @handler(client)  # Register a handler `get_life_span_handler()` to `client`.
    def get_life_span_handler(*_):
        '''
        Returns a handler for browser life span events.
        '''
        life_span_handler = base_ctor(struct.cef_life_span_handler_t)
    
        @handler(life_span_handler)  # Register a handler `on_before_close()` to `life_span_handler`.
        def on_before_close(browser: struct.cef_browser_t):
            '''
            Called just before a browser is destroyed. Release all references to the
            browser object and do not attempt to execute any functions on the browser
            object (other than IsValid, GetIdentifier or IsSame) after this callback
            returns. cef_frame_handler_t callbacks related to final main frame
            destruction, and OnBeforePopupAborted callbacks for any pending popups,
            will arrive after this callback and cef_browser_t::IsValid will return
            false (0) at that time. Any in-progress network requests associated with
            |browser| will be aborted when the browser is destroyed, and
            cef_resource_request_handler_t callbacks related to those requests may
            still arrive on the IO thread after this callback. See cef_frame_handler_t
            and do_close() documentation for additional usage information.
            '''
            header.cef_quit_message_loop()

        # Many other handlers are available.
        # Search "cef_life_span_handler_t._fields_" in header.py.

        return life_span_handler

    # Many other handlers are available.
    # Search "cef_client_t._fields_" in header.py.

    return client


def app_ctor(disable_gpu=True, single_process=False):
    '''
    Returns appropriate `cef_app_t` instance for most usage.
    |disable_gpu| enables `disable-gpu` and `disable-gpu-compositing` switches.
    |single_process| is required for V8 extension (JavaScript interaction).
    '''
    app = base_ctor(struct.cef_app_t)

    @handler(app)  # Register a handler `on_before_command_line_processing()` to `app`.
    def on_before_command_line_processing(
            process_type: cef_string_t,
            command_line: struct.cef_command_line_t):
        '''
        Provides an opportunity to view and/or modify command-line arguments
        before processing by CEF and Chromium. The |process_type| value will be
        NULL for the browser process. Do not keep a reference to the
        cef_command_line_t object passed to this function. The
        cef_settings_t.command_line_args_disabled value can be used to start with
        an NULL command-line object. Any values specified in CefSettings that
        equate to command-line arguments will be set before this function is
        called. Be cautious when using this function to modify command-line
        arguments for non-browser processes as this may result in undefined
        behavior including crashes.
        '''
        # Add a switch to the end of the command line.
        if single_process:
            command_line.append_switch(command_line, cef_string_ctor('single-process'))
        if disable_gpu:
            command_line.append_switch(command_line, cef_string_ctor('disable-gpu'))
            command_line.append_switch(command_line, cef_string_ctor('disable-gpu-compositing'))

            # Without this, "GPU process isn't usable. Goodbye." occurs.
            # See https://stackoverflow.com/questions/68874940/gpu-process-isnt-usable-goodbye
            command_line.append_switch(command_line, cef_string_ctor('in-process-gpu'))
        if sys.platform == 'darwin':
            # Disable the toolchain prompt on macOS.
            command_line.append_switch(command_line, cef_string_ctor('use-mock-keychain'))

    # Many other handlers are available.
    # Search "cef_app_t._fields_" in header.py.

    return app


def settings_main_args_ctor():
    '''
    Returns appropriate `cef_settings_t` and `cef_main_args_t` instances for the platform.
    '''
    settings = size_ctor(struct.cef_settings_t)
    main_args = struct.cef_main_args_t()
    match sysconfig.get_platform():
        case 'win-amd64':
            from ctypes import wintypes
            kernel32 = ctypes.WinDLL("kernel32")  # type: ignore
            GetModuleHandleW = kernel32.GetModuleHandleW
            GetModuleHandleW.restype = ctypes.POINTER(struct.struct_HINSTANCE__)  # type: ignore
            GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
            main_args.instance = GetModuleHandleW(None)
            # browser_subprocess_path is mandatory for Python. Without this,
            # CEF launches Python interpreter as subprocess. No other workaround.
            settings.browser_subprocess_path = cef_string_ctor(str(RUNTIME_DIR / 'cefclient.exe'))
        case 'linux-aarch64':
            main_args.argc = 0
            main_args.argv = ctypes.POINTER(ctypes.POINTER(ctypes.c_ubyte))()
            # browser_subprocess_path is mandatory for Python. Without this,
            # CEF launches Python interpreter as subprocess. No other workaround.
            settings.browser_subprocess_path = cef_string_ctor(str(RUNTIME_DIR / 'cefsimple'))
        case 'linux-x86_64':
            main_args.argc = 0
            main_args.argv = ctypes.POINTER(ctypes.POINTER(ctypes.c_char))()
            # browser_subprocess_path is mandatory for Python. Without this,
            # CEF launches Python interpreter as subprocess. No other workaround.
            settings.browser_subprocess_path = cef_string_ctor(str(RUNTIME_DIR / 'cefsimple'))
        case _:
            es = sysconfig.get_platform().split('-')
            if es[0] == 'macosx':
                main_args.argc = 0
                main_args.argv = ctypes.POINTER(ctypes.POINTER(ctypes.c_char))()
                fp = str(RUNTIME_DIR / 'cefclient.app/Contents/Frameworks/Chromium Embedded Framework.framework')
                settings.framework_dir_path = cef_string_ctor(fp)
                bp = str(RUNTIME_DIR / 'cefclient.app')
                settings.main_bundle_path = cef_string_ctor(bp)
                # browser_subprocess_path is mandatory for Python. Without this,
                # CEF launches Python interpreter as subprocess. No other workaround.
                sp = str(RUNTIME_DIR / 'cefclient.app/Contents/Frameworks/cefclient Helper.app/Contents/MacOS/cefclient Helper')
                settings.browser_subprocess_path = cef_string_ctor(sp)
            else:
                raise Exception(f'unknown platform: {es}')

    return settings, main_args

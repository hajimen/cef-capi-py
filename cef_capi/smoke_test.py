import faulthandler
faulthandler.enable()
import typing as ty
import ctypes
import sys
import os
import time
import threading
from itertools import product
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from multiprocessing import Process

from cef_capi import base_ctor, struct, header, cef_string_ctor, handler, size_ctor, task_factory, decode_cef_string, cef_string_t
from cef_capi.app_client import client_ctor, app_ctor, settings_main_args_ctor

VIEWPORT_SIZE = (800, 600)
COLOR_SHOULD_BE = (0, 0x80, 0, 0xff)  # BGRA green
TIMEOUT_AT = -1.
TIMEOUT_SPAN = 20.  # 20 seconds


def main():
    '''
    Tests CEF runtime loading, reachability to local web server, screenshot, and JavaScript execution / extension.
    '''
    print('Running cef-capi-py smoke test...')

    # Retry mechanism
    retry = False
    while True:
        test_process = Process(target=test_process_main)
        test_process.start()
        test_process.join()
        if test_process.exitcode == 0:
            break

        if retry:
            print('cef-capi-py smoke test failed.')
            sys.exit(1)
        retry = True
        print('cef-capi-py smoke test retrying...')

    print('cef-capi-py smoke test OK.')


def test_process_main():
    global TIMEOUT_AT

    try:
        class Handler(SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(
                    *args,
                    directory=os.path.join(
                        os.path.abspath(os.path.dirname(__file__)),
                        'smoke_test_webpage'),
                    **kwargs)

            def log_message(self, format, *args):
                pass

        tcp_server = ThreadingHTTPServer(
            ('127.0.0.1', 0),
            Handler)
        tcp_server_thread = threading.Thread(target=tcp_server.serve_forever, daemon=True)
        tcp_server_thread.start()
        server_port = str(tcp_server.server_address[1])

        timeout_thread = threading.Thread(target=_fail_after_timeout_span)
        timeout_thread.start()

        reg_process = Process(target=_main, args=(server_port, False))
        reg_process.start()
        reg_process.join()
        if reg_process.exitcode != 0:
            sys.exit(1)

        v8_process = Process(target=_main, args=(server_port, True))
        v8_process.start()
        v8_process.join()
        if v8_process.exitcode != 0:
            sys.exit(1)
    finally:
        TIMEOUT_AT = 0.
        timeout_thread.join(.1)
        tcp_server.shutdown()


def _fail_after_timeout_span():
    global TIMEOUT_AT
    TIMEOUT_AT = time.time() + TIMEOUT_SPAN
    while TIMEOUT_AT > time.time():
        time.sleep(.01)
    if TIMEOUT_AT > 0.:
        print('cef-capi-py smoke test timeout.')
        os._exit(1)  # kills whole process tree under `test_process_main`.


def _main(server_port: str, check_v8_extension=False):
    '''
    CEF cannot initialize twice in a process.
    We have to create a process for different CEF settings.
    '''
    try:
        page_name = 'v8test' if check_v8_extension else 'index'
        _smoke_test_screenshot_check(
            f"http://localhost:{server_port}/{page_name}.html",
            check_v8_extension)
    except Exception as e:
        import traceback
        traceback.print_exception(e)
        sys.exit(1)


def _smoke_test_screenshot_check(url: str, check_v8_extension: bool):
    '''
    Takes a screenshot and checks |url| page for smoke test.
    The screenshot should be solid COLOR_SHOULD_BE color.
    '''
    # Some platforms (WSL2) fail if disable_gpu=False
    app = app_ctor(single_process=check_v8_extension, disable_gpu=True)

    prefix = '[v8]: ' if check_v8_extension else '[regular]: '

    settings, main_args = settings_main_args_ctor()
    settings.log_severity = struct.LOGSEVERITY_DISABLE
    settings.no_sandbox = 1
    settings.windowless_rendering_enabled = 1

    if check_v8_extension:
        v8handler = base_ctor(struct.cef_v8handler_t)

        @handler(v8handler, raw_arg_indices={4, 5})
        def execute(
                name: cef_string_t,
                object: struct.cef_v8value_t,
                arguments_count: int,
                arguments: ctypes._Pointer,  # ctypes.POINTER(ctypes.POINTER(struct.cef_v8value_t))
                retval: ctypes._Pointer,  # ctypes.POINTER(ctypes.POINTER(struct.cef_v8value_t))
                exception: cef_string_t):
            fn = decode_cef_string(name)
            match fn:
                case 'Foo':
                    if arguments_count != 0:
                        cef_string_ctor('bad argument count: Foo() arg should be zero.', exception)
                    else:
                        retval[0] = header.cef_v8value_create_string(cef_string_ctor('foo'))
            return 1

        @handler(app)
        def get_render_process_handler():
            render_process_handler = base_ctor(struct.cef_render_process_handler_t)

            @handler(render_process_handler)
            def on_web_kit_initialized(*_):
                header.cef_register_extension(
                    cef_string_ctor('v8/test_extension'),
                    cef_string_ctor('''
                        var example = {};
                        (function(){
                            example.foo = function(){
                                native function Foo();
                                return Foo();
                            }
                        })();
                    '''), v8handler)
                return 0

            return render_process_handler

    header.cef_initialize(main_args, settings, app, None)

    saved_browser: struct.cef_browser_t | None = None

    @task_factory
    def exit_app():
        if saved_browser is None:
            if saved_exception is not None:
                raise saved_exception
            print(prefix + 'ERROR: saved_browser is None.')
            sys.exit(1)
        browser_host_p = ctypes.cast(
            saved_browser.get_host(saved_browser),
            ctypes.POINTER(struct.cef_browser_host_t))
        browser_host_p.contents.close_browser(browser_host_p, 0)

    saved_exception: Exception | None = None

    def handle_exception(func: ty.Callable):
        def wrapped(*args, **kwargs):
            nonlocal saved_exception
            try:
                return func(*args, **kwargs)
            except Exception as e:
                saved_exception = e
                header.cef_post_task(header.TID_UI, exit_app())
        wrapped.__name__ = func.__name__
        return wrapped

    client = client_ctor()

    # Given bitmap of on_paint() handler.
    saved_buffer: ctypes.c_void_p | None = None

    @handler(client)
    def get_render_handler(*_):
        render_handler = base_ctor(struct.cef_render_handler_t)

        @handler(render_handler)
        @handle_exception
        def on_paint(
                browser: struct.cef_browser_t,
                element_type: int,
                dirty_rects_count: int,
                dirty_rects: struct.cef_rect_t,
                buffer: ctypes.c_void_p,
                width: int,
                height: int):
            nonlocal saved_buffer
            if element_type == header.PET_VIEW:
                saved_buffer = buffer

        @handler(render_handler)
        @handle_exception
        def get_view_rect(
                browser: struct.cef_browser_t,
                rect: struct.cef_rect_t):
            rect.x = 0
            rect.y = 0
            rect.width = VIEWPORT_SIZE[0]
            rect.height = VIEWPORT_SIZE[1]
            return 1

        return render_handler

    MAX_RETRY = 10

    @task_factory
    @handle_exception
    def check_screenshot(retry_count=0):
        if saved_buffer is None:
            if retry_count < MAX_RETRY:
                header.cef_post_delayed_task(
                    header.TID_UI,
                    check_screenshot(retry_count=retry_count + 1),
                    500)
                retry_count += 1
                return
            else:
                raise Exception(f'{prefix}saved_buffer is None')
        bstr = ctypes.string_at(saved_buffer, VIEWPORT_SIZE[0] * VIEWPORT_SIZE[1] * 4)
        for x, y, bgra in product(range(VIEWPORT_SIZE[0]), range(VIEWPORT_SIZE[1]), range(4)):
            i = (x + y * VIEWPORT_SIZE[0]) * 4 + bgra
            if bstr[i] != COLOR_SHOULD_BE[bgra]:
                if retry_count < MAX_RETRY:
                    header.cef_post_delayed_task(
                        header.TID_UI,
                        check_screenshot(retry_count=retry_count + 1),
                        500)
                    retry_count += 1
                    return
                print(f'{prefix}ERROR: bad pixel in screenshot')
                raise Exception(f'{prefix}Screenshot has wrong colored pixel.')
        header.cef_post_task(header.TID_UI, exit_app())

    @handler(client)
    def get_load_handler(*_):
        load_handler = base_ctor(struct.cef_load_handler_t)

        @handler(load_handler)
        @handle_exception
        def on_loading_state_change(
                browser: struct.cef_browser_t,
                is_loading: int,
                can_go_back: int,
                can_go_forward: int):
            nonlocal saved_browser
            if not is_loading:
                saved_browser = browser
                header.cef_post_delayed_task(header.TID_UI, check_screenshot(), 500)

        @handler(load_handler)
        @handle_exception
        def on_load_error(
                browser: struct.cef_browser_t,
                frame: struct.cef_frame_t,
                error_code: int,
                error_text: cef_string_t,
                failed_url: cef_string_t):
            nonlocal saved_browser
            if not frame.is_main(frame):
                return
            saved_browser = browser
            header.cef_post_task(header.TID_UI, exit_app())
        
        return load_handler

    window_info = struct.cef_window_info_t()
    window_info.windowless_rendering_enabled = 1
    window_info.window_name = cef_string_ctor("cef-capi-py smoke test")

    cef_url = cef_string_ctor(url)

    browser_settings = size_ctor(struct.cef_browser_settings_t)

    header.cef_browser_host_create_browser(
        window_info,
        client,
        cef_url,
        browser_settings,
        None,
        None
    )

    header.cef_run_message_loop()

    header.cef_shutdown()

    if saved_exception is not None:
        raise saved_exception


if __name__ == '__main__':
    main()

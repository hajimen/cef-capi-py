import faulthandler
faulthandler.enable()
import os
import ctypes
import threading
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

from cef_capi import cef_string_ctor, size_ctor, base_ctor, task_factory, handler, header, struct, decode_cef_string, cef_pointer_to_struct, cef_string_t, __version__
from cef_capi.app_client import client_ctor, app_ctor, settings_main_args_ctor

VIEWPORT_SIZE = (800, 600)


def main():
    '''
    We are going to see how to interact with JavaScript.
    '''
    # We need local web server.
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(
                *args,
                directory=os.path.join(
                    os.path.abspath(os.path.dirname(__file__)),
                    'webpage'),
                **kwargs)

        def log_message(self, format, *args):
            pass

    tcp_server = ThreadingHTTPServer(
        ('127.0.0.1', 0),
        Handler)
    tcp_server_thread = threading.Thread(
        target=tcp_server.serve_forever,
        daemon=True)
    tcp_server_thread.start()

    try:
        single_process_main(
            f"http://localhost:{str(tcp_server.server_address[1])}/index.html")
    finally:
        tcp_server.shutdown()


def single_process_main(url: str):
    print(f"CEF version: {__version__}")

    # `single_process`` is mandatory for JavaScript interaction.
    # It causes "Cannot use V8 Proxy resolver in single process mode." error message, but no problem for most usage.
    app = app_ctor(single_process=True)

    settings, main_args = settings_main_args_ctor()
    settings.log_severity = struct.LOGSEVERITY_DEBUG
    settings.no_sandbox = 1
    settings.windowless_rendering_enabled = 1

    v8handler = base_ctor(struct.cef_v8handler_t)

    # `raw_arg_indices={4, 5}` is important. `cef_capi.handler()` decorator automatically dereferences
    # pointer args by `.contents` property. `raw_arg_indices` avoids the behavior.
    # To be sure, index 0 arg (self) is ignored by default.
    @handler(v8handler, raw_arg_indices={4, 5})
    def execute(
            name: cef_string_t,
            object: struct.cef_v8value_t,
            arguments_count: int,
            arguments: ctypes._Pointer,  # ctypes.POINTER(ctypes.POINTER(struct.cef_v8value_t))
            retval: ctypes._Pointer,  # ctypes.POINTER(ctypes.POINTER(struct.cef_v8value_t))
            exception: cef_string_t):
        '''
        Handle execution of the function identified by |name|. |object| is the
        receiver ('this' object) of the function. |arguments| is the list of
        arguments passed to the function. If execution succeeds set |retval| to
        the function return value. If execution fails set |exception| to the
        exception that will be thrown. Return true (1) if execution was handled.

        CAUTION: Python debugger cannot make a breakpoint in this handler.
        '''
        fn = decode_cef_string(name)
        match fn:
            case 'Foo':
                print('Foo() called.')
                if arguments_count != 1:
                    # Never occurs
                    cef_string_ctor('Foo() arg should be one.', exception)
                else:
                    a: struct.cef_v8value_t = arguments[0].contents
                    if not bool(a) or not a.is_string(a):
                        cef_string_ctor('Foo() arg should be string.', exception)
                    else:
                        # get_string_value() returns userfree instance pointer.
                        s = decode_cef_string(a.get_string_value(a), free_after_decode=True)
                        if not s.startswith('x'):
                            cef_string_ctor('Foo() arg should start with "x".', exception)
                        else:
                            print(f'Foo() called with right arg "{s}".')
                            retval[0] = header.cef_v8value_create_string(cef_string_ctor('foo'))
            case _:
                # Never occurs
                print('Unknown function called.')
                cef_string_ctor('Unknown function called.', exception)
        return 1

    @handler(app)
    def get_render_process_handler():
        '''
        Return the handler for functionality specific to the render process. This
        function is called on the render process main thread.
        '''
        # print('get_render_process_handler')
        render_process_handler = base_ctor(struct.cef_render_process_handler_t)

        @handler(render_process_handler)
        def on_web_kit_initialized(*_):
            '''
            Called after WebKit has been initialized.
            '''
            print('on_web_kit_initialized')
            # Register a new V8 extension with the specified JavaScript extension code and
            # handler. Functions implemented by the handler are prototyped using the
            # keyword 'native'. The calling of a native function is restricted to the
            # scope in which the prototype of the native function is defined. This
            # function may only be called on the render process main thread.
            header.cef_register_extension(
                cef_string_ctor('v8/test_extension'),
                cef_string_ctor('''
                    var example = {};
                    (function(){
                        example.foo = function(x){
                            native function Foo(x);
                            return Foo(x);
                        };
                    })();
                '''), v8handler)
            return 0

        return render_process_handler

    header.cef_initialize(main_args, settings, app, None)

    # Given cef_browser_t instance of on_loading_state_change() / on_load_error().
    saved_browser: struct.cef_browser_t | None = None

    @task_factory
    def exit_app():
        # Important note:
        #   Do not close browser nor exit app from OnLoadingStateChange
        #   OnLoadError or OnPaint events. Closing browser during these
        #   events may result in unexpected behavior. Use cef.PostTask
        #   function to call exit_app from these events.
        print("exit_app")

        if saved_browser is None:
            # Never occurs
            raise Exception('saved_browser is None.')

        # `saved_browser.get_host()` returns int (memory address), not ctypes.Structure.
        browser_host = cef_pointer_to_struct(
            saved_browser.get_host(saved_browser),
            struct.cef_browser_host_t)
        browser_host.close_browser(browser_host, 0)

    @task_factory
    def execute_bar():
        '''
        Executes `example.bar()` from Python.
        '''
        print("execute_bar in")

        if saved_browser is None:
            # Never occurs
            raise Exception('saved_browser is None.')

        frame = cef_pointer_to_struct(
            saved_browser.get_main_frame(saved_browser),
            struct.cef_frame_t)
        frame.execute_java_script(
            frame,
            cef_string_ctor('example.bar("x from javascript.py:execute_bar()");'),
            None,
            0
        )
        print("execute_bar out")
        # Give a second to execute JavaScript.
        header.cef_post_delayed_task(header.TID_UI, exit_app(), 1000)

    client = client_ctor()

    # Render handler
    @handler(client)
    def get_render_handler(*_):
        '''
        Return the handler for off-screen rendering events.
        Windowless rendering requires a CefRenderHandler implementation
        '''
        render_handler = base_ctor(struct.cef_render_handler_t)

        @handler(render_handler)
        def get_view_rect(
                browser: struct.cef_browser_t,
                rect: struct.cef_rect_t):
            '''
            Called to retrieve the view rectangle in screen DIP coordinates. This
            function must always provide a non-NULL rectangle.
            '''
            # print('get_view_rect')
            rect.x = 0
            rect.y = 0
            rect.width = VIEWPORT_SIZE[0]
            rect.height = VIEWPORT_SIZE[1]
            return 1

        return render_handler

    @handler(client)
    def get_load_handler(*_):
        '''
        Return the handler for browser load status events.
        '''
        load_handler = base_ctor(struct.cef_load_handler_t)

        @handler(load_handler)
        def on_loading_state_change(
                browser: struct.cef_browser_t,
                is_loading: int,
                can_go_back: int,
                can_go_forward: int):
            '''
            Called when the loading state has changed. This callback will be executed
            twice -- once when loading is initiated either programmatically or by user
            action, and once when loading is terminated due to completion,
            cancellation of failure. It will be called before any calls to OnLoadStart
            and after all calls to OnLoadError and/or OnLoadEnd.
            '''
            nonlocal saved_browser
            print('on_loading_state_change')
            if not is_loading:
                # Loading is complete
                print("Web page loading is complete")
                saved_browser = browser
                header.cef_post_delayed_task(header.TID_UI, execute_bar(), 1000)

        @handler(load_handler)
        def on_load_error(
                browser: struct.cef_browser_t,
                frame: struct.cef_frame_t,
                error_code: int,
                error_text: cef_string_t,
                failed_url: cef_string_t):
            ''''
            Called when a navigation fails or is canceled. This function may be called
            by itself if before commit or in combination with OnLoadStart/OnLoadEnd if
            after commit. |errorCode| is the error code number, |errorText| is the
            error text and |failedUrl| is the URL that failed to load. See
            net\base\net_error_list.h for complete descriptions of the error codes.
            '''
            nonlocal saved_browser
            print('on_load_error')
            if not frame.is_main(frame):
                # We are interested only in loading main url.
                # Ignore any errors during loading of other frames.
                return
            print(f"ERROR: Failed to load url: {failed_url}")
            print(f"Error code: {error_code}")
            # See comments in exit_app() why cef_post_task must be used
            saved_browser = browser
            header.cef_post_task(header.TID_UI, exit_app())

        return load_handler

    window_info = struct.cef_window_info_t()
    window_info.windowless_rendering_enabled = 1
    window_info.window_name = cef_string_ctor("cef-capi-py JavaScript example")

    browser_settings = size_ctor(struct.cef_browser_settings_t)

    header.cef_browser_host_create_browser(
        window_info,
        client,
        cef_string_ctor(url),
        browser_settings,
        None,
        None
    )

    header.cef_run_message_loop()

    header.cef_shutdown()


if __name__ == '__main__':
    main()

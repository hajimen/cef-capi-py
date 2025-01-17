import faulthandler
faulthandler.enable()
import win32con
from cef_capi import cef_string_ctor, size_ctor, __version__
import cef_capi.win_amd64.header as header
import cef_capi.win_amd64.struct as struct
from cef_capi.app_client import client_ctor, app_ctor, settings_main_args_ctor


def main():
    '''
    We are going to see how to show Chromium-like window app.
    '''
    print(f"CEF version: {__version__}")

    app = app_ctor()

    settings, main_args = settings_main_args_ctor()
    settings.log_severity = struct.LOGSEVERITY_WARNING  # Show only warnings/errors
    settings.no_sandbox = 1

    print("cef_initialize")
    header.cef_initialize(main_args, settings, app, None)

    # GUI settings
    window_info = struct.cef_window_info_t()
    window_info.style = win32con.WS_OVERLAPPEDWINDOW | win32con.WS_CLIPCHILDREN | win32con.WS_CLIPSIBLINGS | win32con.WS_VISIBLE
    window_info.parent_window = None
    window_info.x = win32con.CW_USEDEFAULT
    window_info.y = win32con.CW_USEDEFAULT
    window_info.width = win32con.CW_USEDEFAULT
    window_info.height = win32con.CW_USEDEFAULT
    window_info.window_name = cef_string_ctor("cef-capi-py example")

    cef_url = cef_string_ctor("https://www.google.com/")

    browser_settings = size_ctor(struct.cef_browser_settings_t)

    client = client_ctor()

    # Create browser asynchronously. There is also a
    # synchronous version of this function available.
    print("cef_browser_host_create_browser")
    header.cef_browser_host_create_browser(
        window_info,
        client,
        cef_url,
        browser_settings,
        None,
        None
    )

    # Message loop. There is also cef_do_message_loop_work()
    # that allow for integrating with existing message loops.
    # On Windows for best performance you should set
    # cef_settings_t.multi_threaded_message_loop to true.
    # Note however that when you do that CEF UI thread is no
    # more application main thread and using CEF API is more
    # difficult and require using functions like cef_post_task
    # for running tasks on CEF UI thread.
    print("cef_run_message_loop")
    header.cef_run_message_loop()

    print("cef_shutdown")
    header.cef_shutdown()


if __name__ == '__main__':
    main()

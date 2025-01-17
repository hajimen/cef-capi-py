import faulthandler
faulthandler.enable()
import ctypes
from PIL import Image as PilImageModule
from cef_capi import cef_string_ctor, size_ctor, base_ctor, task_factory, handler, header, struct, decode_cef_string, cef_string_t, __version__
from cef_capi.app_client import client_ctor, app_ctor, settings_main_args_ctor


VIEWPORT_SIZE = (800, 600)
SCREENSHOT_PATH = 'screenshot.png'
URL = "https://www.google.com/ncr"


def main():
    '''
    We are going to see how to take a screenshot of a web page with CEF.
    '''
    print(f"CEF version: {__version__}")

    app = app_ctor()

    settings, main_args = settings_main_args_ctor()
    settings.log_severity = struct.LOGSEVERITY_WARNING  # Show only warnings/errors
    settings.no_sandbox = 1
    settings.windowless_rendering_enabled = 1

    header.cef_initialize(main_args, settings, app, None)

    client = client_ctor()

    # Given bitmap of on_paint() handler.
    saved_buffer: ctypes.c_void_p | None = None

    @handler(client)
    def get_render_handler(*_):
        '''
        Return the handler for off-screen rendering events.
        Windowless rendering requires a CefRenderHandler implementation
        '''
        render_handler = base_ctor(struct.cef_render_handler_t)

        @handler(render_handler)
        def on_paint(
                browser: struct.cef_browser_t,
                element_type: int,
                dirty_rects_count: int,
                dirty_rects: struct.cef_rect_t,
                buffer: ctypes.c_void_p,
                width: int,
                height: int):
            '''
            Called when an element should be painted. Pixel values passed to this
            function are scaled relative to view coordinates based on the value of
            CefScreenInfo.device_scale_factor returned from GetScreenInfo. |type|
            indicates whether the element is the view or the popup widget. |buffer|
            contains the pixel data for the whole image. |dirtyRects| contains the set
            of rectangles in pixel coordinates that need to be repainted. |buffer|
            will be |width|*|height|*4 bytes in size and represents a BGRA image with
            an upper-left origin. This function is only called when
            cef_window_tInfo::shared_texture_enabled is set to false (0).
            '''
            nonlocal saved_buffer
            print('on_paint')
            if element_type == header.PET_VIEW:
                saved_buffer = buffer

        @handler(render_handler)
        def get_view_rect(
                browser: struct.cef_browser_t,
                rect: struct.cef_rect_t):
            '''
            Called to retrieve the view rectangle in screen DIP coordinates. This
            function must always provide a non-NULL rectangle.
            '''
            print('get_view_rect')
            rect.x = 0
            rect.y = 0
            rect.width = VIEWPORT_SIZE[0]
            rect.height = VIEWPORT_SIZE[1]
            return 1

        return render_handler

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
            raise Exception('saved_browser is None.')
        browser_host_p = ctypes.cast(
            saved_browser.get_host(saved_browser),
            ctypes.POINTER(struct.cef_browser_host_t))
        browser_host_p.contents.close_browser(browser_host_p, 0)

    MAX_RETRY = 4

    @task_factory
    def save_screenshot(retry_count=0):  # The arg from ctor
        print('save_screenshot')
        if saved_buffer is None:
            if retry_count < MAX_RETRY:
                print('save_screenshot retry...')
                header.cef_post_delayed_task(
                    header.TID_UI,
                    save_screenshot(retry_count + 1),  # The arg to function
                    500)
                retry_count += 1
                return
            else:
                raise Exception('save_screenshot timeout.')
        bstr = ctypes.string_at(saved_buffer, VIEWPORT_SIZE[0] * VIEWPORT_SIZE[1] * 4)
        pil_image = PilImageModule.frombytes('RGBA', (VIEWPORT_SIZE[0], VIEWPORT_SIZE[1]), bstr, 'raw', 'BGRA')
        pil_image.save(SCREENSHOT_PATH)
        print(f"Screenshot image saved: {SCREENSHOT_PATH}")
        # See comments in exit_app() why post_task must be used
        header.cef_post_task(header.TID_UI, exit_app())

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
                print("Web page loading is complete")
                # Give up to 200 ms for the OnPaint call. Most of the time
                # it is already called, but sometimes it may be called later.
                # In the case, `save_screenshot` retries.
                saved_browser = browser
                header.cef_post_delayed_task(header.TID_UI, save_screenshot(), 200)

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
            print(f"ERROR: Failed to load url: {decode_cef_string(failed_url)}")
            print(f"Error code: {error_code}")
            # See comments in exit_app() why cef_post_task must be used
            saved_browser = browser
            header.cef_post_task(header.TID_UI, exit_app())
        
        return load_handler

    window_info = struct.cef_window_info_t()
    window_info.windowless_rendering_enabled = 1
    window_info.window_name = cef_string_ctor("cef-capi-py screenshot example")

    browser_settings = size_ctor(struct.cef_browser_settings_t)

    header.cef_browser_host_create_browser(
        window_info,
        client,
        cef_string_ctor(URL),
        browser_settings,
        None,
        None
    )

    header.cef_run_message_loop()

    header.cef_shutdown()


if __name__ == '__main__':
    main()

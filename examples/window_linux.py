import faulthandler
faulthandler.enable()
import ctypes
import sysconfig
import signal
from cef_capi import cef_string_ctor, size_ctor, struct, header, __version__
match sysconfig.get_platform():
    case 'linux-aarch64':
        import examples.linux_aarch64.gtk_x_header as gtk_x_header
    case 'linux-x86_64':
        import examples.linux_x86_64.gtk_x_header as gtk_x_header
    case _:
        raise Exception('unknown platform')
from cef_capi.app_client import client_ctor, app_ctor, settings_main_args_ctor


WIDGET = None


def fix_default_x11_visual(widget):
    # GTK+ > 3.15.1 uses an X11 visual optimized for GTK+'s OpenGL stuff
    # since revid dae447728d: https://github.com/GNOME/gtk/commit/dae447728d
    # However, it breaks CEF: https://github.com/cztomczak/cefcapi/issues/9
    # Let's use the default X11 visual instead of the GTK's blessed one.
    # Ref: https://github.com/chromiumembedded/cef/blob/2197e2d63cf5e5b3d20c26949e24bb7f886cbf9e/tests/cefclient/browser/root_window_gtk.cc#L31
    screen = gtk_x_header.gdk_screen_get_default()
    visuals = gtk_x_header.gdk_screen_list_visuals(screen)
    x11_screen = ctypes.cast(screen, ctypes.POINTER(gtk_x_header.GdkX11Screen))
    default_xvisual = gtk_x_header.XDefaultVisual(
        gtk_x_header.gdk_x11_display_get_xdisplay(
            gtk_x_header.gdk_screen_get_display(x11_screen)),
        gtk_x_header.gdk_x11_screen_get_screen_number(x11_screen))
    cursor = visuals
    while bool(cursor):
        visual = ctypes.cast(cursor.contents.data, ctypes.POINTER(gtk_x_header.GdkX11Visual))
        if default_xvisual.contents.visualid == gtk_x_header.gdk_x11_visual_get_xvisual(visual).contents.visualid:
            gtk_x_header.gtk_widget_set_visual(widget, visual)
            break
        cursor = cursor.contents.next
    gtk_x_header.g_list_free(visuals)


def destroy_widget(user_data):
    print("destroy_widget")
    gtk_x_header.gtk_widget_destroy(WIDGET)
    return 0


def app_terminate_unix_signal(*_):
    print("app_terminate_unix_signal")
    gtk_x_header.g_main_context_invoke(None, gtk_x_header.GSourceFunc(destroy_widget), None)


def create_gtk_window(title: str, width: int, height: int):
    print("create_gtk_window")
    global WIDGET

    # Create window.
    WIDGET = gtk_x_header.gtk_window_new(gtk_x_header.GTK_WINDOW_TOPLEVEL)
    window = ctypes.cast(WIDGET, ctypes.POINTER(gtk_x_header.GtkWindow))

    # Default size.
    gtk_x_header.gtk_window_set_default_size(window, width, height)

    # Center.
    gtk_x_header.gtk_window_set_position(window, gtk_x_header.GTK_WIN_POS_CENTER)
    
    # Title.
    title_cp = ctypes.create_string_buffer(title.encode())
    gtk_x_header.gtk_window_set_title(window, title_cp)
    
    # CEF requires a container. Embedding browser in a top
    # level window fails.
    vbox = gtk_x_header.gtk_box_new(gtk_x_header.GTK_ORIENTATION_VERTICAL, 0)
    container = ctypes.cast(WIDGET, ctypes.POINTER(gtk_x_header.GtkContainer))
    gtk_x_header.gtk_container_add(container, vbox)
    
    fix_default_x11_visual(WIDGET)

    # Show.
    gtk_x_header.gtk_widget_show_all(WIDGET)

    # Flush the display to make sure the underlying X11 window gets created
    # immediately.
    gdk_window = gtk_x_header.gtk_widget_get_window(WIDGET)
    display = gtk_x_header.gdk_window_get_display(gdk_window)
    gtk_x_header.gdk_display_flush(display)

    return vbox


def x11_error_handler(_, __):
    print("x11_error_handler")
    return 0


def x11_io_error_handler(_):
    print("x11_io_error_handler")
    return 0


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
    gtk_x_header.gtk_init(None, None)
    gtk_window = create_gtk_window("cef_capi example", 800, 600)
    window_info = struct.cef_window_info_t()
    window_info.parent_window = gtk_x_header.gdk_x11_window_get_xid(
        gtk_x_header.gtk_widget_get_window(gtk_window))

    # UNIX signals and X error handler
    signal.signal(signal.SIGINT, app_terminate_unix_signal)
    signal.signal(signal.SIGTERM, app_terminate_unix_signal)
    gtk_x_header.XSetErrorHandler(gtk_x_header.XErrorHandler(x11_error_handler))
    gtk_x_header.XSetIOErrorHandler(gtk_x_header.XIOErrorHandler(x11_io_error_handler))

    window_info.window_name = cef_string_ctor("cef-capi-py example")

    cef_url = cef_string_ctor("https://www.google.com/ncr")

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

    return 0


if __name__ == '__main__':
    main()

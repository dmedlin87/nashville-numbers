"""Dev helper: starts the Nashville Numbers GUI HTTP server on a fixed port without opening a window."""
import sys
sys.path.insert(0, "src")

from nashville_numbers.gui import GuiApp


class DevApp(GuiApp):
    """Subclass that accepts localhost origin for preview tools."""

    def is_allowed_origin(self, origin, referer):
        # Accept both 127.0.0.1 and localhost in dev mode
        if origin and ("127.0.0.1" in origin or "localhost" in origin):
            return True
        if referer and ("127.0.0.1" in referer or "localhost" in referer):
            return True
        return super().is_allowed_origin(origin, referer)


app = DevApp()
port = 8765
server, url, thread = app.start_server(port)
# Also set localhost variant so session cookies work
app._base_url = f"http://localhost:{port}"
print(f"Dev server running at {url}")
print(f"Also accepting http://localhost:{port}")

try:
    while True:
        app.create_event().wait(3600)
except KeyboardInterrupt:
    print("\nStopped.")
finally:
    app.cleanup(server, thread)

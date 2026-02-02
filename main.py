"""PC Monitor - System tray application with real-time hardware monitoring dashboard."""

import threading
import webbrowser
import sys
import os
import subprocess
import atexit
import time

# Add the project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# LibreHardwareMonitor path
LHM_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tools", "LibreHardwareMonitor", "LibreHardwareMonitor.exe")

import pystray
from PIL import Image, ImageDraw
import uvicorn

# Server configuration
HOST = "127.0.0.1"
PORT = 8080
BASE_URL = f"http://{HOST}:{PORT}"

# Global server instance
server = None
server_thread = None


def create_icon_image():
    """Create a simple monitor icon for the system tray."""
    # Create a 64x64 image with a monitor/chart icon
    size = 64
    image = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # Draw monitor frame
    margin = 4
    draw.rectangle(
        [margin, margin, size - margin, size - margin - 8],
        outline='#00ff88',
        width=3
    )

    # Draw stand
    stand_width = 16
    stand_left = (size - stand_width) // 2
    draw.rectangle(
        [stand_left, size - margin - 8, stand_left + stand_width, size - margin],
        fill='#00ff88'
    )

    # Draw bar chart inside monitor
    bar_bottom = size - margin - 14
    bar_width = 8
    bars = [
        (14, 20),   # x, height
        (26, 30),
        (38, 25),
    ]

    for x, height in bars:
        draw.rectangle(
            [x, bar_bottom - height, x + bar_width, bar_bottom],
            fill='#00ff88'
        )

    return image


def is_lhm_running():
    """Check if LibreHardwareMonitor is already running."""
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq LibreHardwareMonitor.exe"],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        return "LibreHardwareMonitor.exe" in result.stdout
    except Exception:
        return False


def start_lhm():
    """Start LibreHardwareMonitor in the background with admin privileges."""
    if not os.path.exists(LHM_PATH):
        print(f"LibreHardwareMonitor not found at: {LHM_PATH}")
        return

    # Don't start if already running
    if is_lhm_running():
        print("LibreHardwareMonitor already running")
        return

    try:
        import ctypes
        # Use ShellExecute to run as admin (will show UAC prompt)
        # Pass /minimizeToTray to start in system tray
        # SW_HIDE (0) to not show a window
        result = ctypes.windll.shell32.ShellExecuteW(
            None,
            "runas",  # Request elevation
            LHM_PATH,
            "/minimizeToTray",  # Start minimized to system tray
            os.path.dirname(LHM_PATH),
            0  # SW_HIDE
        )
        # ShellExecuteW returns > 32 on success
        if result <= 32:
            print(f"Failed to start LibreHardwareMonitor, error code: {result}")
    except Exception as e:
        print(f"Could not start LibreHardwareMonitor: {e}")


def stop_lhm():
    """Stop LibreHardwareMonitor."""
    try:
        subprocess.run(
            ["taskkill", "/F", "/IM", "LibreHardwareMonitor.exe"],
            capture_output=True,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
    except Exception:
        pass


def open_dashboard():
    """Open the full dashboard in the default browser."""
    webbrowser.open(BASE_URL)


def exit_app(icon: pystray.Icon):
    """Exit the application and stop the server."""
    stop_lhm()
    icon.stop()
    if server:
        server.should_exit = True


def run_server():
    """Run the uvicorn server in a separate thread."""
    global server

    config = uvicorn.Config(
        "monitor.server:app",
        host=HOST,
        port=PORT,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)
    server.run()


def setup_tray(icon: pystray.Icon):
    """Called when the tray icon is ready."""
    icon.visible = True


def main():
    """Main entry point."""
    global server_thread

    # Register cleanup on exit
    atexit.register(stop_lhm)

    # Start LibreHardwareMonitor for fan/sensor data
    start_lhm()

    # Wait for LHM to initialize (up to 10 seconds)
    for _ in range(20):
        if is_lhm_running():
            time.sleep(1)  # Give it a moment to initialize WMI
            break
        time.sleep(0.5)

    # Start the web server in a background thread
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()

    # Create the system tray icon
    icon_image = create_icon_image()

    menu = pystray.Menu(
        pystray.MenuItem("Open Dashboard", open_dashboard, default=True),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Exit", exit_app),
    )

    icon = pystray.Icon(
        name="PC Monitor",
        icon=icon_image,
        title="PC Monitor",
        menu=menu,
    )

    # Run the tray icon (this blocks)
    icon.run(setup_tray)


if __name__ == "__main__":
    main()

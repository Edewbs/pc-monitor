"""FastAPI web server with WebSocket support for real-time stats."""

import asyncio
import json
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, status
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .hardware import get_all_stats

# Path to static files
STATIC_DIR = Path(__file__).parent.parent / "static"

# Connected WebSocket clients
connected_clients: Set[WebSocket] = set()

# Connection rate limiting
MAX_CONNECTIONS = 10

# Background task for broadcasting stats
broadcast_task = None


async def async_ping(host: str = "8.8.8.8") -> dict:
    """Measure network latency asynchronously."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "ping", "-n", "1", "-w", "1000", host,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=2.0)

        if proc.returncode == 0:
            output = stdout.decode('utf-8', errors='ignore')
            match = re.search(r'time[=<](\d+)ms', output, re.IGNORECASE)
            if match:
                return {'ping': int(match.group(1)), 'host': host, 'success': True}

        return {'ping': None, 'host': host, 'success': False}
    except asyncio.TimeoutError:
        return {'ping': None, 'host': host, 'success': False, 'error': 'timeout'}
    except Exception as e:
        return {'ping': None, 'host': host, 'success': False, 'error': str(e)}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown events."""
    global broadcast_task
    # Startup
    broadcast_task = asyncio.create_task(broadcast_stats())
    yield
    # Shutdown
    if broadcast_task:
        broadcast_task.cancel()
        try:
            await broadcast_task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="PC Monitor", lifespan=lifespan)


@app.get("/")
async def get_dashboard():
    """Serve the main dashboard."""
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/stats")
async def get_stats():
    """Get current hardware stats (REST endpoint)."""
    return get_all_stats()


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time stats with connection limiting."""
    # Rate limiting: reject if too many connections
    if len(connected_clients) >= MAX_CONNECTIONS:
        await websocket.close(code=status.WS_1013_TRY_AGAIN_LATER)
        return

    await websocket.accept()
    connected_clients.add(websocket)

    try:
        while True:
            # Keep connection alive, listen for messages
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
    except WebSocketDisconnect:
        pass
    finally:
        connected_clients.discard(websocket)


async def broadcast_stats():
    """Background task to broadcast stats to all connected clients."""
    # Track previous values for rate calculations
    prev_disk = None
    prev_network = None
    prev_time = None

    while True:
        try:
            # Get hardware stats (sync) and ping (async) concurrently
            stats = get_all_stats()

            # Replace sync ping with async ping
            ping_task = asyncio.create_task(async_ping())

            current_time = asyncio.get_event_loop().time()

            # Calculate disk rates
            if prev_disk and prev_time:
                time_delta = current_time - prev_time
                if time_delta > 0 and 'read_bytes' in stats['disk']:
                    read_rate = (stats['disk']['read_bytes'] - prev_disk['read_bytes']) / time_delta
                    write_rate = (stats['disk']['write_bytes'] - prev_disk['write_bytes']) / time_delta
                    stats['disk']['read_rate'] = read_rate / (1024 * 1024)  # MB/s
                    stats['disk']['write_rate'] = write_rate / (1024 * 1024)  # MB/s

            # Calculate network rates
            if prev_network and prev_time:
                time_delta = current_time - prev_time
                if time_delta > 0 and 'bytes_sent' in stats['network']:
                    upload_rate = (stats['network']['bytes_sent'] - prev_network['bytes_sent']) / time_delta
                    download_rate = (stats['network']['bytes_recv'] - prev_network['bytes_recv']) / time_delta
                    stats['network']['upload_rate'] = upload_rate / (1024 * 1024)  # MB/s
                    stats['network']['download_rate'] = download_rate / (1024 * 1024)  # MB/s

            # Store current values for next iteration
            prev_disk = stats['disk'].copy() if 'read_bytes' in stats.get('disk', {}) else None
            prev_network = stats['network'].copy() if 'bytes_sent' in stats.get('network', {}) else None
            prev_time = current_time

            # Wait for async ping result
            stats['ping'] = await ping_task

            # Broadcast to all connected clients
            if connected_clients:
                # Safely serialize to JSON with error handling
                try:
                    message = json.dumps(stats, default=str)
                except (TypeError, ValueError) as json_err:
                    print(f"JSON serialization error: {json_err}")
                    await asyncio.sleep(0.5)
                    continue

                disconnected = set()

                for client in connected_clients:
                    try:
                        await client.send_text(message)
                    except Exception:
                        disconnected.add(client)

                # Remove disconnected clients
                connected_clients.difference_update(disconnected)

            await asyncio.sleep(0.5)  # Update every 500ms

        except asyncio.CancelledError:
            raise  # Re-raise to allow clean shutdown
        except Exception as e:
            print(f"Error in broadcast_stats: {e}")
            await asyncio.sleep(1)


# Mount static files (CSS, JS)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

"""Hardware monitoring module for collecting system statistics."""

import psutil
import subprocess
import re
import time
from typing import Any

# Try to import WMI for detailed hardware info on Windows
try:
    import wmi
    WMI_AVAILABLE = True
except ImportError:
    WMI_AVAILABLE = False

# Try to import GPU libraries
try:
    import pynvml
    PYNVML_AVAILABLE = True
except ImportError:
    PYNVML_AVAILABLE = False

try:
    import GPUtil
    GPUTIL_AVAILABLE = True
except ImportError:
    GPUTIL_AVAILABLE = False


class HardwareMonitor:
    """Collects hardware statistics from the system."""

    def __init__(self):
        self._nvml_initialized = False
        self._init_nvml()
        self._memory_hardware_info = None
        self._init_memory_hardware_info()
        self._cpu_hardware_info = None
        self._init_cpu_hardware_info()
        # Fan stats cache (WMI queries are expensive)
        self._fan_cache = None
        self._fan_cache_time = 0
        self._fan_cache_ttl = 1.5  # Cache for 1.5 seconds

    def _init_memory_hardware_info(self):
        """Initialize static memory hardware info (speed, type, slots) via WMI."""
        if not WMI_AVAILABLE:
            self._memory_hardware_info = {'available': False}
            return

        try:
            w = wmi.WMI()
            memory_modules = w.Win32_PhysicalMemory()

            if not memory_modules:
                self._memory_hardware_info = {'available': False}
                return

            slots = []
            total_speed = 0
            memory_type_code = None

            # Memory type mapping (SMBIOS memory type)
            memory_types = {
                0: 'Unknown',
                1: 'Other',
                2: 'DRAM',
                3: 'Synchronous DRAM',
                4: 'Cache DRAM',
                5: 'EDO',
                6: 'EDRAM',
                7: 'VRAM',
                8: 'SRAM',
                9: 'RAM',
                10: 'ROM',
                11: 'Flash',
                12: 'EEPROM',
                13: 'FEPROM',
                14: 'EPROM',
                15: 'CDRAM',
                16: '3DRAM',
                17: 'SDRAM',
                18: 'SGRAM',
                19: 'RDRAM',
                20: 'DDR',
                21: 'DDR2',
                22: 'DDR2 FB-DIMM',
                24: 'DDR3',
                26: 'DDR4',
                34: 'DDR5',
            }

            for module in memory_modules:
                capacity_gb = int(module.Capacity) / (1024 ** 3) if module.Capacity else 0
                speed = module.Speed or 0
                configured_speed = getattr(module, 'ConfiguredClockSpeed', None) or speed
                mem_type = module.SMBIOSMemoryType or module.MemoryType or 0
                manufacturer = module.Manufacturer or 'Unknown'
                part_number = (module.PartNumber or '').strip()
                slot = module.DeviceLocator or 'Unknown'

                slots.append({
                    'slot': slot,
                    'capacity_gb': round(capacity_gb, 1),
                    'speed': configured_speed or speed,
                    'manufacturer': manufacturer,
                    'part_number': part_number,
                    'type_code': mem_type,
                })

                total_speed = max(total_speed, configured_speed or speed)
                if memory_type_code is None:
                    memory_type_code = mem_type

            memory_type = memory_types.get(memory_type_code, 'Unknown')

            # Get total slots (including empty)
            try:
                memory_array = w.Win32_PhysicalMemoryArray()
                total_slots = sum(arr.MemoryDevices or 0 for arr in memory_array)
            except Exception:
                total_slots = len(slots)

            self._memory_hardware_info = {
                'available': True,
                'speed': total_speed,
                'type': memory_type,
                'type_code': memory_type_code,
                'slots_used': len(slots),
                'slots_total': total_slots,
                'modules': slots,
            }

        except Exception as e:
            self._memory_hardware_info = {'available': False, 'error': str(e)}

    def _init_cpu_hardware_info(self):
        """Initialize static CPU hardware info via WMI."""
        if not WMI_AVAILABLE:
            self._cpu_hardware_info = {'available': False}
            return

        try:
            w = wmi.WMI()
            cpus = w.Win32_Processor()

            if not cpus:
                self._cpu_hardware_info = {'available': False}
                return

            cpu = cpus[0]  # Get first CPU

            # Clean up CPU name
            name = cpu.Name or 'Unknown CPU'
            name = ' '.join(name.split())  # Remove extra whitespace

            # Cache sizes in KB
            l2_cache = cpu.L2CacheSize or 0
            l3_cache = cpu.L3CacheSize or 0

            self._cpu_hardware_info = {
                'available': True,
                'name': name,
                'max_clock': cpu.MaxClockSpeed,
                'l2_cache_kb': l2_cache,
                'l3_cache_kb': l3_cache,
                'socket': cpu.SocketDesignation,
            }

        except Exception as e:
            self._cpu_hardware_info = {'available': False, 'error': str(e)}

    def _init_nvml(self):
        """Initialize NVIDIA Management Library."""
        if PYNVML_AVAILABLE and not self._nvml_initialized:
            try:
                pynvml.nvmlInit()
                self._nvml_initialized = True
            except Exception:
                self._nvml_initialized = False

    def _shutdown_nvml(self):
        """Shutdown NVIDIA Management Library."""
        if self._nvml_initialized:
            try:
                pynvml.nvmlShutdown()
            except Exception:
                pass
            self._nvml_initialized = False

    def get_cpu_stats(self) -> dict[str, Any]:
        """Get CPU statistics."""
        try:
            cpu_percent = psutil.cpu_percent(interval=None)
            cpu_per_core = psutil.cpu_percent(interval=None, percpu=True)
            cpu_freq = psutil.cpu_freq()

            # Try to get CPU temperature
            cpu_temp = self._get_cpu_temperature()

            result = {
                'usage': cpu_percent,
                'per_core': cpu_per_core,
                'frequency': cpu_freq.current if cpu_freq else None,
                'frequency_max': cpu_freq.max if cpu_freq else None,
                'temperature': cpu_temp,
                'cores': psutil.cpu_count(logical=False),
                'threads': psutil.cpu_count(logical=True),
            }

            # Add static hardware info
            if self._cpu_hardware_info and self._cpu_hardware_info.get('available'):
                result['name'] = self._cpu_hardware_info.get('name')
                result['max_clock'] = self._cpu_hardware_info.get('max_clock')
                result['l2_cache_kb'] = self._cpu_hardware_info.get('l2_cache_kb')
                result['l3_cache_kb'] = self._cpu_hardware_info.get('l3_cache_kb')
                result['socket'] = self._cpu_hardware_info.get('socket')

            return result
        except Exception as e:
            return {'error': str(e)}

    def _get_cpu_temperature(self) -> float | None:
        """Get CPU temperature using multiple methods."""
        # Method 1: Try psutil (works on Linux)
        try:
            temps = psutil.sensors_temperatures()
            if temps:
                for key in ['coretemp', 'cpu_thermal', 'k10temp', 'zenpower']:
                    if key in temps and temps[key]:
                        return temps[key][0].current
        except Exception:
            pass

        # Method 2: Try WMI on Windows (MSAcpi_ThermalZoneTemperature)
        if WMI_AVAILABLE:
            try:
                w = wmi.WMI(namespace="root\\wmi")
                temperature_info = w.MSAcpi_ThermalZoneTemperature()
                if temperature_info:
                    # Temperature is in tenths of Kelvin, convert to Celsius
                    temp_kelvin = temperature_info[0].CurrentTemperature / 10.0
                    temp_celsius = temp_kelvin - 273.15
                    if 0 < temp_celsius < 150:  # Sanity check
                        return round(temp_celsius, 1)
            except Exception:
                pass

            # Method 3: Try Open Hardware Monitor WMI interface (if installed)
            try:
                w = wmi.WMI(namespace="root\\OpenHardwareMonitor")
                sensors = w.Sensor()
                for sensor in sensors:
                    if sensor.SensorType == 'Temperature' and 'CPU' in sensor.Name:
                        return round(sensor.Value, 1)
            except Exception:
                pass

            # Method 4: Try LibreHardwareMonitor WMI interface (if installed)
            try:
                w = wmi.WMI(namespace="root\\LibreHardwareMonitor")
                sensors = w.Sensor()
                for sensor in sensors:
                    if sensor.SensorType == 'Temperature' and 'CPU' in sensor.Name:
                        return round(sensor.Value, 1)
            except Exception:
                pass

        return None

    def get_gpu_stats(self) -> dict[str, Any]:
        """Get GPU statistics using pynvml."""
        if not self._nvml_initialized:
            return self._get_gpu_stats_fallback()

        try:
            device_count = pynvml.nvmlDeviceGetCount()
            if device_count == 0:
                return {'available': False}

            # Get first GPU
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)

            # Get name
            name = pynvml.nvmlDeviceGetName(handle)
            if isinstance(name, bytes):
                name = name.decode('utf-8')

            # Get utilization
            util = pynvml.nvmlDeviceGetUtilizationRates(handle)

            # Get memory
            mem = pynvml.nvmlDeviceGetMemoryInfo(handle)

            # Get temperature
            temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)

            # Get clock speeds
            try:
                graphics_clock = pynvml.nvmlDeviceGetClockInfo(handle, pynvml.NVML_CLOCK_GRAPHICS)
                memory_clock = pynvml.nvmlDeviceGetClockInfo(handle, pynvml.NVML_CLOCK_MEM)
            except Exception:
                graphics_clock = None
                memory_clock = None

            # Get fan speed
            try:
                fan_speed = pynvml.nvmlDeviceGetFanSpeed(handle)
            except Exception:
                fan_speed = None

            # Get power
            try:
                power = pynvml.nvmlDeviceGetPowerUsage(handle) / 1000  # Convert to watts
                power_limit = pynvml.nvmlDeviceGetPowerManagementLimit(handle) / 1000
            except Exception:
                power = None
                power_limit = None

            return {
                'available': True,
                'name': name,
                'usage': util.gpu,
                'memory_used': mem.used / (1024 ** 3),  # GB
                'memory_total': mem.total / (1024 ** 3),  # GB
                'memory_percent': (mem.used / mem.total) * 100,
                'temperature': temp,
                'graphics_clock': graphics_clock,
                'memory_clock': memory_clock,
                'fan_speed': fan_speed,
                'power': power,
                'power_limit': power_limit,
            }
        except Exception as e:
            return self._get_gpu_stats_fallback()

    def _get_gpu_stats_fallback(self) -> dict[str, Any]:
        """Fallback GPU stats using GPUtil."""
        if not GPUTIL_AVAILABLE:
            return {'available': False}

        try:
            gpus = GPUtil.getGPUs()
            if not gpus:
                return {'available': False}

            gpu = gpus[0]
            return {
                'available': True,
                'name': gpu.name,
                'usage': gpu.load * 100,
                'memory_used': gpu.memoryUsed / 1024,  # GB
                'memory_total': gpu.memoryTotal / 1024,  # GB
                'memory_percent': (gpu.memoryUsed / gpu.memoryTotal) * 100 if gpu.memoryTotal else 0,
                'temperature': gpu.temperature,
                'graphics_clock': None,
                'memory_clock': None,
                'fan_speed': None,
                'power': None,
                'power_limit': None,
            }
        except Exception:
            return {'available': False}

    def get_memory_stats(self) -> dict[str, Any]:
        """Get RAM statistics."""
        try:
            mem = psutil.virtual_memory()
            swap = psutil.swap_memory()

            result = {
                'used': mem.used / (1024 ** 3),  # GB
                'total': mem.total / (1024 ** 3),  # GB
                'percent': mem.percent,
                'available': mem.available / (1024 ** 3),  # GB
                'cached': getattr(mem, 'cached', 0) / (1024 ** 3),  # GB (Linux)
                'buffers': getattr(mem, 'buffers', 0) / (1024 ** 3),  # GB (Linux)
                'swap_used': swap.used / (1024 ** 3),  # GB
                'swap_total': swap.total / (1024 ** 3),  # GB
                'swap_percent': swap.percent,
            }

            # Add hardware info (speed, type, slots)
            if self._memory_hardware_info and self._memory_hardware_info.get('available'):
                result['speed'] = self._memory_hardware_info.get('speed')
                result['type'] = self._memory_hardware_info.get('type')
                result['slots_used'] = self._memory_hardware_info.get('slots_used')
                result['slots_total'] = self._memory_hardware_info.get('slots_total')
                result['modules'] = self._memory_hardware_info.get('modules')

            return result
        except Exception as e:
            return {'error': str(e)}

    def get_disk_stats(self) -> dict[str, Any]:
        """Get disk I/O statistics."""
        try:
            disk_io = psutil.disk_io_counters()
            if disk_io:
                return {
                    'read_bytes': disk_io.read_bytes,
                    'write_bytes': disk_io.write_bytes,
                    'read_count': disk_io.read_count,
                    'write_count': disk_io.write_count,
                }
            return {'available': False}
        except Exception as e:
            return {'error': str(e)}

    def get_network_stats(self) -> dict[str, Any]:
        """Get network I/O statistics."""
        try:
            net_io = psutil.net_io_counters()

            # Calculate packet loss percentage
            total_packets = net_io.packets_sent + net_io.packets_recv
            total_errors = net_io.errin + net_io.errout + net_io.dropin + net_io.dropout
            packet_loss = (total_errors / total_packets * 100) if total_packets > 0 else 0

            return {
                'bytes_sent': net_io.bytes_sent,
                'bytes_recv': net_io.bytes_recv,
                'packets_sent': net_io.packets_sent,
                'packets_recv': net_io.packets_recv,
                'packets_dropped': net_io.dropin + net_io.dropout,
                'packets_errors': net_io.errin + net_io.errout,
                'packet_loss': packet_loss,
            }
        except Exception as e:
            return {'error': str(e)}

    def get_ping(self, host: str = "8.8.8.8") -> dict[str, Any]:
        """Measure network latency (ping) to a host."""
        try:
            # Use Windows ping command
            result = subprocess.run(
                ["ping", "-n", "1", "-w", "1000", host],
                capture_output=True,
                text=True,
                timeout=2
            )

            if result.returncode == 0:
                # Parse ping time from output (Windows format: "time=XXms" or "time<1ms")
                output = result.stdout
                match = re.search(r'time[=<](\d+)ms', output, re.IGNORECASE)
                if match:
                    ping_ms = int(match.group(1))
                    return {'ping': ping_ms, 'host': host, 'success': True}

            return {'ping': None, 'host': host, 'success': False}
        except subprocess.TimeoutExpired:
            return {'ping': None, 'host': host, 'success': False, 'error': 'timeout'}
        except Exception as e:
            return {'ping': None, 'host': host, 'success': False, 'error': str(e)}

    def get_top_processes(self, limit: int = 8) -> list[dict[str, Any]]:
        """Get top processes by CPU and memory usage."""
        try:
            num_cpus = psutil.cpu_count(logical=True) or 1
            processes = []
            for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
                try:
                    info = proc.info
                    # Normalize CPU percent so total across all processes <= 100%
                    # psutil reports per-core %, so divide by number of logical CPUs
                    cpu_normalized = (info['cpu_percent'] or 0) / num_cpus
                    processes.append({
                        'pid': info['pid'],
                        'name': info['name'],
                        'cpu_percent': cpu_normalized,
                        'memory_percent': info['memory_percent'] or 0,
                    })
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            # Sort by CPU usage
            processes.sort(key=lambda x: x['cpu_percent'], reverse=True)
            return processes[:limit]
        except Exception as e:
            return []

    def get_fan_stats(self) -> dict[str, Any]:
        """Get fan speed statistics with caching to reduce WMI overhead."""
        # Check cache first
        current_time = time.time()
        if self._fan_cache and (current_time - self._fan_cache_time) < self._fan_cache_ttl:
            return self._fan_cache

        fans = []
        fan_controls = {}  # Map fan name to control percentage
        lhm_available = False

        # Try LibreHardwareMonitor first (best data source)
        if WMI_AVAILABLE:
            try:
                lhm = wmi.WMI(namespace="root\\LibreHardwareMonitor")

                # First pass: collect control (percentage) values
                for sensor in lhm.Sensor():
                    if sensor.SensorType == 'Control':
                        name = sensor.Name
                        if name == 'Pump Fan':
                            name = 'Case Fan'
                        percent = int(sensor.Value) if sensor.Value else 0
                        fan_controls[name] = percent

                # Second pass: collect fan RPM and match with controls
                for sensor in lhm.Sensor():
                    if sensor.SensorType == 'Fan':
                        rpm = int(sensor.Value) if sensor.Value else 0
                        name = sensor.Name

                        # Rename "Pump Fan" to "Case Fan"
                        if name == 'Pump Fan':
                            name = 'Case Fan'

                        fan_type = 'gpu' if 'GPU' in name else 'system'
                        percent = fan_controls.get(name)

                        fans.append({
                            'name': name,
                            'percent': percent,
                            'rpm': rpm,
                            'type': fan_type
                        })
                        lhm_available = True
            except Exception:
                pass

            # Try OpenHardwareMonitor if LHM not available
            if not lhm_available:
                try:
                    ohm = wmi.WMI(namespace="root\\OpenHardwareMonitor")

                    # First pass: collect control values
                    for sensor in ohm.Sensor():
                        if sensor.SensorType == 'Control':
                            name = sensor.Name
                            if name == 'Pump Fan':
                                name = 'Case Fan'
                            percent = int(sensor.Value) if sensor.Value else 0
                            fan_controls[name] = percent

                    # Second pass: collect fan RPM
                    for sensor in ohm.Sensor():
                        if sensor.SensorType == 'Fan':
                            rpm = int(sensor.Value) if sensor.Value else 0
                            name = sensor.Name

                            # Rename "Pump Fan" to "Case Fan"
                            if name == 'Pump Fan':
                                name = 'Case Fan'

                            fan_type = 'gpu' if 'GPU' in name else 'system'
                            percent = fan_controls.get(name)

                            fans.append({
                                'name': name,
                                'percent': percent,
                                'rpm': rpm,
                                'type': fan_type
                            })
                            lhm_available = True
                except Exception:
                    pass

        # If no hardware monitor available, fall back to NVML for GPU fans
        if not lhm_available and self._nvml_initialized:
            try:
                device_count = pynvml.nvmlDeviceGetCount()
                for i in range(device_count):
                    handle = pynvml.nvmlDeviceGetHandleByIndex(i)
                    try:
                        num_fans = 1
                        try:
                            num_fans = pynvml.nvmlDeviceGetNumFans(handle)
                        except Exception:
                            pass

                        for fan_idx in range(num_fans):
                            try:
                                speed_percent = pynvml.nvmlDeviceGetFanSpeed_v2(handle, fan_idx)
                                fans.append({
                                    'name': f'GPU Fan {fan_idx + 1}' if num_fans > 1 else 'GPU Fan',
                                    'percent': speed_percent,
                                    'rpm': None,
                                    'type': 'gpu'
                                })
                            except Exception:
                                try:
                                    speed_percent = pynvml.nvmlDeviceGetFanSpeed(handle)
                                    fans.append({
                                        'name': 'GPU Fan',
                                        'percent': speed_percent,
                                        'rpm': None,
                                        'type': 'gpu'
                                    })
                                except Exception:
                                    pass
                                break
                    except Exception:
                        pass
            except Exception:
                pass

        # Remove duplicates (by name) and filter
        seen_names = set()
        filtered_fans = []
        for f in fans:
            if f['name'] in seen_names:
                continue
            seen_names.add(f['name'])

            if f['type'] == 'gpu':
                # Always show GPU fans
                filtered_fans.append(f)
            elif f['rpm'] and f['rpm'] > 0:
                # Only show system fans with RPM > 0
                filtered_fans.append(f)

        fans = filtered_fans

        # Sort: CPU first, then Case Fan, then GPU, then others
        def sort_key(f):
            name = f['name'].lower()
            if 'cpu' in name:
                return (0, name)
            if 'case' in name:
                return (1, name)
            if 'gpu' in name:
                return (2, name)
            return (3, name)

        fans.sort(key=sort_key)

        result = {
            'fans': fans,
            'count': len(fans)
        }

        # Update cache
        self._fan_cache = result
        self._fan_cache_time = current_time

        return result

    def get_all_stats(self) -> dict[str, Any]:
        """Get all hardware statistics (ping handled async in server)."""
        return {
            'cpu': self.get_cpu_stats(),
            'gpu': self.get_gpu_stats(),
            'memory': self.get_memory_stats(),
            'disk': self.get_disk_stats(),
            'network': self.get_network_stats(),
            'fans': self.get_fan_stats(),
            'processes': self.get_top_processes(),
        }

    def __del__(self):
        self._shutdown_nvml()


# Global instance
_monitor = None

def get_monitor() -> HardwareMonitor:
    """Get or create the global hardware monitor instance."""
    global _monitor
    if _monitor is None:
        _monitor = HardwareMonitor()
    return _monitor

def get_all_stats() -> dict[str, Any]:
    """Convenience function to get all stats."""
    return get_monitor().get_all_stats()

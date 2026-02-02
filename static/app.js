// PC Monitor Dashboard - Compact Real-time WebSocket Client

class PCMonitor {
    constructor() {
        this.ws = null;
        this.charts = {};
        this.maxHistoryLength = 60;
        this.totalMemoryGB = 0;
        this.init();
    }

    init() {
        this.setupCharts();
        this.connect();
    }

    connect() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws`;

        this.ws = new WebSocket(wsUrl);

        this.ws.onopen = () => {
            this.updateConnectionStatus(true);
        };

        this.ws.onclose = () => {
            this.updateConnectionStatus(false);
            setTimeout(() => this.connect(), 2000);
        };

        this.ws.onerror = (error) => {
            console.error('WebSocket error:', error);
        };

        this.ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                this.updateDashboard(data);
            } catch (e) {
                console.error('Failed to parse message:', e);
            }
        };
    }

    updateConnectionStatus(connected) {
        const dot = document.getElementById('status-dot');
        const text = document.getElementById('status-text');
        if (dot && text) {
            dot.classList.toggle('connected', connected);
            text.textContent = connected ? 'Connected' : 'Disconnected';
        }
    }

    setupCharts() {
        const chartOptions = {
            responsive: true,
            maintainAspectRatio: false,
            animation: { duration: 0 },
            plugins: { legend: { display: false }, tooltip: { enabled: false } },
            scales: {
                x: { display: false },
                y: {
                    display: false,
                    min: 0,
                    max: 100,
                }
            },
            elements: {
                point: { radius: 0 },
                line: { borderWidth: 1.5 }
            }
        };

        const rateChartOptions = {
            ...chartOptions,
            scales: { ...chartOptions.scales, y: { display: false, min: 0 } }
        };

        // CPU Chart
        this.createChart('cpu-chart', 'rgba(0, 255, 136, 0.8)', 'rgba(0, 255, 136, 0.1)', chartOptions);

        // GPU Chart
        this.createChart('gpu-chart', 'rgba(0, 170, 255, 0.8)', 'rgba(0, 170, 255, 0.1)', chartOptions);

        // Memory Chart
        this.createChart('memory-chart', 'rgba(170, 102, 255, 0.8)', 'rgba(170, 102, 255, 0.1)', chartOptions);

        // Network Chart (dual)
        this.createDualChart('network-chart', 'rgba(0, 255, 136, 0.8)', 'rgba(255, 136, 68, 0.8)', rateChartOptions);

        // Disk Chart (dual)
        this.createDualChart('disk-chart', 'rgba(0, 170, 255, 0.8)', 'rgba(255, 68, 102, 0.8)', rateChartOptions);
    }

    createChart(canvasId, borderColor, bgColor, options) {
        const canvas = document.getElementById(canvasId);
        if (!canvas) return;

        this.charts[canvasId] = new Chart(canvas.getContext('2d'), {
            type: 'line',
            data: {
                labels: Array(60).fill(''),
                datasets: [{
                    data: Array(60).fill(null),
                    borderColor: borderColor,
                    backgroundColor: bgColor,
                    fill: true,
                    tension: 0.3,
                }]
            },
            options: options
        });
    }

    createDualChart(canvasId, color1, color2, options) {
        const canvas = document.getElementById(canvasId);
        if (!canvas) return;

        this.charts[canvasId] = new Chart(canvas.getContext('2d'), {
            type: 'line',
            data: {
                labels: Array(60).fill(''),
                datasets: [
                    { data: Array(60).fill(null), borderColor: color1, fill: false, tension: 0.3 },
                    { data: Array(60).fill(null), borderColor: color2, fill: false, tension: 0.3 }
                ]
            },
            options: options
        });
    }

    updateChart(chartId, value) {
        const chart = this.charts[chartId];
        if (!chart) return;
        chart.data.datasets[0].data.push(value);
        chart.data.datasets[0].data.shift();
        chart.update('none');
    }

    updateDualChart(chartId, value1, value2) {
        const chart = this.charts[chartId];
        if (!chart) return;
        chart.data.datasets[0].data.push(value1);
        chart.data.datasets[0].data.shift();
        chart.data.datasets[1].data.push(value2);
        chart.data.datasets[1].data.shift();
        chart.update('none');
    }

    updateMiniGauge(gaugeId, value, maxValue = 100) {
        const gauge = document.getElementById(gaugeId);
        if (!gauge) return;

        const fill = gauge.querySelector('.gauge-fill');
        if (fill) {
            const percentage = Math.min(value / maxValue, 1);
            // Detect radius from class - large-gauge uses r=42, mini-gauge uses r=20
            const isLarge = gauge.classList.contains('large-gauge');
            const radius = isLarge ? 42 : 20;
            const circumference = 2 * Math.PI * radius;
            const offset = circumference * (1 - percentage);
            fill.style.strokeDasharray = circumference;
            fill.style.strokeDashoffset = offset;
        }
    }

    updateProgressBar(id, percent) {
        const el = document.getElementById(id);
        if (el) el.style.width = `${Math.min(percent, 100)}%`;
    }

    setText(id, text) {
        const el = document.getElementById(id);
        if (el) el.textContent = text;
    }

    updateCoreBars(perCore) {
        const container = document.getElementById('cpu-core-bars');
        if (!container || !perCore.length) return;

        // Only rebuild if core count changed
        if (container.children.length !== perCore.length) {
            container.innerHTML = perCore.map((_, i) => `
                <div class="core-bar">
                    <div class="core-bar-fill" id="core-bar-${i}"></div>
                    <span class="core-bar-label">C${i + 1}</span>
                </div>
            `).join('');
        }

        // Update bar heights
        perCore.forEach((usage, i) => {
            const bar = document.getElementById(`core-bar-${i}`);
            if (bar) {
                const percent = Math.min(usage, 100);
                bar.style.setProperty('--bar-height', `${percent}%`);
                bar.style.background = `linear-gradient(to top, var(--accent-green) ${percent}%, var(--bg-secondary) ${percent}%)`;
            }
        });
    }

    updateDashboard(data) {
        // CPU
        if (data.cpu) {
            const cpuUsage = data.cpu.usage || 0;
            const cpuTemp = data.cpu.temperature;

            // Basic stats
            this.setText('cpu-name', data.cpu.name || 'CPU');
            this.setText('cpu-usage', `${cpuUsage.toFixed(0)}%`);
            this.setText('cpu-freq', data.cpu.frequency ? `${(data.cpu.frequency / 1000).toFixed(1)} GHz` : '--');
            this.setText('cpu-cores', data.cpu.cores || '--');
            this.setText('cpu-threads', data.cpu.threads || '--');
            this.setText('cpu-temp', cpuTemp ? `${cpuTemp.toFixed(0)}°C` : 'N/A');

            // Cache info
            if (data.cpu.l2_cache_kb) {
                const l2MB = (data.cpu.l2_cache_kb / 1024).toFixed(1);
                this.setText('cpu-l2', `${l2MB} MB`);
            }
            if (data.cpu.l3_cache_kb) {
                const l3MB = (data.cpu.l3_cache_kb / 1024).toFixed(0);
                this.setText('cpu-l3', `${l3MB} MB`);
            }

            // Update core bars
            this.updateCoreBars(data.cpu.per_core || []);

            this.updateChart('cpu-chart', cpuUsage);
        }

        // GPU
        if (data.gpu && data.gpu.available) {
            this.setText('gpu-name', data.gpu.name || 'GPU');
            this.setText('gpu-usage', `${(data.gpu.usage || 0).toFixed(0)}%`);
            this.setText('gpu-temp', data.gpu.temperature ? `${data.gpu.temperature}°C` : 'N/A');
            this.setText('gpu-vram', `${data.gpu.memory_used?.toFixed(1) || 0}/${data.gpu.memory_total?.toFixed(0) || 0} GB`);
            this.setText('gpu-clock', data.gpu.graphics_clock ? `${data.gpu.graphics_clock} MHz` : '--');
            this.setText('gpu-mem-clock', data.gpu.memory_clock ? `${data.gpu.memory_clock} MHz` : '--');
            this.setText('gpu-fan', data.gpu.fan_speed !== null ? `${data.gpu.fan_speed}%` : '--');
            this.setText('gpu-power', data.gpu.power ? `${data.gpu.power.toFixed(0)}/${data.gpu.power_limit?.toFixed(0) || '--'} W` : '--');

            this.updateMiniGauge('gpu-usage-gauge', data.gpu.usage || 0);
            this.updateMiniGauge('gpu-temp-gauge', data.gpu.temperature || 0);
            this.updateProgressBar('gpu-vram-bar', data.gpu.memory_percent || 0);
            this.updateChart('gpu-chart', data.gpu.usage || 0);
        }

        // Memory
        if (data.memory) {
            const memPct = data.memory.percent || 0;
            this.totalMemoryGB = data.memory.total || 0;
            this.setText('mem-pct', `${memPct.toFixed(0)}%`);
            this.setText('mem-used-total', `${data.memory.used?.toFixed(1) || 0} / ${data.memory.total?.toFixed(0) || 0} GB`);
            this.setText('mem-speed', data.memory.speed ? `${data.memory.speed} MHz` : '--');
            this.setText('mem-type', data.memory.type || '--');
            this.setText('mem-slots', data.memory.slots_used !== undefined ? `${data.memory.slots_used}/${Math.min(data.memory.slots_total, 4)}` : '--');

            this.updateMiniGauge('memory-gauge', memPct);
            const memGaugeText = document.querySelector('#memory-gauge .gauge-text');
            if (memGaugeText) memGaugeText.textContent = `${memPct.toFixed(0)}%`;

            this.updateChart('memory-chart', memPct);
        }

        // Network
        if (data.network) {
            const download = data.network.download_rate || 0;
            const upload = data.network.upload_rate || 0;
            this.setText('net-down', `${download.toFixed(2)} MB/s`);
            this.setText('net-up', `${upload.toFixed(2)} MB/s`);
            this.updateDualChart('network-chart', download, upload);
        }

        // Ping
        if (data.ping) {
            if (data.ping.success && data.ping.ping !== null) {
                this.setText('ping-value', `${data.ping.ping} ms`);
            } else {
                this.setText('ping-value', '--');
            }
        }

        // Disk
        if (data.disk) {
            const readRate = data.disk.read_rate || 0;
            const writeRate = data.disk.write_rate || 0;
            this.setText('disk-read', `${readRate.toFixed(2)} MB/s`);
            this.setText('disk-write', `${writeRate.toFixed(2)} MB/s`);
            this.updateDualChart('disk-chart', readRate, writeRate);
        }

        // Fans
        if (data.fans) {
            this.updateFansList(data.fans);
        }

        // Processes
        if (data.processes) {
            this.updateProcessList(data.processes);
        }

        // System Info
        if (data.system) {
            this.updateSystemInfo(data.system);
        }
    }

    updateFansList(fanData) {
        const container = document.getElementById('fans-list');
        if (!container) return;

        const fans = fanData.fans || [];

        if (fans.length === 0) {
            container.innerHTML = '<div class="no-fans">No fan data available.<br><small>GPU fans show when active. System fans require monitoring software.</small></div>';
            return;
        }

        container.innerHTML = fans.map(fan => {
            const percent = fan.percent !== null ? fan.percent : null;
            const rpm = fan.rpm !== null ? fan.rpm : null;

            let speedDisplay = '';
            if (percent !== null) {
                speedDisplay = `<span class="fan-percent">${percent}%</span>`;
                if (rpm !== null) {
                    speedDisplay += `<span class="fan-rpm">${rpm} RPM</span>`;
                }
            } else if (rpm !== null) {
                speedDisplay = `<span class="fan-percent">${rpm} RPM</span>`;
            } else {
                speedDisplay = `<span class="fan-percent">--</span>`;
            }

            const barWidth = percent !== null ? percent : 0;

            return `
                <div class="fan-item">
                    <div class="fan-info">
                        <span class="fan-name">${fan.name}</span>
                        <div class="fan-bar">
                            <div class="fan-bar-fill" style="width: ${barWidth}%"></div>
                        </div>
                    </div>
                    <div class="fan-speed">
                        ${speedDisplay}
                    </div>
                </div>
            `;
        }).join('');
    }

    updateProcessList(processes) {
        const container = document.getElementById('process-list');
        if (!container) return;

        // Filter out system idle process and get top 5
        const filtered = processes
            .filter(p => p.name !== 'System Idle Process')
            .slice(0, 8);

        container.innerHTML = filtered.map(p => {
            // Calculate actual memory usage in MB
            const memoryMB = (p.memory_percent / 100) * this.totalMemoryGB * 1024;
            let memoryStr;
            if (memoryMB >= 1024) {
                memoryStr = `${(memoryMB / 1024).toFixed(1)} GB`;
            } else {
                memoryStr = `${memoryMB.toFixed(0)} MB`;
            }

            // Format CPU with 1 decimal place
            const cpuStr = `${p.cpu_percent.toFixed(1)}%`;

            return `
                <li class="process-item">
                    <span class="process-name" title="${p.name}">${p.name}</span>
                    <span class="process-stats">
                        <span class="text-green">${cpuStr}</span>
                        <span class="text-purple">${memoryStr}</span>
                    </span>
                </li>
            `;
        }).join('');
    }

    updateSystemInfo(system) {
        if (!system.available) return;

        // Uptime
        if (system.uptime) {
            this.setText('sys-uptime', system.uptime);
        }

        // Motherboard
        if (system.motherboard) {
            this.setText('sys-mb-model', system.motherboard.product || '--');
        }

        // Storage Drives
        if (system.drives && system.drives.length > 0) {
            const container = document.getElementById('sys-drives');
            if (container) {
                container.innerHTML = system.drives.map(drive => {
                    const sizeStr = drive.size_gb >= 1000
                        ? `${(drive.size_gb / 1000).toFixed(1)} TB`
                        : `${Math.round(drive.size_gb)} GB`;

                    // Truncate model name if too long
                    let model = drive.model || 'Unknown';
                    if (model.length > 20) {
                        model = model.substring(0, 17) + '...';
                    }

                    return `
                        <div class="drive-item">
                            <div class="drive-info">
                                <div class="drive-name" title="${drive.model}">${model}</div>
                                <div class="drive-details">${drive.type}</div>
                            </div>
                            <span class="drive-size">${sizeStr}</span>
                        </div>
                    `;
                }).join('');
            }
        }
    }
}

document.addEventListener('DOMContentLoaded', () => {
    window.monitor = new PCMonitor();
});

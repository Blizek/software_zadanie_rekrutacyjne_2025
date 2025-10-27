from nicegui import ui
import asyncio
from functools import partial
import json
from pathlib import Path
import utils
from datetime import datetime

SERVICES = {
    'proxy': {'cmd': ['python', 'tcp_proxy.py'], 'title': 'Proxy server'},
    'simulator': {'cmd': ['python', 'tcp_simulator.py'], 'title': 'Simulator'},
    'flight': {'cmd': ['python', 'flight_sequences.py'], 'title': 'Flight Sequences'},
}

running = {}

collected_data = {} 
collecting = False


def get_config_sensor_names():
    try:
        import yaml
        p = Path('simulator_config.yaml')
        if not p.exists():
            return []
        with p.open('r') as fh:
            conf = yaml.safe_load(fh)
        sensors = []
        dev = conf.get('devices', {}) if isinstance(conf, dict) else {}
        sensor_block = dev.get('sensor') if isinstance(dev, dict) else {}
        if isinstance(sensor_block, dict):
            sensors = list(sensor_block.keys())
        return sorted(sensors)
    except Exception:
        return []


def make_status_label(initial_running: bool = False):
    lbl = ui.label('●')
    color = 'green' if initial_running else 'red'
    lbl.style(f'color: {color}; font-size: 20px;')
    return lbl


async def _read_process_output(name: str, proc, log_area):
    try:
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            text = line.decode(errors='replace').rstrip()
            running[name]['logs'].append(text)
            try:
                log_area.set_text('\n'.join(running[name]['logs'][-500:]))
            except Exception:
                log_area.content = '\n'.join(running[name]['logs'][-500:])
    except Exception as e:
        running[name]['logs'].append(f'Error reading output: {e}')
        try:
            log_area.set_text('\n'.join(running[name]['logs'][-500:]))
        except Exception:
            log_area.content = '\n'.join(running[name]['logs'][-500:])


async def _run_service(name: str):
    svc = SERVICES[name]
    cmd = svc['cmd']
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT
    )
    running[name]['proc'] = proc
    running[name]['status_label'].style('color: green; font-size: 20px;')
    running[name]['logs'].append(f"Started: {' '.join(cmd)} (pid={proc.pid})")
    try:
        running[name]['log_area'].set_text('\n'.join(running[name]['logs'][-500:]))
    except Exception:
        running[name]['log_area'].content = '\n'.join(running[name]['logs'][-500:])

    await _read_process_output(name, proc, running[name]['log_area'])

    rc = await proc.wait()
    running[name]['logs'].append(f'Process exited with code {rc}')
    try:
        running[name]['log_area'].set_text('\n'.join(running[name]['logs'][-500:]))
    except Exception:
        running[name]['log_area'].content = '\n'.join(running[name]['logs'][-500:])

    running[name]['status_label'].style('color: red; font-size: 20px;')
    running[name]['proc'] = None
    if name == 'simulator':
        try:
            global collecting
            collecting = False
        except Exception:
            pass
        try:
            update_sensor_select_options()
        except Exception:
            pass
        try:
            ui.notify('Simulation complete, data collected')
        except Exception:
            pass


def start_service(name: str):
    if running.get(name) and running[name].get('proc'):
        ui.notify(f"{SERVICES[name]['title']} już działa")
        return

    ui.notify(f'Uruchamiam {SERVICES[name]["title"]}...')
    running.setdefault(name, {'logs': []})
    if name == 'simulator':
        collected_data.clear()
        try:
            global collecting
            collecting = True
        except Exception:
            pass
        try:
            sensor_select.items = []
        except Exception:
            pass

    task = asyncio.create_task(_run_service(name))
    running[name]['task'] = task


async def _stop_service(name: str):
    info = running.get(name)
    if not info or not info.get('proc'):
        ui.notify(f"{SERVICES[name]['title']} nie działa")
        return

    proc = info['proc']
    proc.terminate()
    try:
        await asyncio.wait_for(proc.wait(), timeout=2.0)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()

    info['logs'].append('Process terminated by user')
    try:
        info['log_area'].set_text('\n'.join(info['logs'][-500:]))
    except Exception:
        info['log_area'].content = '\n'.join(info['logs'][-500:])

    info['status_label'].style('color: red; font-size: 20px;')
    info['proc'] = None


def stop_service(name: str):
    asyncio.create_task(_stop_service(name))


ui.label('Rocket Control Panel').classes('text-2xl font-bold mt-4 mb-2')
ui.separator()

with ui.column().classes('w-full items-center gap-6 mt-4'):
    for name, svc in SERVICES.items():
        with ui.card().classes('w-11/12 max-w-screen-lg shadow-md'):
            with ui.column().classes('w-full gap-2'):
                with ui.row().classes('items-center justify-between w-full'):
                    ui.label(svc['title']).classes('text-lg font-semibold')
                    status = make_status_label(False)
                    running.setdefault(name, {})
                    running[name]['status_label'] = status

                with ui.row().classes('gap-2 w-full justify-start'):
                    ui.button('Start', on_click=partial(start_service, name)).props(
                        'color=primary outline'
                    )
                    ui.button('Stop', on_click=partial(stop_service, name)).props(
                        'color=error outline'
                    )

                ui.label('Logi:').classes('mt-2 text-sm')
                log_area = ui.code(
                    'No logs yet',
                    language='text'
                ).style(
                    'height: 400px; width: 100%; overflow-y: auto; '
                    'white-space: pre-wrap; background-color: #111; '
                    'color: #0f0; border-radius: 6px; padding: 6px;'
                )
                running[name]['log_area'] = log_area
                running[name]['logs'] = running[name].get('logs', [])


with ui.column().classes('w-full items-center'):
    with ui.card().classes('w-11/12 max-w-screen-lg shadow-md mt-6'):
        with ui.column().classes('w-full gap-2'):
            ui.label("Sensor's chart (based on collected data)").classes('text-lg font-semibold mb-2')
            
            with ui.row().classes('gap-4 items-center w-full justify-start'):
                initial_sensors = get_config_sensor_names()
                if 'altitude' in initial_sensors and 'velocity' not in initial_sensors:
                    initial_items = initial_sensors + ['velocity']
                else:
                    initial_items = initial_sensors

                sensor_select = ui.select(initial_items, label='Select sensor to display').classes('w-64')

                ui.button('Show chart', on_click=lambda: show_sensor_chart(sensor_select)).props('color=primary outline')

            ui.html(
                """
                <div style="width:100%; padding:12px; border-radius:6px; background-color: #111;">
                    <canvas id="sensorChart" style="width:100%; height:320px;"></canvas>
                </div>
                """,
                sanitize=False,
            ).classes('w-full mt-2')


ui.add_body_html(
    """
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.3.0/dist/chart.umd.min.js"></script>
<script>
(function(){
    const ctx = document.getElementById('sensorChart').getContext('2d');
    window._sensorChartData = {
        labels: [],
        datasets: [{
            label: '',
            data: [],
            borderColor: 'rgba(75,192,192,1)',
            backgroundColor: 'rgba(75,192,192,0.2)',
            tension: 0.2,
            spanGaps: true
        }]
    };
    window._sensorChart = new Chart(ctx, {
        type: 'line',
        data: window._sensorChartData,
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    labels: {
                        color: '#fff' 
                    }
                }
            },
            scales: { 
                y: { 
                    beginAtZero: false,
                    ticks: {
                        color: '#fff' 
                    },
                    grid: {
                        color: 'rgba(255, 255, 255, 0.2)'
                    }
                },
                x: {
                    ticks: {
                        color: '#fff' 
                    },
                    grid: {
                        color: 'rgba(255, 255, 255, 0.2)'
                    }
                }
            }
        }
    });

    window.renderSensor = function(labels, data, label) {
        try {
            window._sensorChartData.labels = labels.map(l => new Date(l).toLocaleTimeString());
            window._sensorChartData.datasets[0].data = data;
            window._sensorChartData.datasets[0].label = label;
            window._sensorChart.update();
        } catch (e) {
            console.error('renderSensor error', e);
        }
    };
})();
</script>
"""
)


async def _frame_collector():
    await asyncio.sleep(1.0)

    cm = None
    conf = None
    try:
        import yaml
        with open('simulator_config.yaml', 'r') as fh:
            conf = yaml.safe_load(fh)
    except Exception:
        conf = None

    while True:
        try:
            if collecting:
                if cm is None:
                    try:
                        cm = await asyncio.to_thread(utils.connect_manager, '127.0.0.1', 3000)
                    except Exception:
                        cm = None

                if cm is not None and conf is not None:
                    try:
                        while True:
                            frame = utils.receive_frame(cm, timeout=0)
                            if frame is None:
                                break
                            parsed = utils.parse_feed_frame(frame, conf)
                            if parsed and parsed.get('kind') == 'sensor':
                                name = parsed.get('name')
                                raw = parsed.get('value')
                                try:
                                    value = float(raw)
                                except Exception:
                                    value = raw
                                ts = datetime.utcnow().isoformat()
                                collected_data.setdefault(name, []).append((ts, value))
                    except Exception:
                        try:
                            cm.disconnect()
                        except Exception:
                            pass
                        cm = None
            
            await asyncio.sleep(0.5)
        except Exception:
            await asyncio.sleep(1.0)


def update_sensor_select_options():
    keys = sorted(collected_data.keys())
    if 'altitude' in collected_data and 'velocity' not in keys:
        keys.append('velocity')
    try:
        sensor_select.items = keys
        if keys:
            sensor_select.value = keys[0]
    except Exception:
        js = 'const sel = document.getElementById("sensorSelect"); if (sel) { sel.innerHTML = ""; }'
        if keys:
            for k in keys:
                safe = k.replace('"', '\\"')
                js += f"; sel.appendChild(Object.assign(document.createElement('option'), {{value: '{safe}', text: '{safe}'}}))"
        js += "; if (sel && sel.options.length>0) sel.selectedIndex = 0;"
        for session in ui.get_client_sessions():
            with ui.session(session):
                ui.run_javascript(js)


def show_sensor_chart(sensor_select):
    sel_val = sensor_select.value
    
    if not sel_val:
        keys = sorted(collected_data.keys())
        if not keys:
            ui.notify('No data to display')
            return
        sel_val = keys[0]

    entries = collected_data.get(sel_val)
    if not entries:
        ui.notify('No data for selected sensor')
        return

    labels = [ts for ts, _ in entries]
    values = [v if v is not None else None for _, v in entries]
    
    js_labels = json.dumps(labels)
    js_values = json.dumps(values)
    label = sel_val
    
    js = f"if (window.renderSensor) window.renderSensor({js_labels}, {js_values}, {json.dumps(label)});"
    
    for session in ui.get_client_sessions():
        with ui.session(session):
            ui.run_javascript(js)


asyncio.get_event_loop().create_task(_frame_collector())


ui.run(reload=False)
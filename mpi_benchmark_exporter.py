#!/usr/bin/env python3
"""
MPI Benchmark Prometheus Exporter - Log Reader Version
Reads results from stress test log instead of running own benchmarks

Port: 9105
Run on: Master server (192.168.11.152)
"""

import re
import time
import threading
import http.server
import socketserver
from datetime import datetime
import os

# Configuration
LOGFILE = "/tmp/mpi_stress.log"
LOG_CHECK_INTERVAL = 5  # Check log every 5 seconds
PORT = 9105
NUM_PROCESSES = 8

# Current metrics storage
metrics = {
    "allreduce_4mb": 0.0,
    "allreduce_1mb": 0.0,
    "allreduce_64kb": 0.0,
    "allreduce_1kb": 0.0,
    "broadcast_4mb": 0.0,
    "broadcast_1mb": 0.0,
    "alltoall_1mb": 0.0,
    "allgather_128kb": 0.0,
    "reduce_1mb": 0.0,
    "last_update": 0,
    "stress_test_running": 0,
    "iteration": 0,
}

metrics_lock = threading.Lock()

def parse_log_file():
    """Parse the stress test log file for latest results"""

    if not os.path.exists(LOGFILE):
        return None

    try:
        with open(LOGFILE, 'r') as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading log: {e}")
        return None

    results = {}

    # Find the latest iteration
    iteration_matches = re.findall(r'=== Iteration (\d+)', content)
    if iteration_matches:
        results['iteration'] = int(iteration_matches[-1])

    # Get last 5000 chars (most recent results - covers full iteration)
    recent = content[-5000:] if len(content) > 5000 else content

    # Parse OSU benchmark output format: "size    latency"
    # OSU output has headers, then: 4194304    12345.67
    # Use regex that skips headers

    # Allreduce - multiple sizes
    allreduce_4mb = re.search(r'Allreduce 4MB.*?4194304\s+([\d.]+)', recent, re.DOTALL)
    if allreduce_4mb:
        results['allreduce_4mb'] = float(allreduce_4mb.group(1))

    allreduce_1mb = re.search(r'Allreduce 1MB.*?1048576\s+([\d.]+)', recent, re.DOTALL)
    if allreduce_1mb:
        results['allreduce_1mb'] = float(allreduce_1mb.group(1))

    allreduce_64kb = re.search(r'Allreduce 64KB.*?65536\s+([\d.]+)', recent, re.DOTALL)
    if allreduce_64kb:
        results['allreduce_64kb'] = float(allreduce_64kb.group(1))

    allreduce_1kb = re.search(r'Allreduce 1KB.*?1024\s+([\d.]+)', recent, re.DOTALL)
    if allreduce_1kb:
        results['allreduce_1kb'] = float(allreduce_1kb.group(1))

    # Broadcast - multiple sizes
    broadcast_4mb = re.search(r'Broadcast 4MB.*?4194304\s+([\d.]+)', recent, re.DOTALL)
    if broadcast_4mb:
        results['broadcast_4mb'] = float(broadcast_4mb.group(1))

    broadcast_1mb = re.search(r'Broadcast 1MB.*?1048576\s+([\d.]+)', recent, re.DOTALL)
    if broadcast_1mb:
        results['broadcast_1mb'] = float(broadcast_1mb.group(1))

    # Alltoall 1MB
    alltoall_match = re.search(r'Alltoall 1MB.*?1048576\s+([\d.]+)', recent, re.DOTALL)
    if alltoall_match:
        results['alltoall_1mb'] = float(alltoall_match.group(1))

    # Allgather 128KB
    allgather_match = re.search(r'Allgather 128KB.*?131072\s+([\d.]+)', recent, re.DOTALL)
    if allgather_match:
        results['allgather_128kb'] = float(allgather_match.group(1))

    # Reduce 1MB
    reduce_match = re.search(r'Reduce 1MB.*?1048576\s+([\d.]+)', recent, re.DOTALL)
    if reduce_match:
        results['reduce_1mb'] = float(reduce_match.group(1))

    return results

def check_stress_test_running():
    """Check if stress test is currently running"""
    import subprocess
    try:
        result = subprocess.run(
            ['pgrep', '-f', 'mpi_stress_test.sh'],
            capture_output=True,
            timeout=5
        )
        return result.returncode == 0
    except:
        return False

def update_metrics():
    """Update metrics from log file"""

    global metrics

    results = parse_log_file()
    running = check_stress_test_running()

    with metrics_lock:
        metrics["stress_test_running"] = 1 if running else 0

        if results:
            for key, value in results.items():
                if key in metrics:
                    metrics[key] = value
            metrics["last_update"] = time.time()
            print(f"[{datetime.now()}] Updated metrics from log - iteration {results.get('iteration', '?')}")
        else:
            if not running:
                # Stress test stopped - zero out metrics
                for key in ["allreduce_4mb", "allreduce_1mb", "allreduce_64kb", "allreduce_1kb",
                            "broadcast_4mb", "broadcast_1mb", "alltoall_1mb",
                            "allgather_128kb", "reduce_1mb"]:
                    metrics[key] = 0.0
                print(f"[{datetime.now()}] Stress test not running - metrics zeroed")

def log_monitor_loop():
    """Continuously monitor the log file"""
    print(f"[{datetime.now()}] Log monitor started - watching {LOGFILE}")
    while True:
        try:
            update_metrics()
        except Exception as e:
            print(f"Error in log monitor: {e}")

        time.sleep(LOG_CHECK_INTERVAL)

def generate_metrics():
    """Generate Prometheus format metrics"""

    with metrics_lock:
        lines = []

        lines.append("# HELP mpi_allreduce_latency_us MPI Allreduce latency in microseconds")
        lines.append("# TYPE mpi_allreduce_latency_us gauge")
        lines.append(f'mpi_allreduce_latency_us{{size="4MB",nodes="{NUM_PROCESSES}"}} {metrics["allreduce_4mb"]}')
        lines.append(f'mpi_allreduce_latency_us{{size="1MB",nodes="{NUM_PROCESSES}"}} {metrics["allreduce_1mb"]}')
        lines.append(f'mpi_allreduce_latency_us{{size="64KB",nodes="{NUM_PROCESSES}"}} {metrics["allreduce_64kb"]}')
        lines.append(f'mpi_allreduce_latency_us{{size="1KB",nodes="{NUM_PROCESSES}"}} {metrics["allreduce_1kb"]}')

        lines.append("")
        lines.append("# HELP mpi_broadcast_latency_us MPI Broadcast latency in microseconds")
        lines.append("# TYPE mpi_broadcast_latency_us gauge")
        lines.append(f'mpi_broadcast_latency_us{{size="4MB",nodes="{NUM_PROCESSES}"}} {metrics["broadcast_4mb"]}')
        lines.append(f'mpi_broadcast_latency_us{{size="1MB",nodes="{NUM_PROCESSES}"}} {metrics["broadcast_1mb"]}')

        lines.append("")
        lines.append("# HELP mpi_alltoall_latency_us MPI Alltoall latency in microseconds")
        lines.append("# TYPE mpi_alltoall_latency_us gauge")
        lines.append(f'mpi_alltoall_latency_us{{size="1MB",nodes="{NUM_PROCESSES}"}} {metrics["alltoall_1mb"]}')

        lines.append("")
        lines.append("# HELP mpi_allgather_latency_us MPI Allgather latency in microseconds")
        lines.append("# TYPE mpi_allgather_latency_us gauge")
        lines.append(f'mpi_allgather_latency_us{{size="128KB",nodes="{NUM_PROCESSES}"}} {metrics["allgather_128kb"]}')

        lines.append("")
        lines.append("# HELP mpi_reduce_latency_us MPI Reduce latency in microseconds")
        lines.append("# TYPE mpi_reduce_latency_us gauge")
        lines.append(f'mpi_reduce_latency_us{{size="1MB",nodes="{NUM_PROCESSES}"}} {metrics["reduce_1mb"]}')

        lines.append("")
        lines.append("# HELP mpi_benchmark_last_update_timestamp Unix timestamp of last log update")
        lines.append("# TYPE mpi_benchmark_last_update_timestamp gauge")
        lines.append(f"mpi_benchmark_last_update_timestamp {metrics['last_update']}")

        lines.append("")
        lines.append("# HELP mpi_stress_test_running Whether stress test is currently running")
        lines.append("# TYPE mpi_stress_test_running gauge")
        lines.append(f"mpi_stress_test_running {metrics['stress_test_running']}")

        lines.append("")
        lines.append("# HELP mpi_stress_test_iteration Current stress test iteration")
        lines.append("# TYPE mpi_stress_test_iteration counter")
        lines.append(f"mpi_stress_test_iteration {metrics['iteration']}")

        return '\n'.join(lines) + '\n'

class MetricsHandler(http.server.BaseHTTPRequestHandler):
    """HTTP handler for Prometheus metrics"""

    def log_message(self, format, *args):
        print(f"[{datetime.now()}] {args[0]}")

    def do_GET(self):
        if self.path == '/metrics':
            content = generate_metrics()
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.send_header('Content-Length', len(content))
            self.end_headers()
            self.wfile.write(content.encode())

        elif self.path == '/health':
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'OK')

        elif self.path == '/':
            with metrics_lock:
                running = metrics['stress_test_running']
                iteration = metrics['iteration']

            status = "RUNNING" if running else "STOPPED"
            html = f"""<html>
<head><title>MPI Benchmark Exporter</title></head>
<body>
<h1>MPI Benchmark Exporter (Log Reader)</h1>
<p>Stress Test: <b>{status}</b> (Iteration: {iteration})</p>
<p>Reads from: {LOGFILE}</p>
<p><a href="/metrics">Metrics</a></p>
<p><a href="/health">Health</a></p>
</body>
</html>"""
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            self.wfile.write(html.encode())

        else:
            self.send_response(404)
            self.end_headers()

class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    """Threaded HTTP server"""
    daemon_threads = True

def main():
    print(f"MPI Benchmark Exporter (Log Reader Version)")
    print(f"=" * 50)
    print(f"Port: {PORT}")
    print(f"Log file: {LOGFILE}")
    print(f"Check interval: {LOG_CHECK_INTERVAL} seconds")
    print(f"Metrics: http://0.0.0.0:{PORT}/metrics")
    print()
    print("This exporter reads from the stress test log.")
    print("It does NOT run its own benchmarks.")
    print("Start stress test with: ./mpi_bandwidth_stress.py start")
    print()

    # Start log monitor thread
    monitor_thread = threading.Thread(target=log_monitor_loop, daemon=True)
    monitor_thread.start()

    # Start HTTP server
    server = ThreadedHTTPServer(('0.0.0.0', PORT), MetricsHandler)
    print(f"Server running on port {PORT}...")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()

if __name__ == '__main__':
    main()

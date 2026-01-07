#!/usr/bin/env python3
"""
MPI Benchmark Prometheus Exporter (No external dependencies!)
Runs OSU MPI benchmarks periodically and exposes results for Prometheus/Grafana

Port: 9105
Run on: Master server (192.168.11.152)
"""

import subprocess
import time
import threading
import http.server
import socketserver
from datetime import datetime

# Configuration
HOSTFILE = "/home/versa/hostfile_rdma"
NUM_PROCESSES = 8
OSU_PATH = "/usr/local/libexec/osu-micro-benchmarks/mpi/collective"
BENCHMARK_INTERVAL = 60  # Run benchmarks every 60 seconds
PORT = 9105

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
    "last_run": 0,
    "success": 0,
    "running": 0,
}

metrics_lock = threading.Lock()

def run_mpi_command(benchmark, size, iterations=50):
    """Run a single MPI benchmark and return latency in microseconds"""

    cmd = f"""
export UCX_TLS=ud_verbs,self,sm
export UCX_NET_DEVICES=all
mpirun --hostfile {HOSTFILE} -np {NUM_PROCESSES} \
    -x UCX_TLS -x UCX_NET_DEVICES \
    --mca pml ucx --mca btl ^openib,tcp \
    --mca btl_openib_warn_no_device_params_found 0 \
    {OSU_PATH}/{benchmark} -m {size}:{size} -i {iterations} 2>&1 | grep -E "^{size}"
"""

    try:
        result = subprocess.run(
            ['bash', '-c', cmd],
            capture_output=True,
            text=True,
            timeout=120
        )

        if result.returncode == 0 and result.stdout.strip():
            parts = result.stdout.strip().split()
            if len(parts) >= 2:
                latency = float(parts[1])
                return latency
    except Exception as e:
        print(f"Error running {benchmark}: {e}")

    return None

def run_benchmarks():
    """Run all benchmarks and update metrics"""

    global metrics

    print(f"[{datetime.now()}] Running MPI benchmarks...")

    with metrics_lock:
        metrics["running"] = 1

    success = True
    results = {}

    benchmarks = [
        ("osu_allreduce", "4194304", "allreduce_4mb"),
        ("osu_allreduce", "1048576", "allreduce_1mb"),
        ("osu_allreduce", "65536", "allreduce_64kb"),
        ("osu_allreduce", "1024", "allreduce_1kb"),
        ("osu_bcast", "4194304", "broadcast_4mb"),
        ("osu_bcast", "1048576", "broadcast_1mb"),
        ("osu_alltoall", "1048576", "alltoall_1mb"),
        ("osu_allgather", "131072", "allgather_128kb"),
        ("osu_reduce", "1048576", "reduce_1mb"),
    ]

    for bench_name, size, metric_key in benchmarks:
        latency = run_mpi_command(bench_name, size)
        if latency is not None:
            results[metric_key] = latency
            print(f"  {metric_key}: {latency:.2f} us")
        else:
            success = False
            print(f"  {metric_key}: FAILED")

    with metrics_lock:
        for key, value in results.items():
            metrics[key] = value
        metrics["last_run"] = time.time()
        metrics["success"] = 1 if success else 0
        metrics["running"] = 0

    print(f"[{datetime.now()}] Benchmarks complete. Success={success}")

def benchmark_loop():
    """Continuously run benchmarks"""
    while True:
        try:
            run_benchmarks()
        except Exception as e:
            print(f"Error in benchmark loop: {e}")

        time.sleep(BENCHMARK_INTERVAL)

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
        lines.append("# HELP mpi_benchmark_last_run_timestamp Unix timestamp of last benchmark run")
        lines.append("# TYPE mpi_benchmark_last_run_timestamp gauge")
        lines.append(f"mpi_benchmark_last_run_timestamp {metrics['last_run']}")

        lines.append("")
        lines.append("# HELP mpi_benchmark_success Whether last benchmark was successful")
        lines.append("# TYPE mpi_benchmark_success gauge")
        lines.append(f"mpi_benchmark_success {metrics['success']}")

        lines.append("")
        lines.append("# HELP mpi_benchmark_running Whether benchmark is currently running")
        lines.append("# TYPE mpi_benchmark_running gauge")
        lines.append(f"mpi_benchmark_running {metrics['running']}")

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
            html = """<html>
<head><title>MPI Benchmark Exporter</title></head>
<body>
<h1>MPI Benchmark Exporter</h1>
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
    print(f"MPI Benchmark Exporter")
    print(f"Port: {PORT}")
    print(f"Benchmark interval: {BENCHMARK_INTERVAL} seconds")
    print(f"Metrics: http://0.0.0.0:{PORT}/metrics")
    print()

    # Start benchmark thread
    benchmark_thread = threading.Thread(target=benchmark_loop, daemon=True)
    benchmark_thread.start()

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

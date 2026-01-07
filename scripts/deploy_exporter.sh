#!/bin/bash
#
# Deploy MPI Benchmark Exporter to Master Node
#
# Usage: ./deploy_exporter.sh <master_ip> <password>
# Example: ./deploy_exporter.sh 192.168.11.152 'MyPassword'

set -e

MASTER_IP=${1:-"192.168.11.152"}
PASSWORD=${2:-""}
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"

if [ -z "$PASSWORD" ]; then
    echo "Usage: $0 <master_ip> <password>"
    echo "Example: $0 192.168.11.152 'MyPassword'"
    exit 1
fi

echo "Deploying MPI Benchmark Exporter to $MASTER_IP"
echo ""

# Copy exporter script
echo "[1/3] Copying exporter script..."
sshpass -p "$PASSWORD" scp -o StrictHostKeyChecking=no \
    "$REPO_DIR/mpi_benchmark_exporter.py" \
    "versa@$MASTER_IP:/home/versa/"

# Stop existing exporter
echo "[2/3] Stopping existing exporter..."
sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no "versa@$MASTER_IP" \
    "pkill -f mpi_benchmark_exporter.py 2>/dev/null || true"

sleep 2

# Start new exporter
echo "[3/3] Starting exporter..."
sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no "versa@$MASTER_IP" '
cd /home/versa
nohup python3 mpi_benchmark_exporter.py > /tmp/mpi_exporter.log 2>&1 &
sleep 3
if curl -s http://localhost:9105/health | grep -q OK; then
    echo "Exporter started successfully!"
    echo "Metrics: http://'"$MASTER_IP"':9105/metrics"
else
    echo "ERROR: Exporter failed to start"
    tail -20 /tmp/mpi_exporter.log
    exit 1
fi
'

echo ""
echo "Done! Exporter running at http://$MASTER_IP:9105/metrics"

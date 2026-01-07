# Setup Guide

Complete installation guide for setting up MPI benchmarks on an RDMA cluster.

## Prerequisites

### Hardware Requirements
- 2+ Linux servers (Ubuntu 20.04+ or RHEL 8+)
- RDMA-capable NICs (Mellanox ConnectX-4/5/6 recommended)
- Network switch with RoCEv2, PFC, and ECN support

### Software Requirements
- OpenMPI 4.1.x with UCX support
- UCX 1.12+
- OSU Micro-Benchmarks 7.x
- Python 3.6+
- Prometheus (for metrics collection)
- Grafana (for visualization)

## Step 1: Install OpenMPI with UCX

Run on **all nodes**:

```bash
# Install dependencies
sudo apt update
sudo apt install -y build-essential gfortran libibverbs-dev librdmacm-dev \
    rdma-core infiniband-diags perftest wget

# Install UCX
wget https://github.com/openucx/ucx/releases/download/v1.14.1/ucx-1.14.1.tar.gz
tar xzf ucx-1.14.1.tar.gz
cd ucx-1.14.1
./configure --prefix=/usr/local --enable-mt
make -j$(nproc)
sudo make install
sudo ldconfig

# Install OpenMPI
cd ..
wget https://download.open-mpi.org/release/open-mpi/v4.1/openmpi-4.1.6.tar.gz
tar xzf openmpi-4.1.6.tar.gz
cd openmpi-4.1.6
./configure --prefix=/usr/local --with-ucx=/usr/local --enable-mpi-cxx
make -j$(nproc)
sudo make install
sudo ldconfig

# Verify installation
mpirun --version
ucx_info -v
```

## Step 2: Install OSU Micro-Benchmarks

Run on **all nodes**:

```bash
wget https://mvapich.cse.ohio-state.edu/download/mvapich/osu-micro-benchmarks-7.3.tar.gz
tar xzf osu-micro-benchmarks-7.3.tar.gz
cd osu-micro-benchmarks-7.3

./configure CC=mpicc CXX=mpicxx --prefix=/usr/local
make -j$(nproc)
sudo make install

# Verify
ls /usr/local/libexec/osu-micro-benchmarks/mpi/collective/
```

## Step 3: Configure Passwordless SSH

Run on **master node**:

```bash
# Generate SSH key (if not exists)
ssh-keygen -t rsa -N "" -f ~/.ssh/id_rsa

# Copy to all nodes (including itself)
for ip in 192.168.251.111 192.168.250.112 192.168.251.113 192.168.250.114 \
          192.168.250.115 192.168.251.116 192.168.250.117 192.168.251.118; do
    ssh-copy-id -o StrictHostKeyChecking=no $ip
done

# Test connectivity
for ip in 192.168.251.111 192.168.250.112 192.168.251.113 192.168.250.114 \
          192.168.250.115 192.168.251.116 192.168.250.117 192.168.251.118; do
    ssh $ip hostname
done
```

## Step 4: Create MPI Hostfile

Create `/home/versa/hostfile_rdma` on **master node**:

```bash
cat > ~/hostfile_rdma << 'EOF'
192.168.251.111 slots=1
192.168.250.112 slots=1
192.168.251.113 slots=1
192.168.250.114 slots=1
192.168.250.115 slots=1
192.168.251.116 slots=1
192.168.250.117 slots=1
192.168.251.118 slots=1
EOF
```

**Important**: Use RDMA IPs, not management IPs!

## Step 5: Verify RDMA Connectivity

```bash
# Check RDMA devices
ibstat
ibv_devices

# Test RDMA bandwidth between two nodes
# On server 1:
ib_send_bw -d mlx5_0

# On server 2:
ib_send_bw -d mlx5_0 192.168.251.111
```

## Step 6: Test MPI

```bash
# Simple test
mpirun --hostfile ~/hostfile_rdma -np 8 hostname

# Test with UCX
export UCX_TLS=ud_verbs,self,sm
export UCX_NET_DEVICES=all

mpirun --hostfile ~/hostfile_rdma -np 8 \
    -x UCX_TLS -x UCX_NET_DEVICES \
    --mca pml ucx --mca btl ^openib,tcp \
    /usr/local/libexec/osu-micro-benchmarks/mpi/collective/osu_allreduce
```

## Step 7: Deploy Benchmark Scripts

On your **control machine**:

```bash
# Clone repository
git clone https://github.com/YOUR_USERNAME/mpi-ai-cluster-benchmark.git
cd mpi-ai-cluster-benchmark

# Copy exporter to master node
scp mpi_benchmark_exporter.py versa@192.168.11.152:/home/versa/

# Start exporter on master
ssh versa@192.168.11.152 'cd /home/versa && nohup python3 mpi_benchmark_exporter.py > /tmp/mpi_exporter.log 2>&1 &'

# Verify
curl http://192.168.11.152:9105/health
```

## Step 8: Configure Prometheus

Add to `/etc/prometheus/prometheus.yml`:

```yaml
scrape_configs:
  - job_name: 'mpi-benchmarks'
    scrape_interval: 120s
    static_configs:
      - targets: ['192.168.11.152:9105']
        labels:
          cluster: 'rdma'
```

Restart Prometheus:
```bash
sudo systemctl restart prometheus
```

## Step 9: Import Grafana Dashboard

1. Open Grafana (http://YOUR_SERVER:3000)
2. Go to Dashboards > Import
3. Upload `grafana/mpi_dashboard.json`
4. Select Prometheus data source
5. Click Import

## Step 10: Run Benchmarks

```bash
# Latency benchmarks (low traffic)
./mpi_test_controller.py start

# High-bandwidth stress test
./mpi_bandwidth_stress.py start

# Check status
./mpi_bandwidth_stress.py status
```

## Troubleshooting

### MPI Hangs
```bash
# Check if all nodes are reachable
for ip in $(cat ~/hostfile_rdma | awk '{print $1}'); do
    ssh -o ConnectTimeout=2 $ip hostname || echo "FAILED: $ip"
done
```

### UCX Transport Errors
```bash
# Use UD instead of RC for better stability
export UCX_TLS=ud_verbs,self,sm

# Debug UCX
export UCX_LOG_LEVEL=debug
```

### Low Performance
```bash
# Check RDMA device status
ibstat

# Verify PFC/ECN on switch
# (Check switch documentation)

# Use correct RDMA IPs in hostfile
cat ~/hostfile_rdma
```

### Exporter Not Working
```bash
# Check if running
ps aux | grep mpi_benchmark_exporter

# Check log
tail -f /tmp/mpi_exporter.log

# Restart
pkill -f mpi_benchmark_exporter
python3 mpi_benchmark_exporter.py &
```

## Network Requirements

### Switch Configuration (Cisco Nexus Example)

```
! Enable PFC on RDMA VLAN
class-map type qos match-all RDMA_TRAFFIC
  match cos 3

policy-map type qos RDMA_QOS
  class RDMA_TRAFFIC
    set qos-group 3

! Enable ECN
policy-map type queuing RDMA_QUEUING
  class type queuing c-out-8q-q3
    bandwidth percent 50
    random-detect minimum-threshold 100 kbytes maximum-threshold 200 kbytes
    congestion-control ecn
```

### Required Features
- **PFC (Priority Flow Control)**: Prevents packet drops under congestion
- **ECN (Explicit Congestion Notification)**: Signals congestion to endpoints
- **DCBX**: Negotiates QoS settings between NIC and switch

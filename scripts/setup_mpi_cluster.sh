#!/bin/bash
#
# MPI Cluster Setup Script
# Installs OpenMPI, UCX, and OSU Micro-Benchmarks on a single node
#
# Usage: ./setup_mpi_cluster.sh
# Run on each node in your cluster

set -e

echo "=========================================="
echo "MPI AI Cluster Benchmark - Node Setup"
echo "=========================================="

# Check if running as root
if [ "$EUID" -eq 0 ]; then
    echo "Please run as normal user (not root)"
    exit 1
fi

# Install dependencies
echo ""
echo "[1/5] Installing dependencies..."
sudo apt update
sudo apt install -y \
    build-essential \
    gfortran \
    libibverbs-dev \
    librdmacm-dev \
    rdma-core \
    infiniband-diags \
    perftest \
    wget \
    python3 \
    python3-pip

# Install UCX
echo ""
echo "[2/5] Installing UCX..."
cd /tmp
if [ ! -f ucx-1.14.1.tar.gz ]; then
    wget https://github.com/openucx/ucx/releases/download/v1.14.1/ucx-1.14.1.tar.gz
fi
tar xzf ucx-1.14.1.tar.gz
cd ucx-1.14.1
./configure --prefix=/usr/local --enable-mt
make -j$(nproc)
sudo make install
sudo ldconfig

# Install OpenMPI
echo ""
echo "[3/5] Installing OpenMPI..."
cd /tmp
if [ ! -f openmpi-4.1.6.tar.gz ]; then
    wget https://download.open-mpi.org/release/open-mpi/v4.1/openmpi-4.1.6.tar.gz
fi
tar xzf openmpi-4.1.6.tar.gz
cd openmpi-4.1.6
./configure --prefix=/usr/local --with-ucx=/usr/local --enable-mpi-cxx
make -j$(nproc)
sudo make install
sudo ldconfig

# Install OSU Micro-Benchmarks
echo ""
echo "[4/5] Installing OSU Micro-Benchmarks..."
cd /tmp
if [ ! -f osu-micro-benchmarks-7.3.tar.gz ]; then
    wget https://mvapich.cse.ohio-state.edu/download/mvapich/osu-micro-benchmarks-7.3.tar.gz
fi
tar xzf osu-micro-benchmarks-7.3.tar.gz
cd osu-micro-benchmarks-7.3
./configure CC=mpicc CXX=mpicxx --prefix=/usr/local
make -j$(nproc)
sudo make install

# Verify installation
echo ""
echo "[5/5] Verifying installation..."
echo ""
echo "OpenMPI version:"
mpirun --version | head -1

echo ""
echo "UCX version:"
ucx_info -v | head -1

echo ""
echo "OSU Benchmarks installed:"
ls /usr/local/libexec/osu-micro-benchmarks/mpi/collective/ | head -5

echo ""
echo "RDMA devices:"
ibv_devices 2>/dev/null || echo "No RDMA devices found"

echo ""
echo "=========================================="
echo "Setup complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Run this script on all cluster nodes"
echo "2. Configure passwordless SSH between nodes"
echo "3. Create hostfile with RDMA IPs"
echo "4. Test with: mpirun --hostfile hostfile -np N hostname"

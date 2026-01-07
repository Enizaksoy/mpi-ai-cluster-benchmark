# Troubleshooting Guide

Common issues and solutions when running MPI benchmarks on RDMA clusters.

## MPI Issues

### MPI Hangs or Times Out

**Symptoms**: `mpirun` command hangs, never completes

**Causes & Solutions**:

1. **SSH connectivity issues**
   ```bash
   # Test SSH to all nodes
   for ip in $(cat ~/hostfile_rdma | awk '{print $1}'); do
       ssh -o ConnectTimeout=2 $ip hostname || echo "FAILED: $ip"
   done
   ```

2. **Wrong IPs in hostfile**
   - Use RDMA IPs, not management IPs
   - Verify with: `ip addr show | grep '192.168.25'`

3. **Firewall blocking MPI ports**
   ```bash
   # Disable firewall temporarily
   sudo systemctl stop firewalld
   # Or allow MPI ports
   sudo firewall-cmd --add-port=1024-65535/tcp --permanent
   ```

### MPI Fails with "No route to host"

**Solution**: Check RDMA network configuration
```bash
# Verify RDMA interface is up
ip link show ens192

# Check routing
ip route | grep 192.168.25

# Test ping over RDMA network
ping -c 3 192.168.251.111
```

### Low Bandwidth / High Latency

**Possible causes**:

1. **Using wrong transport**
   ```bash
   # Force RDMA transport
   export UCX_TLS=ud_verbs,self,sm
   export UCX_NET_DEVICES=all
   ```

2. **Traffic going over Ethernet instead of RDMA**
   - Verify hostfile uses RDMA IPs
   - Check `ibstat` shows active ports

3. **Network congestion**
   - Check ECN/PFC counters on switch
   - Reduce concurrent traffic

## UCX Issues

### UCX Transport Errors

**Error**: `ucp_wireup.c:xxx UCX ERROR ...`

**Solution**: Use UD transport instead of RC
```bash
export UCX_TLS=ud_verbs,self,sm
```

### UCX Can't Find Devices

**Error**: `UCX ERROR no supported transports`

**Solution**:
```bash
# Check UCX sees RDMA devices
ucx_info -d

# List available transports
ucx_info -t

# Check RDMA devices exist
ibv_devices
ibstat
```

## RDMA Issues

### No RDMA Devices Found

```bash
# Check kernel modules
lsmod | grep mlx

# Load modules if missing
sudo modprobe mlx5_core
sudo modprobe mlx5_ib
sudo modprobe ib_uverbs

# Restart RDMA services
sudo systemctl restart rdma
```

### RDMA Device in "Down" State

```bash
# Check port state
ibstat

# If LinkUp but PortActive=no, check switch
# and verify cable connection
```

### Permission Denied on RDMA Operations

```bash
# Add user to RDMA group
sudo usermod -a -G rdma $USER

# Or set permissions
sudo chmod 666 /dev/infiniband/uverbs*
```

## Exporter Issues

### Exporter Won't Start

**Check Python version**:
```bash
python3 --version  # Need 3.6+
```

**Check port availability**:
```bash
netstat -tlnp | grep 9105
# Kill existing process if needed
pkill -f mpi_benchmark_exporter
```

**Check log**:
```bash
tail -50 /tmp/mpi_exporter.log
```

### Exporter Shows 0 for All Metrics

**Cause**: Benchmark is still running or failed

**Check**:
```bash
# See if benchmark is running
curl http://localhost:9105/metrics | grep mpi_benchmark_running
# 1 = running, 0 = idle

# Check exporter log for errors
tail -50 /tmp/mpi_exporter.log
```

### Prometheus Can't Scrape Exporter

**Check firewall**:
```bash
sudo firewall-cmd --add-port=9105/tcp --permanent
sudo firewall-cmd --reload
```

**Test from Prometheus server**:
```bash
curl http://EXPORTER_IP:9105/metrics
```

## Network Issues

### High ECN Rate

**Symptoms**: ECN rate > 500/s, high latencies

**Causes**:
1. Too much traffic for network capacity
2. Switch buffer exhaustion
3. Misconfigured QoS

**Solutions**:
1. Reduce concurrent benchmark traffic
2. Check switch buffer configuration
3. Verify PFC is enabled on correct priority

### PFC Storms

**Symptoms**: Network becomes very slow, switch CPU high

**Cause**: PFC pause frames cascading through network

**Solution**:
1. Enable PFC watchdog on switch
2. Configure proper ECN thresholds
3. Rate limit RDMA traffic if needed

## Performance Tuning

### Baseline Not Meeting Targets

1. **Check NIC settings**:
   ```bash
   ethtool -g ens192  # Ring buffer size
   ethtool -c ens192  # Coalescing settings
   ```

2. **Verify MTU**:
   ```bash
   ip link show ens192 | grep mtu
   # Should be 9000 for jumbo frames
   ```

3. **Check CPU governor**:
   ```bash
   cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor
   # Should be 'performance'

   # Set performance mode
   sudo cpupower frequency-set -g performance
   ```

4. **Disable CPU frequency scaling**:
   ```bash
   echo 1 | sudo tee /sys/devices/system/cpu/intel_pstate/no_turbo
   ```

### Inconsistent Results

**Cause**: Background processes, thermal throttling, or network jitter

**Solutions**:
1. Run benchmarks multiple times
2. Use larger iteration counts (-i 1000)
3. Pin MPI processes to specific CPUs
4. Check for thermal throttling: `sensors`

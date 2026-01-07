# Metrics Guide

Understanding MPI benchmark metrics and their relevance to AI training performance.

## Prometheus Metrics Reference

### Allreduce Latency
```prometheus
mpi_allreduce_latency_us{size="SIZE",nodes="N"}
```

**Sizes**: 4MB, 1MB, 64KB, 1KB

**What it measures**: Time for all nodes to contribute data, sum it, and distribute the result back to all nodes.

**AI Training relevance**:
- Called **every training step** for gradient synchronization
- Directly impacts training iteration time
- Large models (GPT, BERT) use 1MB-4MB gradients

**Expected values** (8 nodes, 25Gbps RDMA):
| Size | Good | Acceptable | Poor |
|------|------|------------|------|
| 4MB | < 30ms | 30-50ms | > 50ms |
| 1MB | < 10ms | 10-20ms | > 20ms |
| 64KB | < 500μs | 500μs-1ms | > 1ms |
| 1KB | < 100μs | 100-200μs | > 200μs |

### Broadcast Latency
```prometheus
mpi_broadcast_latency_us{size="SIZE",nodes="N"}
```

**Sizes**: 4MB, 1MB

**What it measures**: Time for root node to send data to all other nodes.

**AI Training relevance**:
- Model weight initialization
- Loading checkpoints
- Parameter server updates

**Expected values** (8 nodes):
| Size | Good | Acceptable | Poor |
|------|------|------------|------|
| 4MB | < 20ms | 20-30ms | > 30ms |
| 1MB | < 8ms | 8-15ms | > 15ms |

### Alltoall Latency
```prometheus
mpi_alltoall_latency_us{size="SIZE",nodes="N"}
```

**Size**: 1MB

**What it measures**: Time for every node to send data to every other node.

**AI Training relevance**:
- Mixture of Experts (MoE) models - routing tokens to experts
- Tensor parallelism communication
- All-to-all shuffles in distributed attention

**Expected values** (8 nodes):
| Size | Good | Acceptable | Poor |
|------|------|------------|------|
| 1MB | < 50ms | 50-100ms | > 100ms |

**Note**: Alltoall generates the most traffic: N × N × message_size

### Allgather Latency
```prometheus
mpi_allgather_latency_us{size="SIZE",nodes="N"}
```

**Size**: 128KB

**What it measures**: Time for each node to contribute data and all nodes receive the concatenated result.

**AI Training relevance**:
- Batch normalization statistics
- Gathering embeddings
- Ring-allreduce substep

**Expected values** (8 nodes):
| Size | Good | Acceptable | Poor |
|------|------|------------|------|
| 128KB | < 3ms | 3-10ms | > 10ms |

### Reduce Latency
```prometheus
mpi_reduce_latency_us{size="SIZE",nodes="N"}
```

**Size**: 1MB

**What it measures**: Time for all nodes to contribute data and root receives the sum.

**AI Training relevance**:
- Loss aggregation
- Metrics collection
- Gradient accumulation to master

**Expected values** (8 nodes):
| Size | Good | Acceptable | Poor |
|------|------|------------|------|
| 1MB | < 5ms | 5-10ms | > 10ms |

### Status Metrics

```prometheus
mpi_benchmark_success        # 1 = last run successful, 0 = failed
mpi_benchmark_running        # 1 = benchmark in progress, 0 = idle
mpi_benchmark_last_run_timestamp  # Unix timestamp of last run
```

## Traffic Calculations

### Per-Operation Traffic

For N nodes with message size M:

| Operation | Total Traffic | Formula |
|-----------|--------------|---------|
| Allreduce | N × M × 2 | Each node sends M, receives M |
| Broadcast | M × (N-1) | Root sends to N-1 nodes |
| Alltoall | N × N × M | Every node sends M to every node |
| Allgather | N × M | Each node sends M to all |
| Reduce | N × M | All nodes send to root |

### Example: 8 Nodes, 4MB Message

| Operation | Traffic Generated |
|-----------|------------------|
| Allreduce 4MB | 64 MB |
| Broadcast 4MB | 28 MB |
| Alltoall 1MB | 64 MB |

## Grafana Dashboard Panels

### Panel 1: MPI Allreduce Latency (Gradient Synchronization)

![Allreduce Panel](images/mpi_grafana.jpg)

Shows time-series of Allreduce latencies for different message sizes.

**Key observations**:
- Baseline latency when network is idle
- Spikes during congestion events
- Correlation with ECN activity

### Panel 2: MPI Collective Operations Latency

Shows Broadcast, Reduce, Allgather, and Alltoall in one view.

**What to look for**:
- Relative performance between operations
- Alltoall should be significantly higher (more traffic)
- Consistent ratios indicate healthy network

### Panel 3: Stat Panels

Quick view of current latencies:
- Allreduce 4MB
- Allreduce 1MB
- Broadcast 4MB
- Alltoall 1MB

**Color coding**:
- Green: Within target
- Yellow: Warning threshold
- Red: Critical threshold

### Panel 4: ECN/CNP Activity

Shows network congestion events:
- ECN marked packets (congestion detected by switch)
- CNP packets (congestion notification sent back)

**Interpreting ECN**:
- 0: No congestion
- 1-100/s: Light congestion, normal operation
- 100-500/s: Moderate congestion, PFC may activate
- > 500/s: Heavy congestion, investigate cause

## Correlating Metrics

### Latency vs ECN

When ECN increases:
1. Switch buffers are filling up
2. PFC may pause traffic
3. MPI latencies increase

**Example from our tests**:
- ECN: 200-600 packets/sec during stress test
- Allreduce 1MB: Increased from 6ms to 17ms
- This is normal behavior - lossless RDMA working correctly

### Bandwidth vs Latency

Higher bandwidth utilization → Higher latency due to:
1. Queue buildup at switch
2. Serialization delay for large messages
3. Contention in RDMA fabric

## Baseline Measurements

Before running workloads, establish baselines:

```bash
# Run single benchmark
./mpi_test_controller.py once

# Record baseline values
# Allreduce 1MB baseline: _____ μs
# Broadcast 1MB baseline: _____ μs
```

### Our Baseline (8 nodes, 25Gbps)

| Metric | Idle Baseline | Under Load |
|--------|--------------|------------|
| Allreduce 1MB | 5,000 μs | 10,000-26,000 μs |
| Allreduce 64KB | 400 μs | 484-1,820 μs |
| Broadcast 1MB | 5,000 μs | 5,870-8,630 μs |
| ECN rate | 0 | 200-600/s |

## Alerting Recommendations

### Prometheus Alert Rules

```yaml
groups:
- name: mpi_alerts
  rules:
  - alert: HighAllreduceLatency
    expr: mpi_allreduce_latency_us{size="1MB"} > 20000
    for: 5m
    labels:
      severity: warning
    annotations:
      summary: "Allreduce latency high"

  - alert: MPIBenchmarkFailed
    expr: mpi_benchmark_success == 0
    for: 1m
    labels:
      severity: critical
    annotations:
      summary: "MPI benchmark failed"

  - alert: HighECNRate
    expr: rate(rdma_ecn_marked_packets[5m]) > 500
    for: 5m
    labels:
      severity: warning
    annotations:
      summary: "High network congestion"
```

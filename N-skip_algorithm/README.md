# N-Skip Issue Policy Analysis

This repository analyzes the performance–power trade-off of a limited scan-depth
issue policy (N-skip with early-out) for power-constrained out-of-order cores.

## Motivation
Scanning only the head of an issue queue risks missing ready instructions,
while scanning the full window incurs linear power and complexity costs.
This study explores the optimal scan depth N.

## Methodology
- Analytical probability model: P(issue) = 1 - (1-p)^N
- Monte Carlo simulation (Model A): independent readiness
- Multi-cycle simulation (Model B): queue persistence

## Key Result
Across a wide range of instruction readiness (p=0.1–0.8),
performance-per-watt saturates early.
N=4 consistently appears as a robust balance point between
throughput recovery and hardware cost.

See:
- `analysis/N-Skip Issue Policy Analysis.xlsx` for graphs and data
- `simulation/` for reproducible code# N-Skip Issue Policy Analysis

This repository analyzes the performance–power trade-off of a limited scan-depth
issue policy (N-skip with early-out) for power-constrained out-of-order cores.

## Motivation
Scanning only the head of an issue queue risks missing ready instructions,
while scanning the full window incurs linear power and complexity costs.
This study explores the optimal scan depth N.

## Methodology
- Analytical probability model: P(issue) = 1 - (1-p)^N
- Monte Carlo simulation (Model A): independent readiness
- Multi-cycle simulation (Model B): queue persistence

## Key Result
Across a wide range of instruction readiness (p=0.1–0.8),
performance-per-watt saturates early.
N=4 consistently appears as a robust balance point between
throughput recovery and hardware cost.

See:
- `analysis/N-Skip Issue Policy Analysis.xlsx` for graphs and data
- `simulation/` for reproducible code

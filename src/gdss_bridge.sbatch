#!/bin/bash
#SBATCH --job-name=gdss-bridge
#SBATCH --partition=burst
#SBATCH --cpus-per-task=8
#SBATCH --mem=16G
#SBATCH --time=01:00:00
#SBATCH --output=gdss-bridge-%j.out
# The GDSS adapters for one residual-attractor request: writes <request dir>/cube/, fit_status.parquet, done.json.
# usage, from the repository root: sbatch src/gdss_bridge.sbatch residual-attractor/external/<request_id>
# MATLAB is installed on head only, so the job stays on the burst partition (head).
# Measured 2026-11-14 (smoke, 2 of spec 0's 14 series, all 31 configurations, 4 workers): about 930 CPU-seconds,
# most of it LSBoost's bootstrap forecasts; peak 1.9 GB. Spec 0 in full is about 6,500 CPU-seconds: ~15 min here.
set -euo pipefail
cd "${SLURM_SUBMIT_DIR:-$(pwd)}"
REQ="$(realpath "$1")"
nice -n 10 matlab -batch "addpath('src'); maxNumCompThreads(1); gdss.run_rattractor_request('${REQ}', workers=${SLURM_CPUS_PER_TASK:-8})"

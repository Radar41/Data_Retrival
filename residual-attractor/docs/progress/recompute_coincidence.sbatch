#!/bin/bash
#SBATCH --job-name=trackb-recompute
#SBATCH --cpus-per-task=8
#SBATCH --mem=4G
#SBATCH --time=00:30:00
#SBATCH --output=trackb-recompute-%j.out
# usage, from residual-attractor/: sbatch docs/progress/recompute_coincidence.sbatch <build dir> [n_rows]
cd "${SLURM_SUBMIT_DIR:-$(dirname "$0")/../..}"   # sbatch runs a spooled copy, so $0 is not this file
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 /home/radar-41-0/Documents/Data_Retrival/residual-attractor/.venv/bin/python -I docs/progress/recompute_coincidence.py "$1" "${2:-600}"

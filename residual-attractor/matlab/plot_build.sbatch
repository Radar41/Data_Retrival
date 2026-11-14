#!/bin/bash
#SBATCH --job-name=raplot
#SBATCH --partition=burst
#SBATCH --cpus-per-task=4
#SBATCH --mem=24G
#SBATCH --time=02:00:00
#SBATCH --output=raplot-%j.out
# Draw every stage of one build as PNGs into <build>/figures/ (about 5,700 files).
# usage, from residual-attractor/:  sbatch matlab/plot_build.sbatch builds/<build id>
# MATLAB is installed on head only, so the job runs on the burst partition (head).
# Smoke run (3 rows, 1 worker): about 2 min, 3.6 GB peak; the full run is about 25-40 min on 4 workers.
cd "${SLURM_SUBMIT_DIR:-$(dirname "$0")/..}"   # sbatch runs a spooled copy, so $0 is not this file
B="${1:?usage: sbatch matlab/plot_build.sbatch builds/<build id>}"
matlab -batch "addpath('matlab'); raplot.plot_build('$B', workers=4)"

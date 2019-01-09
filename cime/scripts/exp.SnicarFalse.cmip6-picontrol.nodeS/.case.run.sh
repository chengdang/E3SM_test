#!/bin/bash -e

# Batch system directives
#SBATCH  --job-name=exp.SnicarFalse.cmip6-picontrol.nodeS.run
#SBATCH  --nodes=39
#SBATCH  --output=exp.SnicarFalse.cmip6-picontrol.nodeS.run.%j 
#SBATCH  --exclusive 

# template to create a case run shell script. This should only ever be called
# by case.submit when on batch. Use case.submit from the command line to run your case.

# cd to case
cd /global/u2/c/cdang/E3SM_code_v1_mdf/20180420_SW_snicar/cime/scripts/exp.SnicarFalse.cmip6-picontrol.nodeS

# Set PYTHONPATH so we can make cime calls if needed
LIBDIR=/global/u2/c/cdang/E3SM_code_v1_mdf/20180420_SW_snicar/cime/scripts/lib
export PYTHONPATH=$LIBDIR:$PYTHONPATH

# get new lid
lid=$(python -c 'import CIME.utils; print CIME.utils.new_lid()')
export LID=$lid

# setup environment
source .env_mach_specific.sh

# Clean/make timing dirs
RUNDIR=$(./xmlquery RUNDIR --value)
if [ -e $RUNDIR/timing ]; then
    /bin/rm $RUNDIR/timing
fi
mkdir -p $RUNDIR/timing/checkpoints

# minimum namelist action
./preview_namelists --component cpl
#./preview_namelists # uncomment for full namelist generation

# uncomment for lockfile checking
# ./check_lockedfiles

# setup OMP_NUM_THREADS
export OMP_NUM_THREADS=$(./xmlquery THREAD_COUNT --value)

# save prerun provenance?

# MPIRUN!
cd $(./xmlquery RUNDIR --value)
srun  --label  -n 936  -c 2  --cpu_bind=cores  /global/cscratch1/sd/cdang/acme_scratch/edison/exp.SnicarFalse.cmip6-picontrol.nodeS/bld/e3sm.exe  >> e3sm.log.$LID 2>&1 

# save logs?

# save postrun provenance?

# resubmit ?

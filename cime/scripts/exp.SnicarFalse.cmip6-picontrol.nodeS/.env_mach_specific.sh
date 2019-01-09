source /opt/modules/default/init/sh
module rm PrgEnv-intel PrgEnv-cray PrgEnv-gnu intel cce gcc cray-parallel-netcdf cray-parallel-hdf5 pmi cray-libsci cray-mpich2 cray-mpich cray-netcdf cray-hdf5 cray-netcdf-hdf5parallel craype-sandybridge craype-ivybridge craype papi cray-petsc esmf craype
module load craype/2.5.12 craype-ivybridge
module rm pmi
module load pmi/5.0.12
module rm cray-mpich
module load pe_archive cray-mpich/7.6.0 PrgEnv-intel/6.0.4
module rm intel
module load intel/17.0.2.174
module rm cray-libsci cray-netcdf-hdf5parallel
module load cray-netcdf-hdf5parallel/4.4.1.1.6 cray-hdf5-parallel/1.10.1.1 cray-parallel-netcdf/1.8.1.3
export MPICH_ENV_DISPLAY=1
export MPICH_VERSION_DISPLAY=1
export MPICH_CPUMASK_DISPLAY=1
export OMP_STACKSIZE=64M
export OMP_PROC_BIND=spread
export OMP_PLACES=threads
export HDF5_USE_FILE_LOCKING=FALSE
export FORT_BUFFERED=yes
#
# COMPILER=intel
# OS=CNL
# MACH=edison
#
# Makefile Macros 
CPPDEFS+= -DFORTRANUNDERSCORE -DNO_R16 -DCPRINTEL  -DLINUX 

SLIBS+= -L$(NETCDF_DIR) -lnetcdff -Wl,--as-needed,-L$(NETCDF_DIR)/lib -lnetcdff -lnetcdf   -mkl -lpthread 

CFLAGS:= -O2 -fp-model precise -std=gnu99 

CMAKE_OPTS:= -DCMAKE_SYSTEM_NAME=Catamount

CONFIG_ARGS:= --host=Linux 

CXX_LDFLAGS:= -cxxlib 

CXX_LINKER:=FORTRAN

FC_AUTO_R8:= -r8 

FFLAGS:=  -convert big_endian -assume byterecl -ftz -traceback -assume realloc_lhs -fp-model source 

FFLAGS_NOOPT:= -O0 

FIXEDFLAGS:= -fixed -132 

FREEFLAGS:= -free 

GPTL_CPPDEFS:= -DHAVE_NANOTIME -DBIT64 -DHAVE_VPRINTF -DHAVE_BACKTRACE -DHAVE_SLASHPROC -DHAVE_COMM_F2C -DHAVE_TIMES -DHAVE_GETTIMEOFDAY  

HAS_F2008_CONTIGUOUS:=TRUE

MPICC:= cc 

MPICXX:= CC 

MPIFC:= ftn 

MPI_LIB_NAME:= mpich 

MPI_PATH:= $(MPICH_DIR)

NETCDF_PATH:=$(NETCDF_DIR)

PETSC_PATH:=$(PETSC_DIR)

PIO_FILESYSTEM_HINTS:=lustre

PNETCDF_PATH:=$(PARALLEL_NETCDF_DIR)

SCC:= icc 

SCXX:= icpc 

SFC:= ifort 

SUPPORTS_CXX:=TRUE

ifeq ($(DEBUG), FALSE) 
   FFLAGS +=  -O2 -debug minimal -qno-opt-dynamic-align 
   CFLAGS +=  -O2 -debug minimal 
endif

ifeq ($(DEBUG), TRUE) 
   FFLAGS +=  -O0 -g -check uninit -check bounds -check pointers -fpe0 -check noarg_temp_created 
   CFLAGS +=  -O0 -g 
endif

ifeq ($(compile_threaded), true) 
   FFLAGS +=  -qopenmp 
   FFLAGS_NOOPT +=  -qopenmp 
   LDFLAGS +=  -qopenmp 
   CFLAGS +=  -qopenmp 
endif

ifeq ($(MODEL), clm) 
  ifeq ($(CLM_PFLOTRAN_COLMODE), TRUE) 
    ifeq ($(CLM_PFLOTRAN_COUPLED), TRUE) 
       CPPDEFS +=  -DCOLUMN_MODE 
    endif

  endif

  ifeq ($(CLM_PFLOTRAN_COUPLED), TRUE) 
     FFLAGS +=  -I$(CLM_PFLOTRAN_SOURCE_DIR) 
     CPPDEFS +=  -DCLM_PFLOTRAN 
  endif

endif

ifeq ($(MODEL), driver) 
  ifeq ($(CLM_PFLOTRAN_COUPLED), TRUE) 
     LDFLAGS +=  -L$(CLM_PFLOTRAN_SOURCE_DIR) -lpflotran $(PETSC_LIB) 
  endif

endif

ifeq ($(MODEL), pop) 
   CPPDEFS +=  -D_USE_FLOW_CONTROL 
endif


"""
Common functions used by cime python scripts
Warning: you cannot use CIME Classes in this module as it causes circular dependencies
"""
import logging, gzip, sys, os, time, re, shutil, glob, string, random, imp
import stat as statlib
import warnings
from contextlib import contextmanager

# Return this error code if the scripts worked but tests failed
TESTS_FAILED_ERR_CODE = 100
logger = logging.getLogger(__name__)

@contextmanager
def redirect_stdout(new_target):
    old_target, sys.stdout = sys.stdout, new_target # replace sys.stdout
    try:
        yield new_target # run some code with the replaced stdout
    finally:
        sys.stdout = old_target # restore to the previous value


@contextmanager
def redirect_stderr(new_target):
    old_target, sys.stderr = sys.stderr, new_target # replace sys.stdout
    try:
        yield new_target # run some code with the replaced stdout
    finally:
        sys.stderr = old_target # restore to the previous value


def expect(condition, error_msg, exc_type=SystemExit, error_prefix="ERROR:"):
    """
    Similar to assert except doesn't generate an ugly stacktrace. Useful for
    checking user error, not programming error.

    >>> expect(True, "error1")
    >>> expect(False, "error2")
    Traceback (most recent call last):
        ...
    SystemExit: ERROR: error2
    """
    # Without this line we get a futurewarning on the use of condition below
    warnings.filterwarnings("ignore")
    if not condition:
        if logger.isEnabledFor(logging.DEBUG):
            import pdb
            pdb.set_trace()
        raise exc_type("{} {}".format(error_prefix, error_msg))

def id_generator(size=6, chars=string.ascii_lowercase + string.digits):
    return ''.join(random.choice(chars) for _ in range(size))

def check_name(fullname, additional_chars=None, fullpath=False):
    """
    check for unallowed characters in name, this routine only
    checks the final name and does not check if path exists or is
    writable

    >>> check_name("test.id", additional_chars=".")
    False
    >>> check_name("case.name", fullpath=False)
    True
    >>> check_name("/some/file/path/case.name", fullpath=True)
    True
    """

    chars = '<>/{}[\]~`@:' # pylint: disable=anomalous-backslash-in-string
    if additional_chars is not None:
        chars += additional_chars
    if fullpath:
        _, name = os.path.split(fullname)
    else:
        name = fullname
    match = re.search(r"["+re.escape(chars)+"]", name)
    if match is not None:
        logger.warn("Illegal character {} found in name {}".format(match.group(0), name))
        return False
    return True

# Should only be called from get_cime_config()
def _read_cime_config_file():
    """
    READ the config file in ~/.cime, this file may contain
    [main]
    CIME_MODEL=acme,cesm
    PROJECT=someprojectnumber
    """
    from ConfigParser import SafeConfigParser as config_parser

    cime_config_file = os.path.abspath(os.path.join(os.path.expanduser("~"),
                                                  ".cime","config"))
    cime_config = config_parser()
    if(os.path.isfile(cime_config_file)):
        cime_config.read(cime_config_file)
    else:
        logger.debug("File {} not found".format(cime_config_file))
        cime_config.add_section('main')

    return cime_config

_CIMECONFIG = None
def get_cime_config():
    global _CIMECONFIG
    if (not _CIMECONFIG):
        _CIMECONFIG = _read_cime_config_file()

    return _CIMECONFIG

def reset_cime_config():
    """
    Useful to keep unit tests from interfering with each other
    """
    global _CIMECONFIG
    _CIMECONFIG = None

def get_python_libs_location_within_cime():
    """
    From within CIME, return subdirectory of python libraries
    """
    return os.path.join("scripts", "lib")

def get_cime_root(case=None):
    """
    Return the absolute path to the root of CIME that contains this script

    >>> os.path.isdir(os.path.join(get_cime_root(), get_scripts_location_within_cime()))
    True
    """
    script_absdir = os.path.abspath(os.path.join(os.path.dirname(__file__),".."))
    assert script_absdir.endswith(get_python_libs_location_within_cime()), script_absdir
    cimeroot = os.path.abspath(os.path.join(script_absdir,"..",".."))

    if case is not None:
        case_cimeroot = os.path.abspath(case.get_value("CIMEROOT"))
        cimeroot = os.path.abspath(cimeroot)
        expect(cimeroot == case_cimeroot, "Inconsistent CIMEROOT variable: case -> '{}', file location -> '{}'".format(case_cimeroot, cimeroot))

    logger.debug( "CIMEROOT is " + cimeroot)
    return cimeroot

def set_model(model):
    """
    Set the model to be used in this session
    """
    cime_config = get_cime_config()
    cime_config.set('main','CIME_MODEL',model)

def get_model():
    """
    Get the currently configured model value
    The CIME_MODEL env variable may or may not be set

    >>> os.environ["CIME_MODEL"] = "garbage"
    >>> del os.environ["CIME_MODEL"]
    >>> set_model('rocky')
    >>> get_model()
    'rocky'
    >>> reset_cime_config()
    """
    model = os.environ.get("CIME_MODEL")
    if (model is not None):
        logger.debug("Setting CIME_MODEL={} from environment".format(model))
    else:
        cime_config = get_cime_config()
        if (cime_config.has_option('main','CIME_MODEL')):
            model = cime_config.get('main','CIME_MODEL')
            if model is not None:
                logger.debug("Setting CIME_MODEL={} from ~/.cime/config".format(model))

    # One last try
    if (model is None):
        srcroot = os.path.dirname(os.path.abspath(get_cime_root()))
        if os.path.isfile(os.path.join(srcroot, "SVN_EXTERNAL_DIRECTORIES")):
            model = 'cesm'
        else:
            model = 'acme'
        # This message interfers with the correct operation of xmlquery
        # logger.debug("Guessing CIME_MODEL={}, set environment variable if this is incorrect".format(model))

    if model is not None:
        set_model(model)
        return model

    modelroot = os.path.join(get_cime_root(), "config")
    models = os.listdir(modelroot)
    msg = ".cime/config or environment variable CIME_MODEL must be set to one of: "
    msg += ", ".join([model for model in models
                      if os.path.isdir(os.path.join(modelroot,model))
                      and model != "xml_schemas"])
    expect(False, msg)

def _convert_to_fd(filearg, from_dir):
    if not filearg.startswith("/") and from_dir is not None:
        filearg = os.path.join(from_dir, filearg)

    return open(filearg, "a")

_hack=object()

def run_sub_or_cmd(cmd, cmdargs, subname, subargs, logfile=None, case=None,
                   input_str=None, from_dir=None, verbose=None,
                   arg_stdout=_hack, arg_stderr=_hack, env=None, combine_output=False):

    # This code will try to import and run each buildnml as a subroutine
    # if that fails it will run it as a program in a seperate shell
    do_run_cmd = False
    stat = 0
    output = ""
    errput = ""
    try:
        mod = imp.load_source(subname, cmd)
        logger.info("   Calling {}".format(cmd))
        if logfile:
            with redirect_stdout(open(logfile,"w")):
                getattr(mod, subname)(*subargs)
        else:
            getattr(mod, subname)(*subargs)
    except SyntaxError:
        do_run_cmd = True
    except AttributeError:
        do_run_cmd = True
    except:
        raise

    if do_run_cmd:
        logger.info("   Running {} ".format(cmd))
        if case is not None:
            case.flush()
        stat, output, errput = run_cmd("{} {}".format(cmd, cmdargs), input_str=input_str, from_dir=from_dir,
                                 verbose=verbose, arg_stdout=arg_stdout, arg_stderr=arg_stderr, env=env,
                                 combine_output=combine_output)

        logger.info(output)
        # refresh case xml object from file
        if case is not None:
            case.read_xml()
    return stat, output, errput

def run_cmd(cmd, input_str=None, from_dir=None, verbose=None,
            arg_stdout=_hack, arg_stderr=_hack, env=None, combine_output=False):
    """
    Wrapper around subprocess to make it much more convenient to run shell commands

    >>> run_cmd('ls file_i_hope_doesnt_exist')[0] != 0
    True
    """
    import subprocess # Not safe to do globally, module not available in older pythons

    # Real defaults for these value should be subprocess.PIPE
    if arg_stdout is _hack:
        arg_stdout = subprocess.PIPE
    elif isinstance(arg_stdout, str):
        arg_stdout = _convert_to_fd(arg_stdout, from_dir)

    if arg_stderr is _hack:
        arg_stderr = subprocess.STDOUT if combine_output else subprocess.PIPE
    elif isinstance(arg_stderr, str):
        arg_stderr = _convert_to_fd(arg_stdout, from_dir)

    if (verbose != False and (verbose or logger.isEnabledFor(logging.DEBUG))):
        logger.info("RUN: {}".format(cmd))

    if (input_str is not None):
        stdin = subprocess.PIPE
    else:
        stdin = None

    proc = subprocess.Popen(cmd,
                            shell=True,
                            stdout=arg_stdout,
                            stderr=arg_stderr,
                            stdin=stdin,
                            cwd=from_dir,
                            env=env)

    output, errput = proc.communicate(input_str)
    output = output.strip() if output is not None else output
    errput = errput.strip() if errput is not None else errput
    stat = proc.wait()

    if isinstance(arg_stdout, file):
        arg_stdout.close() # pylint: disable=no-member

    if isinstance(arg_stderr, file) and arg_stderr is not arg_stdout:
        arg_stderr.close() # pylint: disable=no-member

    if (verbose != False and (verbose or logger.isEnabledFor(logging.DEBUG))):
        if stat != 0:
            logger.info("  stat: {:d}\n".format(stat))
        if output:
            logger.info("  output: {}\n".format(output))
        if errput:
            logger.info("  errput: {}\n".format(errput))

    return stat, output, errput

def run_cmd_no_fail(cmd, input_str=None, from_dir=None, verbose=None,
                    arg_stdout=_hack, arg_stderr=_hack, env=None, combine_output=False):
    """
    Wrapper around subprocess to make it much more convenient to run shell commands.
    Expects command to work. Just returns output string.

    >>> run_cmd_no_fail('echo foo')
    'foo'

    >>> run_cmd_no_fail('echo THE ERROR >&2; false') # doctest:+ELLIPSIS
    Traceback (most recent call last):
        ...
    SystemExit: ERROR: Command: 'echo THE ERROR >&2; false' failed with error 'THE ERROR' from dir ...

    >>> run_cmd_no_fail('grep foo', input_str='foo')
    'foo'

    >>> run_cmd_no_fail('echo THE ERROR >&2', combine_output=True)
    'THE ERROR'
    """
    stat, output, errput = run_cmd(cmd, input_str, from_dir, verbose, arg_stdout, arg_stderr, env, combine_output)
    if stat != 0:
        # If command produced no errput, put output in the exception since we
        # have nothing else to go on.
        errput = output if not errput else errput
        expect(False, "Command: '{}' failed with error '{}' from dir '{}'".format(cmd, errput, os.getcwd() if from_dir is None else from_dir))

    return output

def check_minimum_python_version(major, minor):
    """
    Check your python version.

    >>> check_minimum_python_version(sys.version_info[0], sys.version_info[1])
    >>>
    """
    expect(sys.version_info[0] == major and sys.version_info[1] >= minor,
           "Python {:d}, minor version {:d}+ is required, you have {:d}.{:d}".format(major, minor, sys.version_info[0], sys.version_info[1]))

def normalize_case_id(case_id):
    """
    Given a case_id, return it in form TESTCASE.GRID.COMPSET.PLATFORM

    >>> normalize_case_id('ERT.ne16_g37.B1850C5.skybridge_intel')
    'ERT.ne16_g37.B1850C5.skybridge_intel'
    >>> normalize_case_id('ERT.ne16_g37.B1850C5.skybridge_intel.test-mod')
    'ERT.ne16_g37.B1850C5.skybridge_intel.test-mod'
    >>> normalize_case_id('ERT.ne16_g37.B1850C5.skybridge_intel.G.20151121')
    'ERT.ne16_g37.B1850C5.skybridge_intel'
    >>> normalize_case_id('ERT.ne16_g37.B1850C5.skybridge_intel.test-mod.G.20151121')
    'ERT.ne16_g37.B1850C5.skybridge_intel.test-mod'
    """
    sep_count = case_id.count(".")
    expect(sep_count >= 3 and sep_count <= 6,
           "Case '{}' needs to be in form: TESTCASE.GRID.COMPSET.PLATFORM[.TESTMOD]  or  TESTCASE.GRID.COMPSET.PLATFORM[.TESTMOD].GC.TESTID".format(case_id))
    if (sep_count in [5, 6]):
        return ".".join(case_id.split(".")[:-2])
    else:
        return case_id

def parse_test_name(test_name):
    """
    Given a CIME test name TESTCASE[_CASEOPTS].GRID.COMPSET[.MACHINE_COMPILER[.TESTMODS]],
    return each component of the testname with machine and compiler split.
    Do not error if a partial testname is provided (TESTCASE or TESTCASE.GRID) instead
    parse and return the partial results.

    >>> parse_test_name('ERS')
    ['ERS', None, None, None, None, None, None]
    >>> parse_test_name('ERS.fe12_123')
    ['ERS', None, 'fe12_123', None, None, None, None]
    >>> parse_test_name('ERS.fe12_123.JGF')
    ['ERS', None, 'fe12_123', 'JGF', None, None, None]
    >>> parse_test_name('ERS_D.fe12_123.JGF')
    ['ERS', ['D'], 'fe12_123', 'JGF', None, None, None]
    >>> parse_test_name('ERS_D_P1.fe12_123.JGF')
    ['ERS', ['D', 'P1'], 'fe12_123', 'JGF', None, None, None]
    >>> parse_test_name('SMS_D_Ln9_Mmpi-serial.f19_g16_rx1.A')
    ['SMS', ['D', 'Ln9', 'Mmpi-serial'], 'f19_g16_rx1', 'A', None, None, None]
    >>> parse_test_name('ERS.fe12_123.JGF.machine_compiler')
    ['ERS', None, 'fe12_123', 'JGF', 'machine', 'compiler', None]
    >>> parse_test_name('ERS.fe12_123.JGF.machine_compiler.test-mods')
    ['ERS', None, 'fe12_123', 'JGF', 'machine', 'compiler', 'test/mods']
    >>> parse_test_name('SMS.f19_g16.2000_DATM%QI.A_XLND_SICE_SOCN_XROF_XGLC_SWAV.mach-ine_compiler.test-mods')
    Traceback (most recent call last):
        ...
    SystemExit: ERROR: Expected 4th item of 'SMS.f19_g16.2000_DATM%QI.A_XLND_SICE_SOCN_XROF_XGLC_SWAV.mach-ine_compiler.test-mods' ('A_XLND_SICE_SOCN_XROF_XGLC_SWAV') to be in form machine_compiler
    >>> parse_test_name('SMS.f19_g16.2000_DATM%QI/A_XLND_SICE_SOCN_XROF_XGLC_SWAV.mach-ine_compiler.test-mods')
    Traceback (most recent call last):
        ...
    SystemExit: ERROR: Invalid compset name 2000_DATM%QI/A_XLND_SICE_SOCN_XROF_XGLC_SWAV
    """
    rv = [None] * 7
    num_dots = test_name.count(".")

    rv[0:num_dots+1] = test_name.split(".")
    testcase_field_underscores = rv[0].count("_")
    rv.insert(1, None) # Make room for caseopts
    rv.pop()
    if (testcase_field_underscores > 0):
        full_str = rv[0]
        rv[0]    = full_str.split("_")[0]
        rv[1]    = full_str.split("_")[1:]

    if (num_dots >= 3):
        expect(check_name( rv[3] ), "Invalid compset name {}".format(rv[3]))

        expect(rv[4].count("_") == 1,
               "Expected 4th item of '{}' ('{}') to be in form machine_compiler".format(test_name, rv[4]))
        rv[4:5] = rv[4].split("_")
        rv.pop()

    if (rv[-1] is not None):
        rv[-1] = rv[-1].replace("-", "/")

    expect(num_dots <= 4,
           "'{}' does not look like a CIME test name, expect TESTCASE.GRID.COMPSET[.MACHINE_COMPILER[.TESTMODS]]".format(test_name))

    return rv

def get_full_test_name(partial_test, caseopts=None, grid=None, compset=None, machine=None, compiler=None, testmod=None):
    """
    Given a partial CIME test name, return in form TESTCASE.GRID.COMPSET.MACHINE_COMPILER[.TESTMODS]
    Use the additional args to fill out the name if needed

    >>> get_full_test_name("ERS", grid="ne16_fe16", compset="JGF", machine="melvin", compiler="gnu")
    'ERS.ne16_fe16.JGF.melvin_gnu'
    >>> get_full_test_name("ERS", caseopts=["D", "P16"], grid="ne16_fe16", compset="JGF", machine="melvin", compiler="gnu")
    'ERS_D_P16.ne16_fe16.JGF.melvin_gnu'
    >>> get_full_test_name("ERS.ne16_fe16", compset="JGF", machine="melvin", compiler="gnu")
    'ERS.ne16_fe16.JGF.melvin_gnu'
    >>> get_full_test_name("ERS.ne16_fe16.JGF", machine="melvin", compiler="gnu")
    'ERS.ne16_fe16.JGF.melvin_gnu'
    >>> get_full_test_name("ERS.ne16_fe16.JGF.melvin_gnu.mods", machine="melvin", compiler="gnu")
    'ERS.ne16_fe16.JGF.melvin_gnu.mods'
    >>> get_full_test_name("ERS.ne16_fe16.JGF", machine="melvin", compiler="gnu", testmod="mods/test")
    'ERS.ne16_fe16.JGF.melvin_gnu.mods-test'
    """
    partial_testcase, partial_caseopts, partial_grid, partial_compset, partial_machine, partial_compiler, partial_testmod = parse_test_name(partial_test)

    required_fields = [
        (partial_grid, grid, "grid"),
        (partial_compset, compset, "compset"),
        (partial_machine, machine, "machine"),
        (partial_compiler, compiler, "compiler"),
        ]

    result = partial_test

    for partial_val, arg_val, name in required_fields:
        if (partial_val is None):
            # Add to result based on args
            expect(arg_val is not None,
                   "Could not fill-out test name, partial string '{}' had no {} information and you did not provide any".format(partial_test, name))
            result = "{}{}{}".format(result, "_" if name == "compiler" else ".", arg_val)
        elif (arg_val is not None and partial_val != partial_compiler):
            expect(arg_val == partial_val,
                   "Mismatch in field {}, partial string '{}' indicated it should be '{}' but you provided '{}'".format(name, partial_test, partial_val, arg_val))

    if (partial_testmod is None):
        if (testmod is None):
            # No testmod for this test and that's OK
            pass
        else:
            result += ".{}".format(testmod.replace("/", "-"))
    elif (testmod is not None):
        expect(testmod == partial_testmod,
               "Mismatch in field testmod, partial string '{}' indicated it should be '{}' but you provided '{}'".format(partial_test, partial_testmod, testmod))

    if (partial_caseopts is None):
        if caseopts is None:
            # No casemods for this test and that's OK
            pass
        else:
            result = result.replace(partial_testcase, "{}_{}".format(partial_testcase, "_".join(caseopts)), 1)
    elif caseopts is not None:
        expect(caseopts == partial_caseopts,
               "Mismatch in field caseopts, partial string '{}' indicated it should be '{}' but you provided '{}'".format(partial_test, partial_caseopts, caseopts))

    return result

def get_current_branch(repo=None):
    """
    Return the name of the current branch for a repository

    >>> get_current_branch() is not None
    True
    """
    if ("GIT_BRANCH" in os.environ):
        # This approach works better for Jenkins jobs because the Jenkins
        # git plugin does not use local tracking branches, it just checks out
        # to a commit
        branch = os.environ["GIT_BRANCH"]
        if (branch.startswith("origin/")):
            branch = branch.replace("origin/", "", 1)
        return branch
    else:
        stat, output, _ = run_cmd("git symbolic-ref HEAD", from_dir=repo)
        if (stat != 0):
            return None
        else:
            return output.replace("refs/heads/", "")

def get_current_commit(short=False, repo=None):
    """
    Return the sha1 of the current HEAD commit

    >>> get_current_commit() is not None
    True
    """
    rc, output, _ = run_cmd("git rev-parse {} HEAD".format("--short" if short else ""), from_dir=repo)
    if rc == 0:
        return output
    else:
        return 'unknown'

def get_scripts_location_within_cime():
    """
    From within CIME, return subdirectory where scripts live.
    """
    return "scripts"

def get_cime_location_within_acme():
    """
    From within acme, return subdirectory where CIME lives.
    """
    return "cime"

def get_model_config_location_within_cime(model=None):
    model = get_model() if model is None else model
    return os.path.join("config", model)

def get_acme_root():
    """
    Return the absolute path to the root of ACME that contains this script
    """
    cime_absdir = get_cime_root()
    assert cime_absdir.endswith(get_cime_location_within_acme()), cime_absdir
    return os.path.normpath(cime_absdir[:len(cime_absdir)-len(get_cime_location_within_acme())])

def get_scripts_root():
    """
    Get absolute path to scripts

    >>> os.path.isdir(get_scripts_root())
    True
    """
    return os.path.join(get_cime_root(), get_scripts_location_within_cime())

def get_python_libs_root():
    """
    Get absolute path to scripts

    >>> os.path.isdir(get_python_libs_root())
    True
    """
    return os.path.join(get_cime_root(), get_python_libs_location_within_cime())

def get_model_config_root(model=None):
    """
    Get absolute path to model config area"

    >>> os.path.isdir(get_model_config_root())
    True
    """
    model = get_model() if model is None else model
    return os.path.join(get_cime_root(), get_model_config_location_within_cime(model))

def stop_buffering_output():
    """
    All stdout, stderr will not be buffered after this is called.
    """
    os.environ['PYTHONUNBUFFERED'] = '1'

def start_buffering_output():
    """
    All stdout, stderr will be buffered after this is called. This is python's
    default behavior.
    """
    sys.stdout.flush()
    sys.stdout = os.fdopen(sys.stdout.fileno(), 'w')

def match_any(item, re_list):
    """
    Return true if item matches any regex in re_list
    """
    for regex_str in re_list:
        regex = re.compile(regex_str)
        if (regex.match(item)):
            return True

    return False

def safe_copy(src_dir, tgt_dir, file_map):
    """
    Copies a set of files from one dir to another. Works even if overwriting a
    read-only file. Files can be relative paths and the relative path will be
    matched on the tgt side.
    """
    for src_file, tgt_file in file_map:
        full_tgt = os.path.join(tgt_dir, tgt_file)
        full_src = src_file if os.path.isabs(src_file) else os.path.join(src_dir, src_file)
        expect(os.path.isfile(full_src), "Source dir '{}' missing file '{}'".format(src_dir, src_file))
        if (os.path.isfile(full_tgt)):
            os.remove(full_tgt)
        shutil.copy2(full_src, full_tgt)

def find_proc_id(proc_name=None,
                 children_only=False,
                 of_parent=None):
    """
    Children implies recursive.
    """
    expect(proc_name is not None or children_only,
           "Must provide proc_name if not searching for children")
    expect(not (of_parent is not None and not children_only),
           "of_parent only used with children_only")

    parent = of_parent if of_parent is not None else os.getpid()

    pgrep_cmd = "pgrep {} {}".format(proc_name if proc_name is not None else "",
                                 "-P {:d}".format(parent if children_only else ""))
    stat, output, errput = run_cmd(pgrep_cmd)
    expect(stat in [0, 1], "pgrep failed with error: '{}'".format(errput))

    rv = set([int(item.strip()) for item in output.splitlines()])
    if (children_only):
        pgrep_cmd = "pgrep -P {}".format(parent)
        stat, output, errput = run_cmd(pgrep_cmd)
        expect(stat in [0, 1], "pgrep failed with error: '{}'".format(errput))

        for child in output.splitlines():
            rv = rv.union(set(find_proc_id(proc_name, children_only, int(child.strip()))))

    return list(rv)

def get_timestamp(timestamp_format="%Y%m%d_%H%M%S", utc_time=False):
    """
    Get a string representing the current UTC time in format: YYMMDD_HHMMSS

    The format can be changed if needed.
    """
    if utc_time:
        time_tuple = time.gmtime()
    else:
        time_tuple = time.localtime()
    return time.strftime(timestamp_format, time_tuple)

def get_project(machobj=None):
    """
    Hierarchy for choosing PROJECT:
    0. Command line flag to create_newcase or create_test
    1. Environment variable PROJECT
    2  Environment variable ACCOUNT  (this is for backward compatibility)
    3. File $HOME/.cime/config       (this is new)
    4  File $HOME/.cesm_proj         (this is for backward compatibility)
    5  config_machines.xml (if machobj provided)
    """
    project = os.environ.get("PROJECT")
    if (project is not None):
        logger.info("Using project from env PROJECT: " + project)
        return project
    project = os.environ.get("ACCOUNT")
    if (project is not None):
        logger.info("Using project from env ACCOUNT: " + project)
        return project

    cime_config = get_cime_config()
    if (cime_config.has_option('main','PROJECT')):
        project = cime_config.get('main','PROJECT')
        if (project is not None):
            logger.info("Using project from .cime/config: " + project)
            return project

    projectfile = os.path.abspath(os.path.join(os.path.expanduser("~"), ".cesm_proj"))
    if (os.path.isfile(projectfile)):
        with open(projectfile,'r') as myfile:
            for line in myfile:
                project = line.rstrip()
                if not project.startswith("#"):
                    break
            logger.info("Using project from .cesm_proj: " + project)
            cime_config.set('main','PROJECT',project)
            return project

    if machobj is not None:
        project = machobj.get_value("PROJECT")
        if project is not None:
            logger.info("Using project from config_machines.xml: " + project)
            return project

    logger.info("No project info available")
    return None

def setup_standard_logging_options(parser):
    helpfile = "{}.log".format(sys.argv[0])
    helpfile = os.path.join(os.getcwd(),os.path.basename(helpfile))
    parser.add_argument("-d", "--debug", action="store_true",
                        help="Print debug information (very verbose) to file {}".format(helpfile))
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Add additional context (time and file) to log messages")
    parser.add_argument("-s", "--silent", action="store_true",
                        help="Print only warnings and error messages")

class _LessThanFilter(logging.Filter):
    def __init__(self, exclusive_maximum, name=""):
        super(_LessThanFilter, self).__init__(name)
        self.max_level = exclusive_maximum

    def filter(self, record):
        #non-zero return means we log this message
        return 1 if record.levelno < self.max_level else 0

def parse_args_and_handle_standard_logging_options(args, parser=None):
    """
    Guide to logging in CIME.

    logger.debug -> Verbose/detailed output, use for debugging, off by default. Goes to a .log file
    logger.info -> Goes to stdout (and log if --debug). Use for normal program output
    logger.warning -> Goes to stderr (and log if --debug). Use for minor problems
    logger.error -> Goes to stderr (and log if --debug)
    """
    root_logger = logging.getLogger()

    verbose_formatter   = logging.Formatter(fmt='%(asctime)s %(name)-12s %(levelname)-8s %(message)s',
                                            datefmt='%m-%d %H:%M')

    # Change info to go to stdout. This handle applies to INFO exclusively
    stdout_stream_handler = logging.StreamHandler(stream=sys.stdout)
    stdout_stream_handler.setLevel(logging.INFO)
    stdout_stream_handler.addFilter(_LessThanFilter(logging.WARNING))

    # Change warnings and above to go to stderr
    stderr_stream_handler = logging.StreamHandler(stream=sys.stderr)
    stderr_stream_handler.setLevel(logging.WARNING)

    # scripts_regression_tests is the only thing that should pass a None argument in parser
    if parser is not None:
        _check_for_invalid_args(args[1:])
        args = parser.parse_args(args[1:])

    # --verbose adds to the message format but does not impact the log level
    if args.verbose:
        stdout_stream_handler.setFormatter(verbose_formatter)
        stderr_stream_handler.setFormatter(verbose_formatter)

    root_logger.addHandler(stdout_stream_handler)
    root_logger.addHandler(stderr_stream_handler)

    if args.debug:
        # Set up log file to catch ALL logging records
        log_file = "{}.log".format(os.path.basename(sys.argv[0]))

        debug_log_handler = logging.FileHandler(log_file, mode='w')
        debug_log_handler.setFormatter(verbose_formatter)
        debug_log_handler.setLevel(logging.DEBUG)
        root_logger.addHandler(debug_log_handler)

        root_logger.setLevel(logging.DEBUG)
    elif args.silent:
        root_logger.setLevel(logging.WARN)
    else:
        root_logger.setLevel(logging.INFO)
    return args


def get_logging_options():
    """
    Use to pass same logging options as was used for current
    executable to subprocesses.
    """
    root_logger = logging.getLogger()

    if (root_logger.level == logging.DEBUG):
        return "--debug"
    elif (root_logger.level == logging.WARN):
        return "--silent"
    else:
        return ""

def convert_to_type(value, type_str, vid=""):
    """
    Convert value from string to another type.
    vid is only for generating better error messages.
    """
    if value is not None:

        if type_str == "char":
            pass

        elif type_str == "integer":
            try:
                value = int(eval(value))
            except:
                expect(False, "Entry {} was listed as type int but value '{}' is not valid int".format(vid, value))

        elif type_str == "logical":
            expect(value.upper() in ["TRUE", "FALSE"],
                   "Entry {} was listed as type logical but had val '{}' instead of TRUE or FALSE".format(vid, value))
            value = value.upper() == "TRUE"

        elif type_str == "real":
            try:
                value = float(value)
            except:
                expect(False, "Entry {} was listed as type real but value '{}' is not valid real".format(vid, value))

        else:
            expect(False, "Unknown type '{}'".format(type_str))

    return value

def convert_to_unknown_type(value):
    """
    Convert value to it's real type by probing conversions.
    """
    if value is not None:

        # Attempt to convert to logical
        if value.upper() in ["TRUE", "FALSE"]:
            return value.upper() == "TRUE"

        # Attempt to convert to integer
        try:
            value = int(eval(value))
        except:
            pass
        else:
            return value

        # Attempt to convert to float
        try:
            value = float(value)
        except:
            pass
        else:
            return value

        # Just treat as string

    return value

def convert_to_string(value, type_str=None, vid=""):
    """
    Convert value back to string.
    vid is only for generating better error messages.
    """
    if value is not None and type(value) is not str:
        if type_str == "char":
            expect(type(value) is str, "Wrong type for entry id '{}'".format(vid))
        elif type_str == "integer":
            expect(type(value) is int, "Wrong type for entry id '{}'".format(vid))
            value = str(value)
        elif type_str == "logical":
            expect(type(value) is bool, "Wrong type for entry id '{}'".format(vid))
            value = "TRUE" if value else "FALSE"
        elif type_str == "real":
            expect(type(value) is float, "Wrong type for entry id '{}'".format(vid))
            value = str(value)
        else:
            expect(False, "Unknown type '{}'".format(type_str))
    if value is None:
        value = ""
        logger.debug("Attempt to convert None value for vid {} {}".format(vid,value))

    return value

def convert_to_seconds(time_str):
    """
    Convert time value in [[HH:]MM:]SS to seconds

    >>> convert_to_seconds("42")
    42
    >>> convert_to_seconds("01:01:01")
    3661
    """
    components = time_str.split(":")
    expect(len(components) < 4, "Unusual time string: '{}'".format(time_str))

    components.reverse()
    result = 0
    for idx, component in enumerate(components):
        result += int(component) * pow(60, idx)

    return result

def convert_to_babylonian_time(seconds):
    """
    Convert time value to seconds to HH:MM:SS

    >>> convert_to_babylonian_time(3661)
    '01:01:01'
    """
    hours = seconds / 3600
    seconds %= 3600
    minutes = seconds / 60
    seconds %= 60

    return "{:02d}:{:02d}:{:02d}".format(hours, minutes, seconds)

def get_time_in_seconds(timeval, unit):
    """
    Convert a time from 'unit' to seconds
    """
    if 'nyear' in unit:
        dmult = 365 * 24 * 3600
    elif 'nmonth' in unit:
        dmult = 30 * 24 * 3600
    elif 'nday' in unit:
        dmult = 24 * 3600
    elif 'nhour' in unit:
        dmult = 3600
    elif 'nminute' in unit:
        dmult = 60
    else:
        dmult = 1

    return dmult * timeval

def compute_total_time(job_cost_map, proc_pool):
    """
    Given a map: jobname -> (procs, est-time), return a total time
    estimate for a given processor pool size

    >>> job_cost_map = {"A" : (4, 3000), "B" : (2, 1000), "C" : (8, 2000), "D" : (1, 800)}
    >>> compute_total_time(job_cost_map, 8)
    5160
    >>> compute_total_time(job_cost_map, 12)
    3180
    >>> compute_total_time(job_cost_map, 16)
    3060
    """
    current_time = 0
    waiting_jobs = dict(job_cost_map)
    running_jobs = {} # name -> (procs, est-time, start-time)
    while len(waiting_jobs) > 0 or len(running_jobs) > 0:
        launched_jobs = []
        for jobname, data in waiting_jobs.iteritems():
            procs_for_job, time_for_job = data
            if procs_for_job <= proc_pool:
                proc_pool -= procs_for_job
                launched_jobs.append(jobname)
                running_jobs[jobname] = (procs_for_job, time_for_job, current_time)

        for launched_job in launched_jobs:
            del waiting_jobs[launched_job]

        completed_jobs = []
        for jobname, data in running_jobs.iteritems():
            procs_for_job, time_for_job, time_started = data
            if (current_time - time_started) >= time_for_job:
                proc_pool += procs_for_job
                completed_jobs.append(jobname)

        for completed_job in completed_jobs:
            del running_jobs[completed_job]

        current_time += 60 # minute time step

    return current_time

def format_time(time_format, input_format, input_time):
    """
    Converts the string input_time from input_format to time_format
    Valid format specifiers are "%H", "%M", and "%S"
    % signs must be followed by an H, M, or S and then a separator
    Separators can be any string without digits or a % sign
    Each specifier can occur more than once in the input_format,
    but only the first occurence will be used.
    An example of a valid format: "%H:%M:%S"
    Unlike strptime, this does support %H >= 24

    >>> format_time("%H:%M:%S", "%H", "43")
    '43:00:00'
    >>> format_time("%H  %M", "%M,%S", "59,59")
    '0  59'
    >>> format_time("%H, %S", "%H:%M:%S", "2:43:9")
    '2, 09'
    """
    input_fields = input_format.split("%")
    expect(input_fields[0] == input_time[:len(input_fields[0])],
           "Failed to parse the input time; does not match the header string")
    input_time = input_time[len(input_fields[0]):]
    timespec = {"H": None, "M": None, "S": None}
    maxvals = {"M": 60, "S": 60}
    DIGIT_CHECK = re.compile('[^0-9]*')
    # Loop invariants given input follows the specs:
    # field starts with H, M, or S
    # input_time starts with a number corresponding with the start of field
    for field in input_fields[1:]:
        # Find all of the digits at the start of the string
        spec = field[0]
        value_re = re.match(r'\d*', input_time)
        expect(value_re is not None,
               "Failed to parse the input time for the '{}' specifier, expected an integer".format(spec))
        value = value_re.group(0)
        expect(spec in timespec, "Unknown time specifier '" + spec + "'")
        # Don't do anything if the time field is already specified
        if timespec[spec] is None:
            # Verify we aren't exceeding the maximum value
            if spec in maxvals:
                expect(int(value) < maxvals[spec],
                       "Failed to parse the '{}' specifier: A value less than {:d} is expected".format(spec, maxvals[spec]))
            timespec[spec] = value
        input_time = input_time[len(value):]
        # Check for the separator string
        expect(len(re.match(DIGIT_CHECK, field).group(0)) == len(field),
               "Numbers are not permissible in separator strings")
        expect(input_time[:len(field) - 1] == field[1:],
               "The separator string ({}) doesn't match '{}'".format(field[1:], input_time))
        input_time = input_time[len(field) - 1:]
    output_fields = time_format.split("%")
    output_time = output_fields[0]
    # Used when a value isn't given
    min_len_spec = {"H": 1, "M": 2, "S": 2}
    # Loop invariants given input follows the specs:
    # field starts with H, M, or S
    # output_time
    for field in output_fields[1:]:
        expect(field == output_fields[-1] or len(field) > 1,
               "Separator strings are required to properly parse times")
        spec = field[0]
        expect(spec in timespec, "Unknown time specifier '" + spec + "'")
        if timespec[spec] is not None:
            output_time += "0" * (min_len_spec[spec] - len(timespec[spec]))
            output_time += timespec[spec]
        else:
            output_time += "0" * min_len_spec[spec]
        output_time += field[1:]
    return output_time

def append_status(msg, sfile, caseroot='.'):
    """
    Append msg to sfile in caseroot
    """
    ctime = time.strftime("%Y-%m-%d %H:%M:%S: ")

    # Reduce empty lines in CaseStatus. It's a very concise file
    # and does not need extra newlines for readability
    line_ending = "" if sfile == "CaseStatus" else "\n"

    with open(os.path.join(caseroot, sfile), "a") as fd:
        fd.write(ctime + msg + line_ending)
        fd.write("\n ---------------------------------------------------\n" + line_ending)

def append_testlog(msg, caseroot='.'):
    """
    Add to TestStatus.log file
    """
    append_status(msg, "TestStatus.log", caseroot)

def append_case_status(phase, status, msg=None, caseroot='.'):
    """
    Update CaseStatus file
    """
    append_status("{} {}{}".format(phase, status, " {}".format(msg if msg else "")), "CaseStatus", caseroot)

def does_file_have_string(filepath, text):
    """
    Does the text string appear in the filepath file
    """
    return os.path.isfile(filepath) and text in open(filepath).read()

def transform_vars(text, case=None, subgroup=None, check_members=None, default=None):
    """
    Do the variable substitution for any variables that need transforms
    recursively.

    >>> transform_vars("{{ cesm_stdout }}", default="cesm.stdout")
    'cesm.stdout'
    >>> member_store = lambda : None
    >>> member_store.foo = "hi"
    >>> transform_vars("I say {{ foo }}", check_members=member_store)
    'I say hi'
    """
    directive_re = re.compile(r"{{ (\w+) }}", flags=re.M)
    # loop through directive text, replacing each string enclosed with
    # template characters with the necessary values.
    if check_members is None and case is not None:
        check_members = case
    while directive_re.search(text):
        m = directive_re.search(text)
        variable = m.groups()[0]
        whole_match = m.group()
        if check_members is not None and hasattr(check_members, variable.lower()) and getattr(check_members, variable.lower()) is not None:
            repl = getattr(check_members, variable.lower())
            logger.debug("from check_members: in {}, replacing {} with {}".format(text, whole_match, str(repl)))
            text = text.replace(whole_match, str(repl))
        elif case is not None and case.get_value(variable.upper(), subgroup=subgroup) is not None:
            repl = case.get_value(variable.upper(), subgroup=subgroup)
            logger.debug("from case: in {}, replacing {} with {}".format(text, whole_match, str(repl)))
            text = text.replace(whole_match, str(repl))
        elif default is not None:
            logger.debug("from default: in {}, replacing {} with {}".format(text, whole_match, str(default)))
            text = text.replace(whole_match, default)
        else:
            # If no queue exists, then the directive '-q' by itself will cause an error
            if "-q {{ queue }}" in text:
                text = ""
            else:
                logger.warn("Could not replace variable '{}'".format(variable))
                text = text.replace(whole_match, "")

    return text

def get_my_queued_jobs():
    # TODO
    return []

def delete_jobs(_):
    # TODO
    return True

def wait_for_unlocked(filepath):
    locked = True
    file_object = None
    while locked:
        try:
            buffer_size = 8
            # Opening file in append mode and read the first 8 characters.
            file_object = open(filepath, 'a', buffer_size)
            if file_object:
                locked = False
        except IOError:
            locked = True
            time.sleep(1)
        finally:
            if file_object:
                file_object.close()

def gunzip_existing_file(filepath):
    with gzip.open(filepath, "rb") as fd:
        return fd.read()

def gzip_existing_file(filepath):
    """
    Gzips an existing file, removes the unzipped version, returns path to zip file.
    Note the that the timestamp of the original file will be maintained in
    the zipped file.

    >>> import tempfile
    >>> fd, filename = tempfile.mkstemp(text=True)
    >>> _ = os.write(fd, "Hello World")
    >>> os.close(fd)
    >>> gzfile = gzip_existing_file(filename)
    >>> gunzip_existing_file(gzfile)
    'Hello World'
    >>> os.remove(gzfile)
    """
    expect(os.path.exists(filepath), "{} does not exists".format(filepath))

    st = os.stat(filepath)
    orig_atime, orig_mtime = st[statlib.ST_ATIME], st[statlib.ST_MTIME]

    gzpath = '{}.gz'.format(filepath)
    with open(filepath, "rb") as f_in:
        with gzip.open(gzpath, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)

    os.remove(filepath)

    os.utime(gzpath, (orig_atime, orig_mtime))

    return gzpath

def touch(fname):
    if os.path.exists(fname):
        os.utime(fname, None)
    else:
        open(fname, 'a').close()

def find_system_test(testname, case):
    """
    Find and import the test matching testname
    Look through the paths set in config_files.xml variable SYSTEM_TESTS_DIR
    for components used in this case to find a test matching testname.  Add the
    path to that directory to sys.path if its not there and return the test object
    Fail if the test is not found in any of the paths.
    """
    from importlib import import_module
    system_test_path = None
    if testname.startswith("TEST"):
        system_test_path =  "CIME.SystemTests.system_tests_common.{}".format(testname)
    else:
        components = ["any"]
        components.extend( case.get_compset_components())
        env_test = case.get_env("test")
        fdir = []
        for component in components:
            tdir = env_test.get_value("SYSTEM_TESTS_DIR",
                                      attribute={"component":component})

            if tdir is not None:
                tdir = os.path.abspath(tdir)
                system_test_file = os.path.join(tdir  ,"{}.py".format(testname.lower()))
                if os.path.isfile(system_test_file):
                    fdir.append(tdir)
                    logger.debug( "found "+system_test_file)
                    if component == "any":
                        system_test_path = "CIME.SystemTests.{}.{}".format(testname.lower(), testname)
                    else:
                        system_test_dir = os.path.dirname(system_test_file)
                        if system_test_dir not in sys.path:
                            sys.path.append(system_test_dir)
                        system_test_path = "{}.{}".format(testname.lower(), testname)
        expect(len(fdir) == 1, "Test {} found in multiple locations {}, aborting".format(testname, fdir))
    expect(system_test_path is not None, "No test {} found".format(testname))

    path, m = system_test_path.rsplit('.',1)
    mod = import_module(path)
    return getattr(mod, m)

def _get_most_recent_lid_impl(files):
    """
    >>> files = ['/foo/bar/acme.log.20160905_111212', '/foo/bar/acme.log.20160906_111212.gz']
    >>> _get_most_recent_lid_impl(files)
    ['20160905_111212', '20160906_111212']
    """
    results = []
    for item in files:
        basename = os.path.basename(item)
        components = basename.split(".")
        if len(components) > 2:
            results.append(components[2])
        else:
            logger.warning("Apparent model log file '{}' did not conform to expected name format".format(item))

    return sorted(results)

def sorted_ls(path):
    ''' return list of path sorted by timestamp '''
    mtime = lambda f: os.stat(os.path.join(path, f)).st_mtime
    return list(sorted(os.listdir(path), key=mtime))

def get_lids(case):
    model = case.get_value("MODEL")
    logdir = case.get_value("LOGDIR")
    return _get_most_recent_lid_impl(glob.glob("{}/{}.log*".format(logdir, model)))

def new_lid():
    lid = time.strftime("%y%m%d-%H%M%S")
    os.environ["LID"] = lid
    return lid

def analyze_build_log(comp, log, compiler):
    """
    Capture and report warning count,
    capture and report errors and undefined references.
    """
    warncnt = 0
    if "intel" in compiler:
        warn_re = re.compile(r" warning #")
        error_re = re.compile(r" error #")
        undefined_re = re.compile(r" undefined reference to ")
    elif "gnu" in compiler or "nag" in compiler:
        warn_re = re.compile(r"^Warning: ")
        error_re = re.compile(r"^Error: ")
        undefined_re = re.compile(r" undefined reference to ")
    else:
        # don't know enough about this compiler
        return

    with open(log,"r") as fd:
        for line in fd:
            if re.search(warn_re, line):
                warncnt += 1
            if re.search(error_re, line):
                logger.warn(line)
            if re.search(undefined_re, line):
                logger.warn(line)

    if warncnt > 0:
        logger.info("Component {} build complete with {} warnings".format(comp, warncnt))

def is_python_executable(filepath):
    with open(filepath, "r") as f:
        first_line = f.readline()

    return first_line.startswith("#!") and "python" in first_line

def get_umask():
    current_umask = os.umask(0)
    os.umask(current_umask)

    return current_umask

def copy_umask(src, dst):
    """
    Preserves all file metadata except making sure new file obeys umask
    """
    curr_umask = get_umask()
    shutil.copy2(src, dst)
    octal_base = 0o777 if os.access(src, os.X_OK) else 0o666
    dst = os.path.join(dst, os.path.basename(src)) if os.path.isdir(dst) else dst
    os.chmod(dst, octal_base - curr_umask)

def stringify_bool(val):
    val = False if val is None else val
    expect(type(val) is bool, "Wrong type for val '{}'".format(repr(val)))
    return "TRUE" if val else "FALSE"

def run_and_log_case_status(func, phase, caseroot='.'):
    append_case_status(phase, "starting", caseroot=caseroot)
    rv = None
    try:
        rv = func()
    except:
        e = sys.exc_info()[1]
        append_case_status(phase, "error", msg=("\n{}".format(e)), caseroot=caseroot)
        raise
    else:
        append_case_status(phase, "success", caseroot=caseroot)

    return rv

def _check_for_invalid_args(args):
    for arg in args:
        # if arg contains a space then it was originally quoted and we can ignore it here.
        if " " in arg or arg.startswith("--"):
            continue
        if arg.startswith("-") and len(arg) > 2:
            sys.stderr.write( "WARNING: The {} argument is depricated. Multi-character arguments should begin with \"--\" and single character with \"-\"\n  Use --help for a complete list of available options\n".format(arg))

class SharedArea(object):
    """
    Enable 0002 umask within this manager
    """

    def __init__(self, new_perms=0o002):
        self._orig_umask = None
        self._new_perms  = new_perms

    def __enter__(self):
        self._orig_umask = os.umask(self._new_perms)

    def __exit__(self, *_):
        os.umask(self._orig_umask)

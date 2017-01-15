# Cluster-func

Cluster-func is a command line tool that lets you scale embarassingly parallel 
solution written in Python with zero additional code.

## Install

With pip
```bash
pip install cluster-func
```

From source
```bash
git clone git://github.com/enewel101/cluster-func
cd cluster-func
python setup.py develop
```

## Why?

Too often I find myself writing multiprocessing and job-division / scheduling
boilerplate code, which, despite being conceptually straightforward, is tedious
and error-prone.  Let's never do it again.

## Basic usage
Cluster-func is designed for situations where you need to run a single function
on many different arguments.  This kind embarassingly parallelizable problem
comes up pretty often.  At it's minimum, a solution involves defining
A) the function to be repeatedly called, and B) all of the different arguments
on which it should be called.  

Cluster-func assumes that you have defined
these in the form of a *callable* and an *iterable* within a python script, and
then it handles the business of spreading the work across cores and machines.

The tool has two modes.  In **direct mode**, it runs your function on the cpus of
a single machine.  In **dispatch mode**, it breaks the work into subjobs that can
be run on separate machines, and optionally submits them to a job scheduler
using `qsub`.

### Direct mode
This command:
```bash
$ cluf my_script.py 
``` 
will look in `my_script.py` for a function called `target` and an iterable called
`args`, and it will run `target` on every single value yielded from `args`,
spawning as many workers as there are cpu cores available to your user on the
machine.  

To use other names for you target function or arguments iterable,
or to use a different number of worker processes, do this:
```bash
$ cluf my_script.py --target=my_func --args=my_iterable --processes=12	# short options -t, -a, -p
```

If `args` yields a tuple, its contents will be unpacked and used as positional
arguments.  Single-argument invocations need not be packed into a 1-tuple 
(unless that argument is itself a tuple).  Separate invocations can use different
numbers of arguments.

`args` can also be a callable that *returns* an iterable (including a generator),
which is often more convenient.

So, using `cluf` in direct mode lets you multiprocess any script without pools
or queues or even importing multiprocessing.  But, if you really need to scale
up, then you'll want to use the dispatch mode.

### Dispatch mode
The main use of dispatch mode is to spread the work in a cluster that
uses the `qsub` command for job submission.  But you can still use `cluf` to 
spread work between machines don't use `qsub`.

Dispatch mode is implicitly invoked when you specify a number of compute nodes
to use.  This command:
```bash
$ cluf my_script.py --nodes=10 --queue	# short options -n, -q
```
will break the work into 10 subjobs, and submit them using qsub.  It does
this by writing small shell scripts, each of which is responsible for calling 
the target function on a subset of the arguments yielded by the iterable.

(Each shell script has Portable Batch System (PBS) directives that cause the
stdout and stdin to be captured into files by the same name (but with
extentions .stdout and .stdin) in the current working directory.  PBS
directives appear as comments, so the scripts are perfectly valid shell scripts
that can be executed normally.  You can set any PBS directives you want, see
**Cluf options**, and **Reference** for details.)

Because each subjob script is a valid shell script, you can manually run them
on separate machines in case they aren't part of a cluster that uses `qsub`.
Just leave off the `--queue` option, and the scripts will be created but not
enqueued.  This is also a good way to test run one of the subjobs
before submitting it.

To divide the work properly, it's important that your argument iterable yields
the same arguments in the same order on each machine.  If you can't or don't
want write your iterable that way, see **How work is divided** for other options.

## How work is divided 
By default, work is divided by assuming that the arguments iterator will yield
the same arguments in the same order during each subjob.  Each subjob can then
execute the target function only on those arguments assigned to it.  

For example, if there were 10 subjobs, subjob 7 would run arguments 7, 17, 27,
... etc.  For ease of explanation, we'll call that subset "bin 7".

If you open the subjob scripts in an editor, you'll find that they actually
call `cluf` itself in *direct mode*.  In other words, when you run
`cluf` in dispatch mode, it creates scripts that call `cluf` in direct mode.

These direct-mode invocations use the `--bin` option, which
is what instructs `cluf` to only run arguments that fall into that subjob's 
bin.  For example, this command:
```bash
$ cluf my_script --bin=0/3		# short option: -b
```
would run `cluf` in direct mode, but only execute iterations falling into bin 0 
out of 3, i.e., iterations 0, 3, 6, 9, etc.  (Bins are zero-indexed.)

You can use this to start subjobs manually if you like.
You can assign multiple bins to one subjob, For example, the option
`--bins=0-2,5/10` will assign bins 0, 1, 2, and 5 (out of a total of 10 bins).

### If your iterable is not stable
The default approach to binning assumes that the arguments iterable will 
yield the same arguments in the same order during execution of each subjob.
If you can't ensure that, then binning can be based on the arguments themselves,
instead of their order.

There are two alernative ways to handle binning: using *argument hashing* and
*direct assignment*.

### Argument hashing
By specifying the `--hash` option, you can instruct `cluf` to hash one or more
of the arguments to determine its bin.

For example, doing:
```bash
$ cluf example --nodes=12 --hash=0		# short options: -n and -x
```
will instruct `cluf` to hash the first argument of each iteration to decide
which bin the iteration belongs to.  

Before hashing, `cluf` calls `str` on the argument (so for this purpose, lists
are hashable).  It's important that the argument selected for hashing has a
stable string representation that reflects its value. Using objects that don't
implement `__str__` won't work, both because their string representation
doesn't reflect their value, and because their memory address appears within
it, which will be different in each subjob.  However, for this purpose, a list
would be considered "hashable" (provided it's individual elements are).  On the
other hand, dict's and sets are not suitable, because they are unordered, so
their string representation is not stable.  One approach is to simply provide
one argument that is a unique ID, and select it for hashing.

Ideally the argument selected for hashing should be unique throughout
iteration, since repeated values would be assigned to the same subjob, but
occaisional repetitions won't imbalance load much.  To help achieve uniqueness
you can provide combinations of arguments to be hashed.

For example, this:
```bash
$ cluf example --nodes=12 --hash=0-2,5		# short options: -n and -x
```
will hash arguents 0,1,2, and 5.  If any hashed arguments are missing in an 
iteration, they are considered equal to `None`.

### Direct assignment
A final method is to include an argument that explicitly specifies the
bin for each iteration.  To activate direct assignment, and to specify which
argument should be interpreted as the bin, use `--key` option:

```bash
$ cluf example --nodes=12 --key=2 		# short options: -n and -k
```
In the command above, argument 2 (the third argument) will be interpreted as
the bin for each iteration.

You should only use direct assignment if you really have to, because it's more
error prone, and it makes it more difficult to change the number bins.  It also
introduces job division logic into your script which `cluf` was designed to
prevent.

## `cluf_options` and `.clufrc`
You can include a dictionary named `cluf_options` in your target script to
control the behavior of `cluf`.  This can be more convenient than the command
line if you have to set a lot of options, and helps to document the options
you used.  You can also set options globally in a file at `~/.clufrc`. 

`cluf_options` should be a dictionary whose keys are the long option names,
and whose values are strings representing the option values as you would enter
them on the command line.  `.clufrc` should be a valid JSON object, with the
same key-value format.  See the following examples:

**Using `cluf_options`**
(in `my_script.py`)
```python
cluf_options = {
	'hash': (0,1,2,5),	# Collection options set using iterable
	'nodes': 12,
	'queue': True		# Flag options set using using boolean
}
```

**Using `.clufrc`**
(in `~/.clufrc`)
```json
{
	"hash": [0,1,2,5],
	"nodes": 12,
	"queue": true
}
```

For the most part, any option that can be set on the command line can be set in
`cluf_options` and `.clufrc`, and vice versa, but there are a few options that
can *only* be set in `cluf_options` and `.clufrc`.  We cover those now.  See
**Reference** for all available options.

### Environment variables
Let's suppose execution of your target script requires certain environment
variables to be set.  If you run `cluf` in *direct mode*, there's nothing to
think about -- your script will execute in an environment inhereted from the
one you are in.  

For example, if you did:
```bash
MYENV=1 cluf my_script.py
```
The value of `MYENV` would be seen by your script.

However, if you run `cluf` in dispatch mode, then the job scripts will not
be run in a different environment.  Use the `env` option to specify any 
environment variables that should be set when running the subjobs.  `env` should
be a dictionary within `cluf_options` or `.clufrc` that has variable names
as keys and values as, well, values:

(in `my_script.py`)
```python
cluf_options = {
	'env': {'MYENV': 1}
}
```

(in `~/.clufrc`)
```json
{
	"env": {"MYENV": 1}
}
```

Setting the env option using either method shown will cause the given environment
variables to be set within each of the subjob scripts.

### PBS options
Portable Batch System options control how the cluster scheduler schedules your
job, and allows you to request specific compute resources and specify the
amount of time that your job should run.  For example, to request that your
jobs run on compute nodes with at least 4 cpu cores and 2 gpus, you can do
something like this:

In general pbs options should be set using a dictionary of key-value pairs
using the option name as the key:

(in `my_script.py`)
```python
cluf_options = {
	'pbs_options': {'cpus': 4, 'gpus': 2}
}
```

(in `~/.clufrc`)
```json
{
	"pbs_options": {"cpus": 4, "gpus": 2}
}
```

However there are three special option whose names differ from the 
PBS option names slightly.  These options are also set by default.

	- `'name'`: the name of your subjobs as they appear in the job scheduler.
		this is also used to name your subjob scripts.  The default is the 
		format string `'{target_module}-{node_num}-{nodes}'`.  If you override
		this you can also use those format fields, and you must at least use
		the `{node_num}` field to ensure that each of your subjobs gets a 
		unique name (otherwise the subjob scripts will overwrite one another.
	- `'stdout'`: the path at which to place stdout captured from your subjobs,
		relative to the `jobs_dir` if set (if not set it defaults to the current
		working directory).
		The default is `'{target_module}-{node_num}-{nodes}.stdout'`
		As for name, if you override this, make sure that the paths for subjobs
		are unique by using the `{node_num}` field somewhere.
	- `'stderr'`: similar to stdout.  Defaults to 
		`'{target_module}-{node_num}-{nodes}.stderr'`

The combinations of PBS options that are available and/or required depends on 
the setup of your cluster.

There are three PBS options that are set by default, unless you specifically
override them.  These determine the name of your subjobs within the scheduler and
where stdout and stderr, captured for each subjob, should be written to disk.

	1. The name of your subjobs defaults to the following format
	`'{target_module}-{node_num}-{nodes}'`, with the fields being filled in for
	each subjob.  You can choose a different naming scheme and make use of those
	fields within it.  Be sure that your naming scheme yields different names for
	different subjobs (i.e. you should at least make use of `{node_num}`
	somewhere).  The naming of subjob scripts that are output are based on this
	name, with `'.pbs'` appended afterward, so if the subjob names aren't unique,
	then the subjob scripts will overwrite one another.

	2. T


### Additional statements
You can also specify any additional statements that you want to appear in your
job script.  This gives you more flexibility than simply setting environment 
variables.   You can include statements before the subjob is run using
 `prepend_statements` or after, using `append_statements`.  The value of 
the either should be a list of statements, which will be joined with endline
characters before placing it in the subjob script.  You can also use the 
options `prepend_script` and `append_script`, passing it a file path, to include
the contents of full scripts into your subjob scripts.  (while the `prepend_statements` and `append_statements` options are only available using `cluf_options`
and `.clufrc`, you can specify `prepend_script` and `append_script` on the
commandline.  Multiple, comma-separated scripts may be given.


# Reference

The `cluf` command has lots of options, which can be specified in three
different places:

 1. as command line arguments, or
 2. within your target module, inside a dictionary called cluf_options, or
 3. in the `~/.clufrc` file, in the form of a JSON object

These locations are in decreasing order of precedence, i.e. the command line
overrides all other options, and the `.clufrc` file doesn't override the others.

Options given in the `cluf_options` dictionary in the target module or in the
`.clufrc` JSON object should be identified by the long option name, without
the leading '--'.


### All `cluf` options

<pre>
usage: cluf [-h] [-j JOBS_DIR] [-t TARGET] [-a ARGS] [-q] [-p PROCESSES]
            [-b BINS] [-e ENV] [-P PREPEND_SCRIPT] [-A APPEND_SCRIPT]
            [-m {dispatch,direct}] [-x HASH | -k KEY]
            [-n NODES | -i ITERATIONS]
            target_module

Run a function many times on multiple processors and machines.

positional arguments:
  target_module         path to the python module that contains the target
                        function to be run many times.

optional arguments:
  -h, --help            show this help message and exit
  -j JOBS_DIR, --jobs-dir JOBS_DIR
                        Specify a directory in which to store job scripts and
                        the files generated from the stdout and stdin during
                        job execution. This directory will be made if it
                        doesn't exist. This option only takes effect in
                        dispatch mode.
  -t TARGET, --target TARGET
                        Alternate name for the target callable to be invoked
                        repeatedly. Default is "target".
  -a ARGS, --args ARGS  Alternate name for the arguments iterable. Default is
                        "args".
  -q, --queue           Enqueue the generated scripts using qsub. This option
                        only takes effect in dispatch mode.
  -p PROCESSES, --processes PROCESSES
                        Number of processors to use.
  -b BINS, --bins BINS  Optionally specify a portion of the work to be done.
                        Should take the form "x/y" meaning "do the x-th
                        section out of y total sections. For example, "0/2"
                        means divide the work into two halves, and do the
                        first (0th) half. Note that x and y should be
                        integers, and x should be from 0 to y-1 inclusive.
                        This option only takes effect in direct mode.
  -e ENV, --env ENV     Provide environment variables that should be set when
                        running sub-jobs. This is for use in dispatch mode,
                        since job scripts will run in a different environment.
                        In direct mode, the environment is inherited. The
                        value of this option should be an enquoted string of
                        space-separated key=value pairs. For example: $ cluf
                        my_script -n 12 -e 'FOO=bar BAZ="fizz bang"'will set
                        FOO equal to "bar" and BAZ equal to "fizz bang". This
                        option only takes effect in dispatch mode.
  -P PREPEND_SCRIPT, --prepend-script PREPEND_SCRIPT
                        Path to a script whose contents should be included at
                        the beginning of subjob scripts, being executed before
                        running the subjob. You can include multiple comma-
                        separated paths. This option only takes effect in
                        dispatch mode.
  -A APPEND_SCRIPT, --append-script APPEND_SCRIPT
                        Path to a script whose contents should be included at
                        the end of subjob scripts, being executed after the
                        subjob completes. You can include multiple comma-
                        separated paths. This option only takes effect in
                        dispatch mode.
  -m {dispatch,direct}, --mode {dispatch,direct}
                        Explicitly set the mode of operation. Can be set to
                        "direct" or "dispatch". In direct mode the job is run,
                        whereas in dispatch mode a script for the job(s) is
                        created and optionally enqueued. Setting either -n or
                        -i implicitly sets the mode of operation to
                        "dispatch", unless specified otherwise.
  -x HASH, --hash HASH  Specify an argument or set of arguments to be used to
                        determine which bin an iteration belons in. These
                        arguments should have a stable string representation
                        (i.e. no unordered containers or memory addresses) and
                        should be unique over the argumetns iterable. This
                        should only be set if automatic binning won't work,
                        i.e. if your argument iterable is not stable.
  -k KEY, --key KEY     Integer specifying the positional argument to use as
                        the bin for each iteration. That key argument should
                        always take on a value that is an integer between 0
                        and num_bins-1. This should only be used if you really
                        need to control binning. Prefer to rely on automatic
                        binning (if your iterable is stable), or use the
                        -xoption, which is more flexible and less error-prone.
  -n NODES, --nodes NODES
                        Number of compute nodes. This option causes the
                        command to operate in dispatch mode, unless the mode
                        is explicitly set
  -i ITERATIONS, --iterations ITERATIONS
                        Approximate number of iterations per compute node.
                        This option causes the command to operate in dispatch
                        mode, unless the mode is explicitly set. Note that
                        using this instead of --nodes (-n) can lead to delay
                        because the total number of iterations has to be
                        counted to determine the number of compute nodes
                        needed.
</pre>



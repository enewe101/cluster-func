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
and error-prone.

Sure, `xargs` is nice, assuming that you can conveniently get the shell to
spit out your argument values.  But that's often not the case, and 
you may want your arguments to be arbitrary python types instead of strings.

And, sure, Hadoop is nice too, assuming you've got a lot of time to burn
configuring it, and that your mappers and reducers don't use too much 
memory, and that you've loaded all your data in the hdfs, 
and that the results from your maps don't 
yield too much data and overwhelm the network.  Oh, and assuming
you enjoy writing boilerplate mapper and reducer code... wait, maybe hadoop
isn't so nice... (OK, OK, it does have its place!)

## Basic usage
Cluster-func is designed for situations where you need to run a single function
on many different arguments.  This kind embarassingly parallelizable problem
comes up pretty often.  At it's minimum, a solution involves defining
**A)** the function to be repeatedly called, and **B)** all of the different 
arguments on which it should be called.  

Cluster-func assumes that you have defined
these in the form of a *callable* and an *iterable* within a python script, and
then it handles the business of spreading the work across cores and machines.

The nice thing about this approach is that you unavoidably define these two
things when you write your code for a single process anyway.  So you'll get
multiprocessing and cluster processing basically for free!

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

If `args` yields a tuple, its contents will be unpacked and interpreted as the
positional arguments for one invocation of the target function.  If you need
greater control, for example, to provide keyword arguments, then see 
**<a href="#arguments-iterable">Arguments iterable</a>**

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
to use (you can force the running mode using `--mode`, see **<a
href="#reference">Reference</a>**).
For example, this command:
```bash
$ cluf my_script.py --nodes=10 --queue	# short options -n, -q
```
will break the work into 10 subjobs, and submit them using qsub.  It does
this by writing small shell scripts, each of which is responsible for calling 
the target function on a subset of the arguments yielded by the iterable.

(To learn about setting PBS directives for your subjob scripts, see **<a
href="#pbs-options">PBS
options</a>** below.)

Because each subjob script is a valid shell script, you can manually run them
on separate machines in case they aren't part of a cluster that uses `qsub`.
Just leave off the `--queue` option, and the scripts will be created but not
enqueued.  This is also a good way to test run one of the subjobs
before submitting it.

To divide the work properly, it's important that your argument iterable yields
the same arguments in the same order on each machine.  If you can't or don't
want write your iterable that way, see **<a href="#how-work-is-divided">How work is divided</a>** for other options.

And that's the end of the basic usage guide.  This will cover you for the most 
basic usecases.  To learn about more cool features, read on!

## <a name="arguments-iterable">Arguments iterable</a>
The main usecase imagined is one where the arguments iterable yields either
single, bare arguments, or tuples of positional arguments.  Of course, the 
Python language provides a very
flexible way of calling functions, allowing you to mix positional arguments
and keyword arguments.  If you need that flexibility, then set up your iterator
to yield `cluster_func.Arguments` objects.  This class acts as a proxy, and 
will be used to call your target function in exactly the way you called the 
`Arguments` constructor.

Here is the `Arguments` class in action:
```python
>>> from cluster_func import Arguments
>>> my_args = Arguments(0, *[1,2,3], four=4, **{'five':5, 'six':6})
>>> my_args
Arguments(0, 1, 2, 3, four=4, five=5, six=6)
>>>
>>> # Your target function would be called the same way you called Arguments, e.g.:
>>> my_target(0, *[1,2,3], four=4, **{'five':5, 'six':6})
```

## <a name="how-work-is-divided">How work is divided</a>
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

Before hashing, `cluf` calls `str` on the argument.
It's important that the argument selected for hashing has a
stable string representation that reflects its value. Using objects that don't
implement `__str__` won't work, both because their string representation
doesn't reflect their value, and because their memory address appears within
it, which will be different in each subjob.  However, for this purpose, a list
would be considered "hashable" (provided it's individual elements are).  On the
other hand, dict's and sets are not suitable, because they are unordered, so
their string representation is not stable.  One safe approach is to simply 
provide one argument that is a unique ID, and select it for hashing.

Ideally the argument selected for hashing should be unique throughout
iteration, since repeated values would be assigned to the same subjob.  But
occaisional repetitions won't imbalance load much.  To help achieve uniqueness
you can provide combinations of arguments to be hashed.  If you provided 
arguments as keyword arguments (using an Arguments object) you can select them 
too.

For example, this:
```bash
$ cluf example --nodes=12 --hash=0-2,5,my_kwarg	# short options: -n and -x
```
will hash arguents in positions 0,1,2, and 5, along with the keyword argument 
`my_kwarg`.  If any hashed arguments are missing in an 
iteration (becase, recall, invocations may use different numbers of arguments), 
they are simply ommitted when calculating the hash.

### Direct assignment
The final method for dividing work is to include an argument that explicitly 
specifies the
bin for each iteration.  To activate direct assignment, and to specify which
argument should be interpreted as the bin, use `--key` option:

```bash
$ cluf example --nodes=12 --key=2 		# short options: -n and -k
```
In the command above, the argument in position 2 (the third argument)
 will be interpreted as
the bin for each iteration.  You can also specify a keyword argument by name.

You should only use direct assignment if you really have to, because it's more
error prone, and it makes it more difficult to change the number of bins.
It also
introduces job division logic into your script which `cluf` was designed to
prevent.

## `cluf_options` and `.clufrc`
For more extensive configuration, you can include a dictionary named 
`cluf_options` in your target script to
control the behavior of `cluf`.  This can be more convenient than the command
line if you have to set a lot of options, and helps to document the options
you used.  You can also set options globally in a file at `~/.clufrc`. 

All options that can be set on the command line can be set within `cluf_options`
or `.clufrc`, plus a few extras.  There is one exception, however, which is
the option to force direct / dispatch mode (`--mode` or `-m`), which can only 
be set on the command line.

`cluf_options` should be a dictionary whose keys are the long option names,
and whose values are strings representing the option values as you would enter
them on the command line.  `.clufrc` should be a valid JSON object, with the
same key-value format.  See the following examples:

**Using `cluf_options`**
(in `my_script.py`)
```python
cluf_options = {
	'hash': (0,1,2,5),	# Or use '0-2,5'.  Applies to .clufrc as well
	'nodes': 12,
	'queue': True		# Flag options based on truthiness of value
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

In some cases you may want to use `cluf_options` to simply modify (e.g. add to) 
the options in `.clufrc`, rather than overriding them.  You can access the 
`.clufrc` options by importing them, using `from clusterf_func import RC_PARAMS`.

For the most part, any option that can be set on the command line can be set in
`cluf_options` and `.clufrc`, and vice versa, but there are a few options that
can *only* be set in `cluf_options` and `.clufrc`.  We cover those now along
with some options that are just less convenient to set on the command line.  
See **<a href="#reference">Reference</a>** for all available options.

### Environment variables
(Note: This option can be set on the command line but is somewhat less 
convenient.)
Let's suppose execution of your target script requires certain environment
variables to be set.  If you run `cluf` in *direct mode*, there's nothing to
think about—your script will inheret the current environment.

For example, if you did:
```bash
MYENV=1 cluf my_script.py
```
The value of `MYENV` would be seen by your script.

However, if you run `cluf` in dispatch mode, then the job scripts will
run in a different environment.  Use the `env` option to specify any 
environment variables that should be set when running the subjobs.  `env` should
be a dictionary within `cluf_options` or `.clufrc` that has variable names
as keys and values as, well, values:

(in `my_script.py`)
```python
cluf_options = {
	'env': {
		'MYENV': 'foo',
		'OTHER_ENV': 'bar',
	}
}
```

(in `~/.clufrc`)
```json
{
	"env": {
		"MYENV": "foo",
		"OTHER_ENV": "bar"
	}
}
```

If provided on the commandline, the contents of `env` will be pasted as-is
in front of the line that runs the subjob within the subjob script.  So the
equivalent `env` specification would be:
```bash
cluf my_script.py --nodes=4 --env='MYENV=foo OTHER_ENV=bar'
```

Each of these methods will cause the invocation of subjobs within subjob
scripts to look like this:
```bash
MYENV=foo OTHER_ENV=bar cluf my_script [...options]
```

Note that, regardless of where it is specified, if you want to provide a 
value for an environment variable that contains a space or other character
needing escaping, keep in mind that a round of interpretation by the 
command line, Python, or JSON will have occurred (depending on where it was set)

So, e.g., this won't work:
```bash
cluf my_script.py --nodes=4 --env='MYENV=foo bar'
```
Nor will, this:
```bash
cluf my_script.py --nodes=4 --env=MYENV=foo\ bar
```
But This will work:
```bash
cluf my_script.py --nodes=4 --env='MYENV=foo\ bar'
```
And so will this:
```bash
cluf my_script.py --nodes=4 --env=MYENV=foo\\\ bar
```

### <a name="pbs-options">PBS options</a>
(This option cannot be set on the command line.)
Portable Batch System options control how the cluster scheduler schedules your
job, and allows you to request specific compute resources and specify the
amount of time that your job should run.
In general PBS options should be set using a dictionary of key-value pairs
using the option name as the key.  For example, to request that your
subjobs run on compute nodes with at least 4 cpu cores and 2 gpus, you can do
something like this:

(in `my_script.py`)
```python
cluf_options = {
	'pbs_options': {'ppn': 4, 'gpus': 2}
}
```

(in `~/.clufrc`)
```json
{
	"pbs_options": {"ppn": 4, "gpus": 2}
}
```

The `ppn` (processes per node) option should usually match the number of worker
processes set by the  `processes` option (whether set on the command line, 
`cluf_options`, or in `.clufrc`).  So if `ppn` isn't explicitly set in your
PBS options, but `processes` is set, then it will default to the value of 
`processes`.  You can still set a different value for ppn, if e.g.  your target 
function itself spawns proceses.

There are three special options whose names differ from the 
PBS option names slightly, and these options are set to defaults unless 
specifically overridden.

- `'name'`: the name of your subjobs as they appear in the job scheduler.
	This is also used to name your subjob scripts (by appending `'.pbs'`).
	The default is the format string `'{target}-{subjob}-{num_subjobs}'`,
	with the fields being interpolated by the target module's name, the 
	subjob number, and the total number of subjobs respectively.
	If you override
	this you can also use those format fields, and you must at least use
	the `{subjob}` field to ensure that each of your subjobs gets a 
	unique name (otherwise the subjob scripts will overwrite one another).
- `'stdout'`: the path at which to place stdout captured from your subjobs,
	relative to the `jobs_dir` if set (if not set then it is relative to the 
	current working directory).
	This defaults to the subjob name plus `'.stdout'`
	As for the `'name'` option, 
	if you override this, make sure that the paths for subjobs
	are unique by using the `{node_num}` field somewhere.
- `'stderr'`: similar to `'stdout'`.  Defaults to the subjob name plus 
	`'.stderr'`

The combinations of PBS options that are available and/or required depends on 
the setup of your cluster.  Usually a system is configured with smart defaults
so that you can queue simple jobs without setting any PBS options.


### Additional statements
(This option can be set on the command line but may be more convenient to set
within your target script.)
You can also specify any additional statements that you want to appear in your
subjob scripts.  This gives you more flexibility than simply setting environment 
variables.   You can include an external script, whose statements get merged
into the job script before the line that runs subjob using
 `prepend_script`.  Include an external script *after* the line that runs
the subjob using the `append_script` option.  

If you just want to add a statement or two, it maybe more convenient to 
put them in your target script (or `.clufrc`).
The options `prepend_statements` and `append_statements` can be used provide a 
list of shell statements that get inserted right before or after the line
that actually runs the subjob within subjob scripts.  Each element of the list
should be a valid shell statement which will appear on its own line when merged
into the jobscripts.  The options aren't available on the command line.

# <a name="reference">Reference</a>

The `cluf` command has lots of options, which can be specified in three
different places:

 1. as command line arguments, or
 2. within your target module, inside a dictionary called `cluf_options`, or
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



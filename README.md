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

If `args` yields a tuple, its contents will be unpacked and used as positional
arguments.  Single-argument invocations need not be packed into a 1-tuple 
(unless that argument is itself a tuple).  Separate invocations can use different
numbers of arguments.

`args` can also be a callable that *returns* an iterable (including a generator),
which is often more convenient.

To use other names for you target function or arguments iterable,
or to use a different number of worker processes, do this:
```bash
$ cluf my_script.py --target=my_func --args=my_iterable --processes=12	# short options -t, -a, -p
```

This means you can multiprocess any script without pools or queues or even
importing multiprocessing.  But, if you really need to scale up, then you'll
want to use the dispatch mode.

### Dispatch mode
The main use of dispatch mode is to spread the work in a cluster that
uses the `qsub` command for job submission.  But you can still use `cluf` to 
spread work between machines don't use `qsub`.

Batch mode is implicitly invoked when you specify a number of compute nodes to 
use.  This command:
```bash
$ cluf my_script.py --nodes=10 --queue	# short options -n, -q
```
will break the work into 10 subjobs, and submit them using qsub.  It does
this by writing small shell scripts that each call the target function on a
subset of the arguments yielded by the iterable.

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

**Using `.clufrc`**
(in `~/.clufrc`)
```json
{
	"hash": [0,1,2,5], 	# Collection options set using Array
	"nodes": 12,
	"queue": True		# Flag options set using boolean
}
```
*Don't forget that JSON requires double quotes around strings.* 

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
	...
	'env': {'MYENV': 1}
}
```

(in `~/.clufrc`)
```json
{ ... "env": {"MYENV": 1}}
```

Setting the env option using either method shown will cause the given environment
variables to be set within each of the subjob scripts.

# Additional statements
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
 2. within your target module, inside a dictionary called clum_options, or
 3. in the `~/.clufrc` file, in the form of a JSON object

These locations are in decreasing order of precedence, i.e. the command line
overrides all other options, and the `.clufrc` file doesn't override the others.

Options given in the `clum_options` dictionary in the target module or in the
`.clufrc` JSON object should be identified by the long option name, without
the leading '--'.


### All `cluf` options

<pre>
usage: cluf [-h] [-j JOBS_DIR] [-t TARGET] [-a ARGS] [-q] [-p PROCESSES]
            [-b BINS] [-n NODES | -i ITERATIONS]
            target_module

Run a function many times on multiple processors and machines.

positional arguments:
  target_module         path to the python module that contains the target
                        function to be run many times.

optional arguments:
  -h, --help            show this help message and exit
  -j JOBS_DIR, --jobs-dir JOBS_DIR
                        Specify a directory in which to store jobscripts and
                        the files generated from the stdout and stdin during
                        job execution
  -t TARGET, --target TARGET
                        Alternate name for the target callable to be invoked
                        repeatedly. Default is "target".
  -a ARGS, --args ARGS  Alternate name for the arguments iterable. Default is
                        "args".
  -q, --no-q            Do not enqueue the generated scripts using qsub.
                        Default is to Enqueue them
  -p PROCESSES, --processes PROCESSES
                        Number of processors to use.
  -b BINS, --bins BINS  Optionally specify a partition of the work to be done.
                        Should take the form "x/y" meaning "do the x-th
                        section out of y total sections. For example, "0/2"
                        means divide the work into two halves, and do the
                        first (0th) half. Note that x and y should be
                        integers, and x should be from 0 to y-1 inclusive.
                        Running for all values of x will perform all the work,
                        and each run (each value of x) can be done on a
                        separate machine.
  -n NODES, --nodes NODES
                        Number of compute nodes.
  -i ITERATIONS, --iterations ITERATIONS
                        Approximate number of iterations per compute node.
                        Note that using this instead of --nodes (-n) can lead
                        to delay because the number total number of iterations
                        has to be counted before dispatching in order to
                        determine the number of compute nodes needed.

</pre>



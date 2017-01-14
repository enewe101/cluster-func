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
enqueued using `qsub`.  This is also a good way to test run one of the subjobs
before submitting it.

To divide the work properly, it's important that your argument iterable yields
the same arguments in the same order on each machine.  If you can't or don't
want write your iterable that way, see **How work is divided** for other options.

## How work is divided 
Work is divided by assuming that the arguments iterator will yield the same
arguments in the same order during each subjob.  Each subjob can then execute
the target function only on those arguments assigned to it.  

For example, if there were 10 subjobs, subjob 7 would run arguments 7, 17, 27,
... etc.  For ease of explanation, we'll call that subset "bin 7".

If you open the subjob scripts in an editor, you'll find that they actually
call `cluf` itself in *direct mode*.  In other words, when you run
`cluf` in dispatch mode, it creates scripts that call `cluf` in direct mode.

However, these direct-mode invocations of `cluf` use the `--bin` option, which
is what instructs `cluf` to only run arguments that fall into that subjob's 
bin.  For example, this command:
```bash
$ cluf my_script --bin=0/3		# short option: -b
```
Would run `cluf` in direct mode, but only execute iterations falling into bin 0 
out of 3, i.e., iterations 0, 3, 6, 9, etc.  (Bins are zero-indexed.)

This means that if you're machines aren't part of a cluster that uses qsub, 
you can use the `--bin` option to spread work over multiple machines
by logging into each machine and running `cluf` in direct mode using different
bins.  

If you like, you can assign multiple bins to one subjob, For example, the option
`--bins=0-2,5/10` will assign bins 0, 1, 2, and 5 (out of a total of 10 bins).

### If your iterable is not stable
The default approach to binning assumes that the arguments iterable will 
yield the same arguments in the same order during execution of each subjob.
If you can't ensure that, then binning can be based on the arguments themselves,
instead of their order.

There are two alernative ways to hadle bnning: using *argument hashing* and
*direct assignment*.

### Argument hashing
By specifying the `--hash` option, you can instruct `cluf` to hash one of the
arguments to determine its bin.

For example, doing

```bash
$ cluf example --nodes=12 --hash=0		# or use -n and -x
```
will instruct `cluf` to hash the first argument before calling the target 
function to decide which bin the iteration belongs to.  Before hashing,
`cluf` calls `str` on the argument (so for this purpose, lists are hashable).

To use this approach, it's important that the argument selected for hashing
has a stable string representation that reflects its value, so passing
objects that don't implement `__str__` won't work, both because their string
representation doesn't reflect their value, and because their memory address
appears within it, which will be different in each subjob.

Ideally the argument selected for hashing should be unique throughout iteration,
since repeated values will be assigned to the same subjob.  You can also specify
combinations of arguments to be hashed, which are more likely to be unique.
For example, this:
```bash
$ cluf example --nodes=12 --hash=0-2,5		# or use -n and -x
```
will hash arguents 0,1,2, and 5.  Because each iteration can use a different
number of arguments, if one of the hashed arguments is missing, it is considered
equal to `None`.

### Direct assignment
A final method is to include an argument that explicitly specifies the
bin for each iteration.  To activate direct assignment, and to specify which
argument should be interpreted as the bin, use `--key` option:

```bash
$ cluf example --nodes=12 --key=2 		# or use -n and -k
```
In the command above, argument 2 (the third argument) will be interpreted as
the bin for each iteration.

You should only use direct assignment if you really have to, because it's more
error prone, and it makes it more difficult to change the number bins.  It also
introduces job division logic into your script which `cluf` was designed to
prevent.

# Reference

The `cluf` command has lots of options, most of which can be specified in either
of two places:

 1. as command line arguments, or
 2. within your target module, inside a dictionary called clum_options

When an option is set in both places, the command line option overrides.
Using clum_options helps to document how your script was run, while using the
command line gives you ad hoc flexibility and fulfills the goal of zero-code 
multiprocessing / cluster processing.  The key for options set in clum_options
should be the long name of the corresponding command line option, without the
leading '--'.  Options that can be specified both on the command line and in the
target script will be covered first, followed by the options that can only be
specified in the target module.  All options can be specified in the target
module except where noted.

### Options that can be specified via command line 

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



Thee commands are also outside of the scope of this tool, but are provided here
as a handy bare minimum to start mucking about with running jobs on a cluster.

## Stdout and stderr

Once your jobs complete, anything that was sent to stdout or stderr
will be stored in `<script-name>-<job-num>-<num-jobs>.stdout` and
`<script-name>-<job-num>-<num-jobs>.stderr` in the current directory,
respectively.

## A few details you should know about ##

To distribute work between nodes, the script hashes the string 
representation of the first argument in each iteration into one of 
<num-nodes> bins.  This makes a stable
but pseudorandom assignment -- stable in the sense that iterations will
always be grouped onto the same nodes according to their first argument.

To ensure good load balancing, the first argument should be unique accross 
all iterations.  

If a different argument should be used for balancing (if, say, the 
second argument is always unique) you can specify that in the script 
options.

If many iterations have the same first argument, it's not a fatal problem, 
but they will
all be sent to the same machine.  It's not a fatal problem, but it might
imbalance the load.

Second, before hashing, the first argument will have `str()` called on it.
Anything with a reasonable and unique string representation will work fine.
The argument values themselves don't need to be hashable because of this.
It doesn't need to be hashable.  If calling `str()` just yields a memory
address, then this will probably achieve uniqueness, but you subsequent
runs over the same arguments wouldn't group work onto machines in the same
way (which generally isn't a problem and sometimes might be desireable).




`IterableQueue` is a directed queue, which means that it has 
(arbitrarily many) *producer endpoints* and *consumer endpoints*.  This
directedness enables `IterableQueue` to know how many producers and 
consumers are still at work, and this lets it take care of the tracking
and signalling necessary to tell the difference between being 
temporarily empty, and being empty with no new work coming.  Because the
`IterableQueue` knows when no new work is coming, it can be treated like
an iterable on the consumer end, stopping iteration naturally when all work 
is complete.

Producers use the queue much like a `multiprocessing.Queue`, but with one
small variation: when they are done putting work on the queue, they call
`queue.close()`:

```python
producer_func(queue):
	while some_condition:
		...
		queue.put(some_work)
		...
	queue.close()
```

The beautiful part is in how consumers use the queue, which is somewhat
differently than it is with `multiprocessing.Queue`: 
consumers can simply treat the queue as an iterable:

```python
consumer_func(queue):
	for work in queue:
		do_something_with(work)
```

Because the `IterableQueue` knows how many producers and consumers are open,
it knows when no more work will come through the queue, and so it can
stop iteration transparently.

(Although you can, if you choose, consume the queue "manually" by calling 
`queue.get()`, with `Queue.Empty` being raised whenever the queue is empty, and `iterable_queue.ConsumerQueueClosedException` being raised when the queue is empty with no more work coming.)

## Use `IterableQueue` ##
As mentioned, `IterableQueue` is a directed queue, meaning that it has 
producer and consumer endpoints.  Both wrap the same underlying 
`multiprocessing.Queue`, and expose *nearly* all of its methods.
Important exceptions are the `put()` and `get()` methods: you can only
`put()` onto producer endpoints, and you can only `get()` from consumer 
endpoints.  This distinction is needed for the management of consumer 
iteration to work automatically.

To see an example, let's setup a function that will be executed by 
*producers*, i.e. workers that *put onto* the queue:

```python
from random import random
from time import sleep

def producer_func(queue, producer_id):
	for i in range(10):
		sleep(random() / 100.0)
		queue.put(producer_id)
	queue.close()
```

Notice how the producer calls `queue.close()` when it's done putting
stuff onto the queue.

Now let's setup a consumer function:
```python
def consumer_func(queue, consumer_id):
	for item in queue:
		sleep(random() / 100.0)
		print 'consumer %d saw item %d' % (consumer_id, item)
```

Notice again how the consumer treats the queue as an iterable&mdash;there 
is no need to worry about detecting a termination condition.

Now, let's get some processes started.  First, we'll need an `IterableQueue`
Instance:

```python
from iterable_queue import IterableQueue
iq = IterableQueue
```

Now, we just start an arbitrary number of producer and consumer 
processes.  We give *producer endpoints* to the producers, which we get
by calling `IterableQueue.get_producer()`, and we give *consumer endpoints*
to consumers by calling `IterableQueue.get_consumer()`:

```python
from multiprocessing import Process

# Start a bunch of producers:
for producer_id in range(17):
	
	# Give each producer a "producer-queue"
	queue = iq.get_producer()
	Process(target=producer_func, args=(queue, producer_id)).start()

# Start a bunch of consumers
for consumer_id in range(13):

	# Give each consumer a "consumer-queue"
	queue = iq.get_consumer()
	Process(target=consumer_func, args=(queue, consumer_id)).start()
```

Finally&mdash;and this is important&mdash;once we've finished making 
producer and consumer endpoints, we close the `IterableQueue`:  

```python
iq.close()
```

This let's the `IterableQueue` know that no new producers will be coming 
onto the scene and adding more work.

And we're done.  Notice the pleasant lack of signalling and keeping track 
of process completion, and notice the lack of `try ... except Empty` 
blocks: you just iterate through the queue, and when its done its done.

You can try the above example by running [`example.py`](https://github.com/enewe101/iterable_queue/blob/master/iterable_queue/example.py).






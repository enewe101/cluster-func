# `cluster-func`

`cluster-func` is a command line tool that lets you scale embarassingly parallel 
algorithms written in Python with zero additional code.

It ships with two commands: 
	
```bash
$ clum my_script.py --target=my_func --args=my_args
``` 
runs a target function found from my_script.py using every set of arguments
in the iterable my_args, using as many processes as there are cpu cores 
available.  The `args` iterator should group arguments for a single 
invocation in a tuple.  Single-argument invocations need not be within a 
tuple if the argument is not itself a tuple.  Specify the number of 
processors using `--processes`.  If the target function and arguments 
iterable are called `target` and `args`, omit those options.  Environment 
variabes are inherited.  Pass through command line arguments to my_script.py 
by placing them after a '--'.

```bash
$ cluf myscript.py --target=my_func --args=my_args --nodes=12
```
runs a target function on the indicated number of machines (here 12), 
using as many processors as are available, by splitting up the work
into sub-jobs and submitting the sub-jobs via qsub.  Environment 
variables are *not* inherited, but can be specified using options (see 
"`cluf` options").  Pass through command line arguments as with `clum`.  
Optionally ommit the  `--target` and `--args` options as with `clum`.  
Specify resource requirements via PBS options (see "`cluf` options").

Note, properly dividing
the work into sub-jobs assumes that your iterator is stable (that it 
yields the same element in the same order during execution of each sub-job.
if that is not the case, see "How binning works" below). 

## Why?

Too often I find myself writing multiprocessing and job-division / scheduling
boilerplate code, which, despite being conceptually straightforward, is tedious
and error-prone.  Let's never do it again.

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

## Example

Suppose we want to process a million files, writing the output to disk.
(Sorry, for simplicity, I'm forgoing context managers to open files D: )

(process_files.py)
```python
def target(in_path, out_path):
	processed = do_stuff_with(in_path)
	open(out_path, 'w').write(processed)

args = [ 
	('input/dir/' + fname, 'output/dir/' + fname)
	for fname in os.listdir('input/dir')
]
```

To do all the work on one machine, using all available processes:
```bash
$ clum process_files.py
```

To do all the work on 12 machines on a cluster that uses qsub for job 
submission:
```bash
$ cluf process_files.py --nodes=12
```

## Let `cluf` decide how many nodes to use

Rather than specifying the number of nodes (sub-jobs) directly, you can specify 
the number of iterations to be executed on each node.  `cluf` will count the
total number of iterations, and figure out how many sub-jobs to make:

```bash
$ cluf example --iterations=200	# or use -i
```

(Performance note -- `cluf` will iterate through your iterator once completely
to figure out how many nodes are needed, which may cause some delay).

## Split work accross nodes without using `qsub`
If you have access to machines that aren't under a scheduler that uses qsub,
you can still manually dispatch sub jobs to each machine.  In this case,
you'll log into each machine, and use `clum` to run each sub-job.  `clum`
accepts a `--bin` argument, which instructs it to execute the target function
over a specific subset (or bin) of arguments yielded from the iterable:

```bash
$ clum example --bin=0/3		# or use -b
```

In the above example, the bin specification means "bin 0 of 3".  This instructs
clum to divide the iterations into 3 approximately equal bins, and to execute
iterations belonging to the zeroth bin.  Bins are zero indexed.  The normal
usage would be to log into two other machines and run sub-jobs using the bin
sepcifications `1/3` and `2/3`.  As long as your arguments iterator is stable
(yielding the same elements in the same order on each machine), the sub-jobs
are guaranteed to cover all iterations without duplication.  If your iterator
is not stable, see "How binning works".

If you want to send more work to certain machines, you can achieve that by
having machines complete more than one bin.  For example, to do two-thirds
of the work on one machine, use `--bin=0,1/3`, and do one third of the work
on the other machine using `--bin=2/3`.  You can combine comma separated 
ranges and integers for specifying the bins to be performed, so 
`--bin=0-2,7/8` is a valid way to do bins 0,1,2, and 7 (out of a total of 8 
bins).

If your machines have very different numbers of available cpus, you could, for
example, have as many bins as you have total cpus, and assign each machine as
many bins as it has cpus, to divide work evenly over cpus.  You probably
should'tget too fancy.  If you are getting fancy, cluster-func might not be the
right tool!


## How binning works
`cluf` and `clum` split up the work into sub-jobs or "bins", by dealing out 
arguments
from the arguments iterator like dealing playing cards -- the i-th argument goes
in bin i % num_bins. For that to work your iterator must be "stable": it should
yield the same elements in the same order during execution of each sub-job.

If you can't or don't want to write a stable iterator, you have two other
options.  First, `cluf` can hash one or more of the arguments to determine the 
bin as follows:

```bash
$ cluf example --nodes=12 --hash=0-2,7		# or use -n and -x
```

In the above command, `cluf` will hash the *string representation* of arguments
0,1,2, and 7 to determine the bin for a given interation.  Any string
or number that is nearly unique throughout iteration is suitable.
It's critical that the chosen argument(s) have a stable string representation, 
so, for example, they shouldn't include objects whose memory address appears
Uniqueness is a soft requirement -- repeated values will be routed to the same
bin, which isn't a huge deal if rare, but could cause load imbalance.

Usually it's best just to set up a stable iterator.  The hashing approach
above is a good alternative.  A final method is to explicitly specify the
bin for each iteration using one of the arguments:

```bash
$ cluf example --nodes=12 --key=2 		# or use -n and -k
```

Bins are zero-indexed, so the key argument must always be an interger from 0 to 
one less than the number of nodes, inclusive.  This isn't the recommended 
approach.  It starts to couple your code to `cluf` and commits you to a specific 
number of bins.  It's up to you to make sure that the key argument is always a 
valid bin, since if it's not, that iteration would be passed over silently.


# Reference

## `clum`

The `clum` command has lots of options, most of which can be specified in either
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

## Binning unstable iterables

The default strategy for binning assigns iterations to bins based on their
position in the arguments iterable -- like how playing cards are dealt.  This
only works if, on each machine, the iterable's order and contents are consistent.

There are a variety of reasons why that might not be a convenient set up your
iterator in a way that guarantees stability, and there are a few other options
for binning available to you.

### Explicitly set the bin using your iterator
One option is to have your iterator explicitly provide the bin assignment as
one of the arguments in each argument set.  Be sure that, if you are running
with `n` bins, this argument's value is always an integer from 0 to n-1, since
other values correspond to non-existent bins and would be silently skipped.

This can be accomplished in two ways:

	1. Use the `cluf` argument `--key` or `-k`, and provide the position of the
		argument to be used as the key:

			```bash
			$ cluf my_script -key=0
			```

	2. Include a dicionary called `cluf_options` in your target module, and
		provide the key within it:
		
			(in my_script.py)
			```python
			cluf_options = {'key':0}
			```

### Use a unique argument as the basis for binning Explicitly setting the bin
gives predictable behaviour, and allows you to control where given iterations
are executed which can be useful.  However, it forces you to address
work-splitting concerns in your iterator, which means not writing zero code,
and which commits you to a specific number of bins.

Usually your iterator yields unique argument sets, and hashing these can be
used as the basis for binning.  It's necessary that the arguments have a stable
string representation (so objects that show their memory address won't work).
Uniqueness is not strictly necessary -- repeated values will be routed to the
same bin, and if that happens rarely it won't imbalance workloads too much.

To designate certain argument(s) as the basis for binning, do one of the
following:

	1. Use the `cluf` argument `--hash` or `-h`, and provide the position(s) of 
		the arguments to be used for binning.  These can be single integers,
		ranges, and comma-separated combinations:

			```bash
			$ cluf my_script -hash=0-3,7
			```
		
		This would hash the string representation of use arguments 0,1,2,3 and 7
		to determine the bin.

	2. Include a dicionary called `cluf_options` in your target module, and
		provide a list of argument positions within it:
		
			(in my_script.py)
			```python
			cluf_options = {'key':[0,1,2,3,7]}
			```

Note that using argument hashes won't distribute work perfectly evenly, but 
it will still be fairly even, following the `balls in bins` distribution, 
meaning that, assuming each iteration takes the same amount of time, 
instead of taking O(n) time for the final iteration to complete, it will take
order of log n / log log n.  No big deal.  Put in the work to stabalize your
iterator if it matters to you!




Boom! Don't write multiprocessing / cluster-job-splitting code for embarassingly
parallel problems ever again!

## A few more details.

Before you flood the cluster with jobs, there's a few more helpful details
and some handy tricks to know about.

### Do a subset of the work

The `clum` command has a handy and intuitive way of running the target function
on a subset of the arguments.  This is accomplished using the `--bins` or `-b`
option, so-named because it separates the work into differnt bins or buckets,
and performs the specified bin.  It's best illustrated by example:

```bash
$ clum example --bins=0/2	
```

The bins argument takes two integers, separated by a slash.  The first number
indicates which bin should be done, and the second argument indicates the
total number of bins.  In the above example, the command will execute bin 0
of 2, or in other words, it will do approximately half ot the work.  The other
half of the work would be done by specifying `--bins=1/2`.  Note that bins
are zero-indexed.

This gives you a handy way to distrubte your work across a few machines even
if they aren't linked together and managed by a job scheduler.  If you had, 
say, three machines, then you could run `clum` using 0/3, 1/3, and 2/3 as 
the values supplied to `--bins` and the work will be evenly split without
the need for any fuss.

You may be wondering how `clum` decides which arguments to run in each bin.
In fact, consistently dividing the work without duplicating or missing any calls
relies on two assumptions about the arguments iterable:

	Repeated iterations should yield
	 1. The same elements,
	 2. in the same order.

If that isn't the case, you need to use the `key` option to activate binning
based on the particular arguments themselves, which will stabalize the binning,
as described in "Binning ustable iterables".

### `cluf` creates PBS scripts

When you run `cluf` it splits the work across machines by writing a PBS job
script for each machine, and then it submits those job scripts to the cluster
scheduler using qsub.

Each job script is just a regular shell script which you could run manually,
instead of submitting to the scheduler, if you wanted to.  In fact, it's
useful to use `cluf` to generate the scripts without submitting them, so that
you can test-run one of them.  To generate the scripts without submitting them,
do this:

```bash
$ cluf example -n4 -no-q	# you can also do -q
```

Whether or not the scripts are submitted, they are (by default) written to 
the current working directory.  You may not want to clutter your source code
directory with those scripts, so if you want to specify a different directory,
use the `--jobs-dir` or `-j` option, and provide the path to the directory
where the job scripts should be written.

There are a lot of options that can be specified in the job scripts that
controls how the scheduler will handle them.  For example, you can indicate
that you want a machines with a certain number of nodes, a cretain amount of
memory, or which have gpus available.  It's outside of the scope of the tool
to review all of the different PBS options available, but you can easily set 
any of them without getting your hands dirty -- see "Setting PBS options" below.

If you're new to qsub and PBS, read about it.  But for now, be aware that you 
 can view the status of your jobs (and thier ids) by running

```bash
$ qstat | grep <your-username>
```

And you can delete a job by doing

```bash
$ qdel <job-id>
```

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






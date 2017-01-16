#!/usr/bin/env python
'''
This submodule defines core functionality of the cluster-func module.  The two
most prominent functions are `dispatch` and `do_this`, whose purposes are
described in the following paragraphs.

Note that this module and its contents are not intended to be used directly
(any member might be changed or removed in the future).  Rather, the command
line tools `cluster-func` and `cluster-func-do` should be used, which rely on
this module.

`dispatch` writes a series of files (bash scripts) each of which invokes a
target function many times using multiprocessing.  The main point of `dispatch`
is to break down a large amount of invokations into separate chunks which can
each be run on different machines, without having to divide the work ahead of
time and without interprocess communication.

Each script calls the target function indirectly via a call to `do_this`.
These scripts are qsub-compatible job scripts that are optionally submitted to
to a scheduler using qsub.  They can also be run manually using bash as long as
no module load statements were included (see "Loading Modules" in the
documentation).  Each script represents multiprocessed invocations of the
target function against a subset of its argument sets on a single machine, with
separate scripts intented to run on separate machines.

`do_this` calls a target function many times using multiprocessing on a single
machine.  The main point of `do_this` is to factor out logic needed to spawn a
pool of workers and divide work among them locally on a machine.

The functions `dispatch` and `do_this` are tightly coupled to the command line
tools `cluster-func` and `cluster-func-do`, which are the intended entry
points.

Rather than call `dispatch` and `do_this` directly, those commandline tools
call other functions (respectively `main` and `do`) that first handle the
business of parsing command line arguments, and then delegate to `dispatch` and
`do_this`.  That separation is intended to isolate command line invocation
logic from the job-division and multiprocessing logic.
'''

# Builtins
import os
import sys
import imp
import math
import json
from inspect import getargspec
from subprocess import check_output
from multiprocessing import Process

# 3rd parties
from iterable_queue import IterableQueue

# From this package
import utils
from arguments import Arguments
from arg_parser import ClufArgParser
from exceptions import OptionError, RCFormatError, BinError

# Constants
DEFAULT_PBS_OPTIONS = {'name': '{target}-{subjob}-{num_subjobs}'}
DEFAULT_CLUF_OPTIONS = {
	'target_func_name': 'target', 
	'argument_iterable_name': 'args',
	'these_bins': [0],
	'num_bins': 1,
	'queue': False, 
	'target_cli': [],
	'env': {},
	'processes': utils.cpus(),
	'pbs_options': {}
}
 
DEFAULT_GUILLIMIN_MODULES	= ['Python/2.7.10']
TEMPLATE = '''#!/bin/bash
{pbs_option_statements}
cd {current_directory}
{prepend_statements}
{command}
{append_statements}
'''

# Load the RC_PARAMS (if the user has a .clufrc file).
try:
	RC_PARAMS = json.loads(open(os.path.expanduser('~/.clufrc')).read())
	utils.normalize_options(RC_PARAMS)
except IOError:
	RC_PARAMS = {}
except ValueError as e:
	print '.clufrc: %s' % str(e)
	sys.exit(1)

# Validate the RC_PARAMS.  If there's an error, inform user it's in rc_file.
try:
	utils.validate_options(RC_PARAMS)
except OptionError as e:
	print '.clufrc: %s' % str(e)
	sys.exit(1)


# Entry points for handling the `cluf` command.
def main():
	'''
	Possible entry point, used by the `cluster-func` command.  Parses command
	line arguments then delegates to dispatch.

	Divides the work of an embarassingly parallel problem among compute nodes
	by writing scripts which, when run on separate nodes, perform partitions
	of the work.

	Optionally submits those scripts via qsub.  Behavior depends on commandline
	arguments given, see `parse_dispatch_args` for details or run
		$ cluster-func -h
	'''


	# In this block we can catch early problems with command line arguments
	# that are supplied, and print a friendlier message to the user
	parser = ClufArgParser()
	try:

		# Parse arguments, pull out the running mode and the target module.
		args = parser.parse_args()
		mode = args.pop('mode')
		target_module_path = args.pop('target_module_path')

		# Run the function with the arguments
		if mode == 'dispatch':
			dispatch(target_module_path, args)
		elif mode == 'direct':
			run_direct(target_module_path, args)
		else:
			raise OptionError('Unexpected mode: %s' % mode)

	# Handle errors by printing error message followed by the usage
	except OptionError, e:
		print '\n%s\n' % str(e)
		parser.print_usage()




def load_module(target_module_path):
	'''
	Import the module located at `target_module_path`.  The target module's name
	and a reference to the target module are returned (in that order).
	'''
	full_path, target_module_name, found_module = find_module(
		target_module_path)
	target_module = imp.load_module(target_module_name, *found_module)
	return target_module_name, target_module


def find_module(target_module_path):
	'''
	Resolve the module to be loaded.  The file extension given 
	by target_module_path (if any) is ignored, because python modules may be
	imported from .py, .pyc, and many others.  Further more, it's possible for
	the module to be found as a builtin or on sys.path.  This method resolves
	the requested model to a specific source.  The full path to the source, 
	target module's name, and a tuple describing the found module suitable for
	use in imp.load_module are returned, in that order.
	'''
	path, fname = os.path.split(target_module_path)
	target_module_name, extension = os.path.splitext(fname)
	found_module = imp.find_module(target_module_name, [path])
	full_path = found_module[1]
	return full_path, target_module_name, found_module


def get_options(options, target_module):

	# Get the module options
	cluf_options = getattr(target_module, 'cluf_options', {})
	utils.normalize_options(cluf_options)

	# Merge commandline options, module options, RC_PARAMS, and default options.
	options = utils.merge_dicts(
		options, cluf_options, RC_PARAMS, DEFAULT_CLUF_OPTIONS
	)

	# Validate the merged options
	utils.validate_options(options)

	return options


def dispatch(target_module_path, options):
	'''
	Creates a set of scripts that, when run, will each perform a portion of
	a large job.  The job is defined by the python module located at 
	`target_module_path`.  This module contains (at least) two members:

		1. a "target function" which needs to be run many times using different
			argument sets, and

		2. an "arguments iterable", which yields the sets of arguments at which
			with which the function needs to be called.

	As an example usecase, the target function could preprocess a text file
	and the arguments iterable might yield the path to the input file and the
	path at which to write the result.

	The main point of dispatch is to break the work down into portions, which
	will each be run on different machines.  Each script that this function 
	writes is responsible for calling the target function using a subset of 
	the argument sets yielded by the arguments iterable.

	Each script itself calls the commandline tool `cluster-func-do` in order
	to invoke its portion of the argument sets, using multiprocessing, on
	one machine.

	The output script is also partly controlled by optional configurations
	in the target module.  See "Target Module Configurations" in the 
	documentation.  If the `modules` option is an empty list, then the scripts
	can be executed from a shell without submitting with qsub.

	Inputs

	* target_module_path [str] - path to the target module that contains the
		target function and the arguments iterable (and possibly other
		configuration options for the job.

	* options [dict] - Various options that control how the job dispatching
		works are stored here.  These will be merged with `cluf_options`
		found in the target_module (if any), and then merged 
		CLUF_DEFAULT_OPTIONS, in order of decreasing precedence. Valid keys
		are:

		- nodes [int|None] - number of machines over which to spread the work 
			(equivalently, the number of scripts to generate).  Either this or
			`iterations` should be provided (i.e. not be None).

		- iterations [int|None] - Approximate number of function calls to 
			be performed per machine.  This may be provided instead of `nodes`,
			in which case the number of machines needed will be calculated by
			counting the number of arguments in `iterable` and hence the total
			number of iterations.  Either this or `nodes` should be provided
			(i.e. not be None). Overridden by `nodes` if both are supplied.

		- processes [int] - Number of processers to request per node, and number 
			of processes to be spawned on each node.  Overrides setting in
			`pbs_options` if any.

		- jobs_dir [str] - Path at which to write the job scripts, will be 
			created if it doesn't exist.  Default is the current working
			directory.  

		- target_func_name [str] - name of the target function.  It can actually 
			be an identifier for any callable in the module's namespace.
			Default is to look for a callable called "target".

		- argument_iterable_name [str] - name of the iterable that yields 
			argument sets.  This iterable should yield tuples of arguments;
			each tuple will be unpacked and passed as the arguments list to the
			target function.  If an invocation involves a single argument, it
			need not be within a tuple (unless that single argument is itself a
			tuple).

		- queue [bool] - Whether to enqueue the generated scripts to
			the job scheduler using the `qsub` command.  Default is to enqueue.

		- target_cli [list] - Command line arguments intended for interpretation
			by the target module.  These are passed through, and, when the
			target module is loaded (during execution of the scripts output by
			this function), those arguments will appear in sys.argv, just as
			they would if the target module were directly run in a shell.

	[No outputs]
	'''

	# Import the target module, get needed members.
	target_module_name, module = load_module(target_module_path)

	# Resolve the options.  In `merge_dicts`, the left-more takes precedence.
	options = get_options(options, module)

	# Get the target function and arguments iterable
	target_func, iterable = get_target_func_and_iterable(module, options)

	# How many nodes will we use?  We might need to count the arguments iterable.
	options['nodes'] = get_num_nodes(options, iterable)

	# Ensure the jobs dir exists.
	utils.ensure_exists(options['jobs_dir'])

	# Print a message about what will be hashed.  Reduces user errors from
	# badly formatted hash options (which would silently cause all of the work
	# to be done by a single node)
	if 'hash' in options:
		print 'Dividing work by hashing arguments'
		positional_args = [str(h) for h in options['hash'] if isinstance(h, int)]
		keyword_args = [
			str(h) for h in options['hash'] if isinstance(h, basestring)]
		if len(positional_args) > 0:
			print '\t- positional arguments: %s' % ', '.join(positional_args)
		if len(keyword_args) > 0:
			print '\t- keyword arguments: %s' % ', '.join(keyword_args)

	elif 'key' in options:
		arg_type = 'positional' if isinstance(options['key'], int) else 'keyword'
		print (
			'Work will be explicitly assigned using %s argument %s' 
			% (arg_type, options['key'])
		)

	else:
		print 'Dividing work based on argument order'

	# Make each job script, and possibly enqueue it
	for node_num in range(options['nodes']):

		# Format the script for this iteration
		script = format_script(target_module_name, node_num, options)

		# Write the script to disk
		script_path = resolve_script_path(target_module_name, node_num, options)
		open(script_path, 'w').write(script)

		# Queue the script
		if options['queue']:
			print 'submitting job %d' % node_num
			print check_output(['qsub %s' % script_path], shell=True)
		else:
			print 'created script for subjob %d' % node_num


def resolve_script_path(target_module_name, node_num, options):
	script_name_fmt = options['pbs_options'].get(
		'name', DEFAULT_PBS_OPTIONS['name'])
	script_name = script_name_fmt.format(
		target=target_module_name, subjob=node_num, num_subjobs=options['nodes'])
	return os.path.join(options['jobs_dir'], script_name + '.pbs')


def resolve_options(
	primary_options, secondary_options, defaults={}, keys=None
):

	# If keys is provided, use those keys (and only those keys).
	# But by default, consider the union of all keys in the provided dictionaries
	if keys is None:
		keys = set(
			primary_options.keys() + secondary_options.keys() + defaults.keys()
		)

	resolved_options = {}
	for key in all_keys:
		resolved_options[key] = (
			primary_options.get(key, None)
			or secondary_options.get(key, None)
			or defaults.get(key, None)
		)

	return resolved_options



def format_script(target_module_name, node_num, options):

	# Work out pbs statements for this job
	pbs_option_statements = format_pbs_statements(
		target_module_name, node_num, options
	)

	# Get any additional statements to prepend
	prepend_statements = [
		open(script).read() for script in options['prepend_script']
	]
	prepend_statements.extend(options['prepend_statements'])
	prepend_statements = '\n'.join(prepend_statements)

	# Get any additional statements to append
	append_statements = [
		open(script).read() for script in options['append_script']
	]
	append_statements.extend(options['append_statements'])
	append_statements = '\n'.join(append_statements)

	command = format_command_statement(target_module_name, node_num, options)

	# Format the pbs script for this job
	return TEMPLATE.format(
		pbs_option_statements=pbs_option_statements,
		prepend_statements=prepend_statements,
		append_statements=append_statements,
		current_directory=os.getcwd(),
		command=command
	)


def format_command_statement(target_module_name, node_num, options):

	# Collect a list of tokens that make up the command
	command_tokens = []

	# Add environment variables if any
	if 'env' in options:
		command_tokens.append(options['env'])

	# Add the main part of the command
	command_tokens.extend([
		'cluf',
		target_module_name,
		'-m', 'direct',
		'-b', '%s/%s' % (node_num, options['nodes']),
		'-t', options['target_func_name'],
		'-a', options['argument_iterable_name'],
	])

	# Add the hash option if any
	if 'hash' in options:
		command_tokens.extend(['-x', options['hash_cli']])

	# Add the key option if any
	if 'key' in options:
		command_tokens.extend(['-k', str(options['key'])])

	# Add the processors option if any
	if 'processes' in options:
		command_tokens.extend(['-p', str(options['processes'])])

	# Place the pass-through command line args (if any) after a '--' separator
	if len(options['target_cli']):
		command_tokens.append('--')
		command_tokens.extend(options['target_cli'])

	return ' '.join(command_tokens)


def get_num_nodes(options, argument_iterable):

	# If nodes was explicitly provided as an option, use that
	if 'nodes' in options:
		return options['nodes']

	# Either 'nodes' or 'iterations' must be specified in the options
	if 'iterations' not in options:
		raise OptionError(
			'You must specify either the number of nodes or the '
			'number of inputs per node.'
		)

	print 'Counting iterations to determine number of nodes needed...'
	# The number of nodes will be based on the supplied number of iterations per
	# node.  We need to count total iterations.  Try calling len directly on
	# the argument iterable (this will work for lists, e.g.)
	try:
		num_iterations = len(argument_iterable)

	# If the iterable doesn't know it's length, we need to count it.
	except AttributeError:
		num_iterations = 0
		for item in argument_iterable:
			num_iterations += 1

	# Calculate the number of nodes needed based on iterations per node
	nodes = int(math.ceil(num_iterations / float(options['iterations'])))

	print (
		'\t%d iterations, will be divided over %d nodes (~%d iterations each)'
		% (num_iterations, nodes, options['iterations'])
	)
	return nodes


def format_pbs_statements(target_module_name, node_num, options):
	'''
	Helper function that prepares the pbs option statements for scripts created
	by dispatch.

	Inputs

	* target_module_name [str] - the name of the target module (no file 
		extension).

	* node_num [int] - node identifier between 0 and the number of nodes 
		(=`nodes`).

	* options [dict(pbs_options={},node=int)] - Dictionary that contains
		a dictionary of PBS configuration options and an integer representing the
		total number of nodes being used for the job.
		The following keys may appear in the pbs_options:
		- '<key>': where <key> is the name of any option specified in the form 
			-l <key>=<val>
			examples: 'walltime', 'ppn', 'pmem', 'gpus', etc.
		- 'stdout': the path to where stdout should be written.
		- 'stderr': the path to where stderr should be written.
		- 'name': the name to be given to the job (e.g. as seen when running
			qstat).
		* Note -- 'nodes' should not appear within pbs_options because each 
			script is intended to run on one machine.
	'''

	# Pull out the relevant options for easier access
	pbs_options = options['pbs_options']
	nodes = options['nodes']

	# Many pbs parameters are specified using a generic statement format.
	# Identify the parameters that need to be handled separately.
	non_generic_params = {'ppn', 'stdout', 'stderr', 'name'}

	# First format the generic parameters
	pbs_option_statements = [
		'#PBS -l %s=%s' % (k, v) 
		for k, v in pbs_options.items() 
		if k not in non_generic_params
	]

	# Next we will handle each of the non-generic parameters.
	# We begin by specifying the number of processors.
	if 'ppn' in pbs_options:
		pbs_option_statements.append(
			'#PBS -l nodes=1:ppn=%s' % pbs_options['ppn'])
	elif 'processes' in options:
		pbs_option_statements.append(
			'#PBS -l nodes=1:ppn=%s' % options['processes'])

	# Specify the name of the job (this is what will display, e.g., when
	# calling qstat)
	job_name_formatter = pbs_options.get('name', DEFAULT_PBS_OPTIONS['name'])
	job_name = job_name_formatter.format(
		target=target_module_name, subjob=node_num, num_subjobs=nodes
	)
	pbs_option_statements.append('#PBS -N ' + job_name)

	# Specify the stdout path.  If none was given, use the default.
	stdout_path_formatter = pbs_options.get(
		'stdout', job_name_formatter + '.stdout')
	stdout_relative_path = stdout_path_formatter.format(
		target=target_module_name, subjob=node_num, num_subjobs=nodes
	)
	stdout_relative_path = os.path.expanduser(stdout_relative_path)
	stdout_path = os.path.join(options['jobs_dir'], stdout_relative_path)
	pbs_option_statements.append('#PBS -o ' + stdout_path)

	# Specify the stderr path.  If none was given, use the default.
	stderr_path_formatter = pbs_options.get(
		'stderr', job_name_formatter + '.stderr')
	stderr_relative_path = stderr_path_formatter.format(
		target=target_module_name, subjob=node_num, num_subjobs=nodes
	)
	stderr_relative_path = os.path.expanduser(stderr_relative_path)
	stderr_path = os.path.join(options['jobs_dir'], stderr_relative_path)
	pbs_option_statements.append('#PBS -e ' + stderr_path)

	return '\n'.join(pbs_option_statements)


def run_direct( target_module_path, options
):
	'''
	This function performs a portion of an embarassingly parallel problem that
	is defined in the python module located at `target_module_path`.
	This module contains (at least) two members:

		1. a "target function" which needs to be run many times using different
			argument sets, and

		2. an "arguments iterable", which yields the sets of arguments at which
			with which the function needs to be called.

	As an example usecase, the target function could preprocess a text file
	and the arguments iterable might yield the path to the input file and the
	path at which to write the result.

	The purpose of this function is to factor out the concern of setting up
	distributing the work accross several processors.  Note that, in general,
	this function will only perform a *subset* of the target function
	iterations provided for by the arguments iterable.  

	The specific subset performed depends on the values of `these_bins`, `bin`,
	as well as the value assigned to the optional target module configuration
	member `key`.  For details on how this subset is determined see "Job
	Partitionning" in the documentation, or see the function
	`generate_args_subset` below.

	Inputs

	* target_module_path [str] - path to the target module that contains the
		target function and the arguments iterable (and possibly other
		configuration options for the job.

	* these_bins [list(int)] - Controls the particular subset of argument sets 
		from the arguments iterable used to run the target function.  Must be
		an integer from 0 to `num_bins`-1 inclusive.  

	* num_bins [int] - Number of portions into which the work has been split.
		Consequently, the number of iterations of the target function that 
		will be performed is approximately equal to 1 / `num_bins` times the
		number of argument sets yielded by the arguments iterable.  Can be
		1 in which case the full job will be processed.  Must be greater than 0.
		In normal usage, this should be equal to the number of machines over
		which the work has been spread.

	* processes [int|None] - number of worker processes to be concurrently 
		spawned for repeated execution of the target function.  By default
		this is equal to the number of cpus available on the machine.

	* target_func_name [str] - name of the target function.  It can actually be
		an identifier for any callable in the module's namespace.  Default is
		to look for a callable called "target".

	* argument_iterable_name [str] - name of the iterable that yields argument
		sets.  This iterable should yield tuples of arguments; each tuple will
		be unpacked and passed as the arguments list to the target function.
		If an invocation involves a single argument, it need not be within a 
		tuple (unless that single argument is itself a tuple).

	* target_cli [list] - Command line arguments intended for interpretation
		by the target module.  These are passed through, and, when the 
		target module is loaded (during execution of the scripts output by this
		function), those arguments will appear in sys.argv, just as they would
		if the target module were directly run in a shell.

	[No outputs]
	'''

	# Pass the arguments in target_cli (if any) through to the target module by
	# putting them in sys.argv before loading the target module.
	pass_through_args(target_module_path, options['target_cli'])

	# Load the target module, the iterable, and the target function
	module_name, module = load_module(target_module_path)

	# Resolve the options.  In `merge_dicts`, the left-more takes precedence.
	options = get_options(options, module)

	# Get the target function and arguments iterable.
	target_func, iterable = get_target_func_and_iterable(module, options)

	# Make a queue on which to put arguments
	args_queue = IterableQueue()

	# Start the pool of workers
	for proc_num in range(options.get('processes', utils.cpus())):
		proc = Process(
			target=worker, 
			args=(target_func, args_queue.get_consumer(),)
		)
		proc.start()

	# Start loading work onto the args queue
	args_producer = args_queue.get_producer()
	args_queue.close()
	for args in generate_args_subset(iterable, options):
		args_producer.put(args)
	args_producer.close()


def get_target_func_and_iterable(target_module, options):

	try:
		target_func = getattr(target_module, options['target_func_name'])
		iterable = getattr(target_module, options['argument_iterable_name'])
	except AttributeError, e:
		raise OptionError(str(e))

	# What we call the "iterable" may be an iterable or a callable that yields
	# an iterable.  Resolve that now.
	try:
		iter(iterable)
	except TypeError:
		iterable = iterable()

	return target_func, iterable


def pass_through_args(target_module_path, args):

	"""
	Resolve the file name of the name of the target module, and put
	that name, along with args, into sys.argv.  Recall that the first argument
	is sys.argv is always the called script's filename.
	"""

	# Figure out the filename found for the target script, note that this might
	# differ from the basename of target_module_path...
	full_module_path, module_name, found_module = find_module(target_module_path)
	module_fname = os.path.basename(full_module_path)

	# Fallback to the basename in target_module_path if module_fname came out 
	# blank.
	if module_fname.strip() == '':
		module_fname = os.path.basename(target_module_path)

	# Add teh arguments to sys.argv
	sys.argv = [module_fname]
	sys.argv.extend(args)



def worker(target_func, args_consumer):
	'''
	Runs the callable `target_func` repeatedly inside a single process.  
	Consumes sets of arguments from the IterableQueue.ConsumerQueue 
	`args_consumer`, unpacks them, and executes target_func with them.
	'''
	for args in args_consumer:
		target_func(*args.args, **args.kwargs)


def generate_args_subset(iterable, options):
	"""
	Generator that yields a subset of the elements from `iterable`.
	This helps to divide the elements of `iterable` into `num_bins`
	subsets, so that each subset can be run on a different machine without
	missing or duplicating any elements.
	
	For example, if `num_bins` is 4, then this function will return an 
	iterable that yields (approximately) one out of every four of the 
	elements of `iterable`.

	The particular subset of elements yielded is controlled by `these_bins`, 
	which must be an integer from 0 to `num_bins`-1 inclusive.  
	
	So long as the elements in `iterable` don't change, and their order
	doesn't change, then calling this function for all values of
	`these_bins` gives iterables whose elements are a partition of `iterable`s
	elements -- none repeated, none missed.

	But if consistent ordering or contents of iterable can't be guaranteed,
	then `key` must be set to an integer value, as described below.

	To understand `key`, recall that each element of `iterable` is a tuple 
	of arguments to be supplied to the target function.  `key` selects one 
	of the arguments, and uses its sha1 hash to determine whether that
	particluar argument set belongs to `these_bins`.  

	Ideally `key` should point to an argument whose value is unique in 
	`iterable`.  Duplicated values will all be routed to the same machine, which 
	might imbalance workloads.

	It is essential that the key argument should have a stable string
	representation.  Specifically do not have it point to an object whose
	string representation contains the memory address, because that won't be
	consistent accross machines.

	Note, although the elements of `iterable` are expected to be tuples
	(each nested element being a positional argument), if an invokation of
	the target function is made with a single argument, it doesn't need to be
	packed into a length-1 tuple (except if it is iteslf a tuple, since that
	would be ambiguous).
	"""

	# If "hash" is specified, then concatenate the string representations
	# of each argument indexed in hash (which is a list of ints), and
	# hash it to determine the bin.
	if 'hash' in options:
		for args in as_arguments(iterable):
			hashable = ''.join([
				str(args[i])
				for i in options['hash'] if i in args
			])
			this_bin = utils.binify(hashable, options['num_bins'])
			if this_bin in options['these_bins']:
				yield args

	# However, if "key" is specified, then the key'th argument designates
	# the bin
	elif 'key' in options:
		for i, args in enumerate(as_arguments(iterable)):
			try:
				key = args[options['key']]
			except KeyError:
				raise BinError(
					'Argument %s was not found in iteration %d' 
					% (repr(options['key']), i)
				)
			if key in options['these_bins']:
				yield args

	# By default, work is dealt around to each bin in the order that it is
	# yielded
	else:
		for i, args in enumerate(as_arguments(iterable)):
			if i % options['num_bins'] in options['these_bins']:
				yield args


def as_arguments(iterable):
	"""Ensure elements emerge wrapped Arguments objects."""
	for item in iterable:
		if isinstance(item, Arguments):
			yield item
		elif isinstance(item, tuple):
			yield Arguments(*item)
		else:
			yield Arguments(item)



if __name__ == '__main__':
	main()



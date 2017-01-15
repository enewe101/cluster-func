import sys
import utils
import argparse

class ClufArgParser(object):

	def __init__(self):
		self.parser = self._build_parser()


	def _build_parser(self):
		"""
		Creates / configures the underlying argument parser, adding all the 
		expected arguments.
		"""

		# First set up the argument parser
		parser = argparse.ArgumentParser(description=(
			'Run a function many times on multiple processors and machines.'
		))

		# Add the only required positional argument.
		parser.add_argument(
			'target_module', 
			help=(
				'path to the python module that contains the target function to '
				'be run many times.'
			)
		)

		# Add various optional arguments.
		parser.add_argument(
			'-j', '--jobs-dir',
			help=(
				'Specify a directory in which to store job scripts and the '
				'files generated from the stdout and stdin during job '
				"execution.  This  directory will be made if it doesn't exist. "
				'This option only takes effect in dispatch mode.'
			)
		)
		parser.add_argument(
			'-t', '--target',
			help=(
				'Alternate name for the target callable to be invoked '
				'repeatedly.  Default is "target".'
			)
		)
		parser.add_argument(
			'-a', '--args',
			help='Alternate name for the arguments iterable.  Default is "args".'
		)
		parser.add_argument(
			'-q', '--queue', action='store_true', default=None,
			help=(
				'Enqueue the generated scripts using qsub.  This option only '
				'takes effect in dispatch mode.'
			)
		)
		parser.add_argument(
			'-p', '--processes', type=int, help='Number of processors to use.'
		)
		parser.add_argument(
			'-b', '--bins', 
			help=(
				'Optionally specify a portion of the work to be done. '
				'Should take the form "x/y" meaning "do the x-th section out of '
				'y total sections.  For example, "0/2" means divide the work '
				'into two halves, and do the first (0th) half.  Note that x and '
				'y should be integers, and x should be from 0 to y-1 '
				'inclusive.  This option only takes effect in direct mode.'
			)
		)
		parser.add_argument(
			'-e', '--env',
			help=(
				'Provide environment variables that should be set when running '
				'sub-jobs.  This is for use in dispatch mode, since job scripts '
				'will run in a different environment.  In direct mode, the '
				'environment is inherited.  The value of this option should be '
				'an enquoted string of space-separated key=value pairs.  For '
				'example:\n'
				"\t$ cluf my_script -n 12 -e 'FOO=bar BAZ=\"fizz bang\"'"
				'will set FOO equal to "bar" and BAZ equal to "fizz bang". '
				'This option only takes effect in dispatch mode.'
			)
		)
		parser.add_argument(
			'-P', '--prepend-script',
			help=(
				'Path to a script whose contents should be included at the '
				'beginning of subjob scripts, being executed before running the '
				'subjob.  You can include multiple comma-separated paths. '
				'This option only takes effect in dispatch mode'
			)
		)
		parser.add_argument(
			'-A', '--append-script',
			help=(
				'Path to a script whose contents should be included at the '
				'end of subjob scripts, being executed after the subjob '
				'completes.  You can include multiple comma-separated paths.  '
				'This option only takes effect in dispatch mode.'
			)
		)
		parser.add_argument(
			'-m', '--mode', choices=('dispatch', 'direct'),
			help=(
				'Explicitly set the mode of operation.  '
				'This option can only be set on the command line.  '
				'Can be set to "direct" '
				'or "dispatch".  In direct mode the job is run, whereas in '
				'dispatch mode a script for the job(s) is created and '
				'optionally enqueued. Setting either -n or -i implicitly sets '
				'the mode of operation to "dispatch", unless specified '
				'otherwise.'
			)
		)
		parser.add_argument(
			'-o', '--pbs-options', help=(
				'Set the PBS options.'
			)
		)

		# Only one of the the optional arguments that determine the argument(s)
		# on which to base binning cannot both be set.
		group = parser.add_mutually_exclusive_group()
		group.add_argument(
			'-x', '--hash',
			help=(
				'Specify an argument or set of arguments to be used to '
				'determine which bin an iteration belons in.  These arguments '
				'should have a stable string representation (i.e. no '
				'unordered containers or memory addresses) and should be '
				'unique over the iterable.  This should only be set '
				"if automatic binning won't work, i.e. if your argument "
				'iterable is not stable.'
			)
		)
		group.add_argument(
			'-k', '--key',
			help=(
				'Integer specifying the positional argument to use as the bin for '
				'each iteration.  That key argument should always take on a value '
				'that is an integer between 0 and num_bins-1.  This should only '
				'be used if you really need to control binning.  Prefer to rely on '
				'automatic binning (if your iterable is stable), or use the -x'
				'option, which is more flexible and less error-prone.'
			)
		)

		# The optional arguments that determine number of nodes / iterations per 
		# node are mutually exlusive.
		group = parser.add_mutually_exclusive_group()
		group.add_argument(
			'-n', '--nodes', type=int, 
			help=(
				'Number of compute nodes.  This option causes the command to '
				'operate in dispatch mode, unless the mode is explicitly set.  '
				'This option can only be set on the command line.'
			)
		)
		group.add_argument(
			'-i', '--iterations', type=int, 
			help=(
				'Approximate number of iterations per compute node.  '
				'This option causes the command to operate in dispatch mode, '
				'unless the mode is explicitly set.  Note that '
				'using this instead of --nodes (-n) can lead to delay because '
				'the total number of iterations has to be counted to '
				'determine the number of compute nodes needed.  '
				'This option can only be set on the command line.'
			)
		)

		return parser


	def parse_args(self, args=sys.argv[1:]):
		'''
		Parses the command line arguments for the `cluf` command.
		'''

		# Parse the arguments.  
		# By calling parse_known_args, we allow unrecognized args to be passed
		# through to the target module's `sys.argv`.  This also gives the
		# desireable behavior that command line arguments intended for the target
		# module can be separated from those intended for `cluf` by a '--'
		# token.
		parsed_args, target_cli = self.parser.parse_known_args(args)

		# Let the user see how the arguments were interpreted.
		for k,v in vars(parsed_args).items():
			print '%s = %s' % (k, v)

		# Pack all the arguments into a dictionary, exclude args that are None
		parsed_args = {
			k: v
			for k, v in vars(parsed_args).items()
			if v is not None
		}

		# Put target_cli in `parsed_args`, and remove the '--' if any.
		parsed_args['target_cli'] = [a for a in target_cli if a != '--']

		# Determine the running mode -- are we dispatching work to nodes on a 
		# compute cluster, or are we going to run the job locally?
		if 'mode' not in parsed_args:
			if 'nodes' in parsed_args or 'iterations' in parsed_args:
				parsed_args['mode'] = 'dispatch'
			else:
				parsed_args['mode'] = 'direct'

		# Replace 'hash' with parsed version.
		if 'hash' in parsed_args:
			parsed_args['hash'] = utils.unfurl(parsed_args['hash'])

		# Normalize the options by rename a few options and parsing the bins
		# option.  Operates through side effects.
		utils.normalize_options(parsed_args)

		return parsed_args

	def print_usage(self):
		"""
		Print the usage statemetn for the `cluf` command.  Delegates to the
		underlying argument parser.
		"""
		self.parser.print_usage()

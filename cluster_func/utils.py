import hashlib
import os
import re
import subprocess
from exceptions import OptionError


NORMALIZED_OPTIONS = {
	'jobs-dir', 'target-func-name', 'argument-iterable-name',
	'queue', 'processes', 'env', 'prepend-script', 'append-script',
	'prepend-statements', 'append-statements', 'hash', 'key', 'nodes',
	'iterations', 'these_bins', 'num_bins', 'target_cli'
}


def cpus():
	""" Number of available virtual or physical CPUs on this system, i.e.
	user/real as output by time(1) when called with an optimally scaling
	userspace-only program"""

	# cpuset
	# cpuset may restrict the number of *available* processors
	try:
		m = re.search(r'(?m)^Cpus_allowed:\s*(.*)$',
					  open('/proc/self/status').read())
		if m:
			res = bin(int(m.group(1).replace(',', ''), 16)).count('1')
			if res > 0:
				return res
	except IOError:
		pass

	# Python 2.6+
	try:
		import multiprocessing
		return multiprocessing.cpu_count()
	except (ImportError, NotImplementedError):
		pass

	# http://code.google.com/p/psutil/
	try:
		import psutil
		return psutil.cpu_count()   # psutil.NUM_CPUS on old versions
	except (ImportError, AttributeError):
		pass

	# POSIX
	try:
		res = int(os.sysconf('SC_NPROCESSORS_ONLN'))

		if res > 0:
			return res
	except (AttributeError, ValueError):
		pass

	# Windows
	try:
		res = int(os.environ['NUMBER_OF_PROCESSORS'])

		if res > 0:
			return res
	except (KeyError, ValueError):
		pass

	# jython
	try:
		from java.lang import Runtime
		runtime = Runtime.getRuntime()
		res = runtime.availableProcessors()
		if res > 0:
			return res
	except ImportError:
		pass

	# BSD
	try:
		sysctl = subprocess.Popen(['sysctl', '-n', 'hw.ncpu'],
								  stdout=subprocess.PIPE)
		scStdout = sysctl.communicate()[0]
		res = int(scStdout)

		if res > 0:
			return res
	except (OSError, ValueError):
		pass

	# Linux
	try:
		res = open('/proc/cpuinfo').read().count('processor\t:')

		if res > 0:
			return res
	except IOError:
		pass

	# Solaris
	try:
		pseudoDevices = os.listdir('/devices/pseudo/')
		res = 0
		for pd in pseudoDevices:
			if re.match(r'^cpuid@[0-9]+$', pd):
				res += 1

		if res > 0:
			return res
	except OSError:
		pass

	# Other UNIXes (heuristic)
	try:
		try:
			dmesg = open('/var/run/dmesg.boot').read()
		except IOError:
			dmesgProcess = subprocess.Popen(['dmesg'], stdout=subprocess.PIPE)
			dmesg = dmesgProcess.communicate()[0]

		res = 0
		while '\ncpu' + str(res) + ':' in dmesg:
			res += 1

		if res > 0:
			return res
	except OSError:
		pass

	raise Exception('Can not determine number of CPUs on this system')



def binify(string_id, num_bins):
    ''' 
    Uniformly assign objects to one of `num_bins` bins based on the
    hash of their unique id string.
    '''
    hexdigest = hashlib.sha1(string_id).hexdigest()
    return int(hexdigest,16) % num_bins


def inbin(string_id, num_bins, this_bin):
	if this_bin >= num_bins:
		raise ValueError(
			'`this_bin` must be an integer from 0 to `num_bins`-1.')
	return binify(string_id, num_bins) == this_bin


UNFURL_SPLITTER_1 = re.compile(',|;')
UNFURL_SPLITTER_2 = re.compile('-|:')
def unfurl(string_representation):
	"""
	Returns the unfurled representation, a list of integers.  

	E.g. '0-2,7-9,10'  -->  [0,1,2,7,8,9,10]
	
	Colons ':' can be used instead of dashes '-', and semicolons ';' can be used 
	in place of commas ','.  Ranges, like 0-2 in the example above, can also
	take a form that has three elements.  These are handled similarly to how
	`range()` handles its arguments, except that stop value is considered 
	inclusively.  Ranges where the stop value is smaller than the start value 
	are ignored.

	E.g. '0:4:2;9:7' --> [0,2,4]
	"""
	unfurled = []

	# Split up span expressions
	spans = UNFURL_SPLITTER_1.split(string_representation)
	for span in spans:

		# Split up the start, stop, and incrment values in the expression
		span = [int(s) for s in UNFURL_SPLITTER_2.split(span)]

		# Handle the case where the span is an individual value.
		if len(span) == 1:
			unfurled.extend(span)
			continue

		# The span may have 2 or 3 values, which will be fed into range()
		# We want to consider the stop value inclusively, so add one to it first.
		span[1] += 1
		unfurled.extend(range(*span))

	return unfurled


def ensure_exists(path):
	if not os.path.exists(path):
		os.makedirs(path)



def normalize_options(options):
	"""
	Mutate the options dict, renaming some of the keys, and parsing the 
	bins option.
	"""

	# Rename some keys.  Though user-friendly, these keys will become confusing 
	# deeper within the handling of the command.
	if 'target' in options:
		options['target-func-name'] = options.pop('target')
	if 'args' in options:
		options['argument-iterable-name'] = options.pop('args')
	if 'target_module' in options:
		options['target_module_path'] = options.pop('target_module')

	# Parse the bins option, replacing it with "these_bins" and "num_bins"
	if 'bins' in options:
		this_bin, num_bins = options.pop('bins').split('/')
		these_bins = utils.unfurl(this_bin)
		num_bins = int(num_bins)
		options['these_bins'] = these_bins
		options['num_bins'] = num_bins

	# Unfurl the scripts listings if any
	if 'prepend-script' in options:
		options['prepend-script'] = options['prepend-script'].split(',')

	# Unfurl the scripts listings if any
	if 'append-script' in options:
		options['prepend-script'] = options['prepend-script'].split(',')

	# Convert env dictionary into a string
	if 'env' in options and not isinstance(options['env'], basestring):
		options['env'] = ' '.join([
			"%s=%s" % (k,v) 
			for k,v in options['env'].items()
		])


def validate_options(options):

	# Raise an error if we see an unexpected option
	for option in options:
		if option not in NORMALIZED_OPTIONS:
			raise OptionError('Unrecognized option: %s' % option)

	# Raise on error if we see conflicting options
	if 'hash' in options and 'key' in options:
		raise OptionError('The `hash` and `key` options are mutually exclusive.')
	if 'nodes' in options and 'iterations' in options:
		raise OptionError(
			'The `nodes` and `iterations` options are mutually exclusive.')


def merge_dicts(*dictionaries):
    merged = {}
    for dictionary in reversed(dictionaries):
        merged.update(dictionary)
    return merged


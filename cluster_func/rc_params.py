import json
import os
import utils
from exceptions import OptionError, RCFormatError
import sys

# Load the RC_PARAMS (if the user has a .clufrc file).
try:
	RC_PARAMS = json.loads(open(os.path.expanduser('~/.clufrc')).read())
	utils.normalize_options(RC_PARAMS)
except IOError:
	RC_PARAMS = {}
except ValueError as e:
	raise RCFormatError(str(e))

## Validate the RC_PARAMS.  If there's an error, inform user it's in rc_file.
try:
	utils.validate_options(RC_PARAMS)
except OptionError as e:
	raise OptionError('.clufrc: %s' % str(e))


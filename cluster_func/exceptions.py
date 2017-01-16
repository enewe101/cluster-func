# Custom exception raised if invalid or conflicting options were used with the
# `cluf` command
class OptionError(ValueError):
	pass

class RCFormatError(ValueError):
	pass

class BinError(KeyError):
	pass

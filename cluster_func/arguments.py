class Arguments(object):
	def __init__(self, *args, **kwargs):
		self.args = args
		self.kwargs=kwargs

	def __str__(self):
		positional_args_tokens = [repr(a) for a in self.args]
		kwargs_tokens = ['%s=%s' % (k,repr(v)) for k,v in self.kwargs.items()]
		args_tokens = positional_args_tokens + kwargs_tokens

		return '(%s)' % ', '.join(args_tokens)


	def __contains__(self, key):
		try:
			self.__getitem__(key)
		except KeyError:
			return False
		return True


	def __getitem__(self, key):
		try:
			return self.args[key]
		except (IndexError, TypeError):
			return self.kwargs[key]


	def __repr__(self):
		return 'Arguments' + self.__str__()

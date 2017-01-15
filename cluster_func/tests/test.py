alphabet = 'abcdefghijklmnopqrst'

args = zip(range(20), alphabet)
my_args = zip(range(20), reversed(alphabet))

def my_func(number, letter):
	print letter, number

def target(number, letter):
	print number, letter

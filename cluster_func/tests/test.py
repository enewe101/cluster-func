import os
from cluster_func import Arguments

alphabet = 'abcdefghijklmnopqrst'

args = zip(range(20), alphabet)
my_args1 = zip(range(20), reversed(alphabet))
my_args2 = [Arguments(number=n, letter=l) for n,l in my_args1]

def my_func(number, letter):
	print os.environ['MYENV']
	print letter, number

def target(number, letter):
	print number, letter


cluf_options = {
	"jobs_dir": "my_jobs",
	"target":	"target",
	"args": "my_args1",
	"processes": 2,
	"bins": "0/10",
	"env": {"MYENV": 5},
	"prepend_statements": [
		"echo my-prepend-statement-2",
		 "echo my-prepend-statement-3"
	],
	"append_statements": [
		"echo my-append-statement-2", 
		"echo my-append-statement-3"
	],
	"append_script": "my-append-script-2,my-append-script-3",
	"prepend_script": "my-prepend-script-2,my-prepend-script-3",
	"iterations": 5,
	"pbs_options": {
		'name': 'yo-{subjob}-{num_subjobs}-{target}',
		'stdout': '~/my-job-{target}-{subjob}-{num_subjobs}.stdout',
		'stderr': '~/../my-job-{target}-{subjob}-{num_subjobs}.stderr'
	}
}

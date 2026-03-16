import pandas as pd
import json
import dataset.dataset as dataset

def write_json_file(dataset, filepath:str):

	# Write the file
	with open(filepath, "w") as file:
		json.dump(
			dataset, 
			default=lambda o: o.json_encode(),
			indent=2,
			fp=file
		)

	return ""

def read_json_file(fp:str, encoding="utf8"):

	# Read the file
	with open(fp) as f:
		d = json.load(f)
		print(json.dumps(d, indent=2))
	# do checks, convert to df, actually return the df

	return d
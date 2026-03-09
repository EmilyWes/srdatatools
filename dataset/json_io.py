import pandas as pd
import json
import dataset.dataset as dataset

def write_json_file(dataset, filepath:str):

	# Write the file
	print(json.dumps(dataset))

	# do checks, convert to df, actually return the df

	return ""

def read_csv_file(fp:str, encoding="utf8"):

	# Read the file
	df = pd.read_csv(fp, encoding=encoding)

	# do checks, convert to df, actually return the df

	return df
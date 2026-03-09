import pandas as pd

def write_csv_file(df, filename:str):

	# Write the file
	df.to_csv(filename, index=False)

	# do checks, convert to df, actually return the df

	return ""

def read_csv_file(fp:str, encoding="utf8"):

	# Read the file
	df = pd.read_csv(fp, encoding=encoding)

	# do checks, convert to df, actually return the df

	return df
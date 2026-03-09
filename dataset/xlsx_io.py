import pandas as pd

def write_excel_file(df, filename:str):

	# Write the file
	df.to_excel(filename, index=False)

	# do checks, convert to df, actually return the df

	return ""


def read_excel_file(fp:str, encoding="utf8"):

	# Read the file
	df = pd.read_excel(fp)

	# do checks, convert to df, actually return the df

	return df
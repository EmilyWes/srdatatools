import pandas as pd
import rispy
import copy


def write_ris_file(df: pd.DataFrame, filepath:str):

	# Write the file
	records = copy.deepcopy(df.to_dict("records"))
	with open(filepath, "w", encoding="utf8") as fp:
		rispy.dump(records, fp)

	# do checks, convert to df, actually return the df

	return ""

def read_ris_file(fp, encoding="utf8"):
	with open(fp, encoding=encoding) as bibliography_file:
		entries = list(rispy.load(bibliography_file, skip_unknown_tags=True))

		if entries is None:
			raise ValueError("Cannot find proper encoding for data file")

		return pd.DataFrame(entries)
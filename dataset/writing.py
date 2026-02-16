import pandas as pd
import rispy
import copy


def _write_ris_file(df, filepath:str):

	# Write the file
	records = copy.deepcopy(df.to_dict("records"))
	with open(filepath, "w", encoding="utf8") as fp:
		rispy.dump(records, fp)

	# do checks, convert to df, actually return the df

	return ""


def _write_csv_file(df, filename:str):

	# Write the file
	df.to_csv(filename, index=False)

	# do checks, convert to df, actually return the df

	return ""


def _write_excel_file(df, filename:str):

	# Write the file
	df.to_excel(filename, index=False)

	# do checks, convert to df, actually return the df

	return ""


def write_file(df, filename: str):
	extension = filename.split('.')[-1]

	if extension == "ris":
		_write_ris_file(df, filename)
	elif extension == "csv":
		_write_csv_file(df, filename)
	elif extension == "xlsx":
		_write_excel_file(df, filename)
	else:
		print(f"extension type {extension} not supported as output.")



#df = pd.read_csv("telemonitoring_year_corrected.csv")
#RISWriter.write_data(df, "telemonitoring_year_corrected.ris")

#df = RISReader.read_data("asr_all_rec_screening_EE_AI_dupl_marked.ris")
#df.to_csv("asr_all_rec_screening_EE_AI_dupl_marked.csv")
import pandas as pd
import rispy


def _read_ris_file(fp, encoding="utf8"):
	with open(fp, encoding=encoding) as bibliography_file:
		entries = list(rispy.load(bibliography_file, skip_unknown_tags=True))

		if entries is None:
			raise ValueError("Cannot find proper encoding for data file")

		return pd.DataFrame(entries)

def _read_csv_file(fp:str, encoding="utf8"):

	# Read the file
	df = pd.read_csv(fp, encoding=encoding)

	# do checks, convert to df, actually return the df

	return df

def _read_excel_file(fp:str, encoding="utf8"):

	# Read the file
	df = pd.read_excel(fp)

	# do checks, convert to df, actually return the df

	return df


def read_file(fp: str):
	extension = fp.split('.')[-1]
	encodings = ["utf-8", "utf-8-sig", "ISO-8859-1"]

	for encoding in encodings:
		try:
			if extension == "ris":
				df = _read_ris_file(fp, encoding)
			elif extension == "csv":
				df = _read_csv_file(fp, encoding)
			elif extension == "xlsx":
				df = _read_excel_file(fp, encoding)
			break
		except UnicodeDecodeError:
			continue
		except Exception as e:
			raise ValueError(f"Error reading file: {e}")

	return df

#df = pd.read_csv("telemonitoring_year_corrected.csv")
#RISWriter.write_data(df, "telemonitoring_year_corrected.ris")

#df = RISReader.read_data("asr_all_rec_screening_EE_AI_dupl_marked.ris")
#df.to_csv("asr_all_rec_screening_EE_AI_dupl_marked.csv")
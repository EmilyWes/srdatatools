import pandas as pd
import os
from dataset.record import *

# formats
import dataset.io.json_io as json_io
import dataset.io.csv_io as csv_io
import dataset.io.ris_io as ris_io
import dataset.io.xlsx_io as xlsx_io

class Dataset:

	# columns for writing. todo: move this code to get it from record automatically.
	columns = ["doi", "openalex_id", "authors", "title"]

	def __init__(self):
		self.records = []

	# reads input file to records
	def get_data(self, filepath: str):
		if filepath.split('.')[-1] in ["ris", "csv", "xlsx"]:
			df = self.read_file(filepath)
			cols = list(df)
			for _, row in df.iterrows():
				record = Record()
				for col, val in zip(cols, row):
					record.add_value(col, val)
				self.records.append(record)
		elif filepath.split('.')[-1] == "json":
			data = json_io.read_json_file(filepath)

			# hardcoded use of own format only at the moment!
			dataset = Dataset()
			for record_data in data["dataset"]:
				record = Record.create_from_json(record_data["record"])

	# converts records to dataframe
	def get_df(self):
		data = [record.get_row() for record in self.records]
		df = pd.DataFrame(data, columns=Dataset.columns)
		df = df.dropna(how='all', axis=1)

		return df

	# write output file
	def write_data(self, filepath: str):

		extension = filepath.split('.')[-1]

		if extension == "ris":
			ris_io.write_ris_file(self.get_df(), filepath)
		elif extension == "csv":
			csv_io.write_csv_file(self.get_df(), filepath)
		elif extension == "xlsx":
			xlsx_io.write_excel_file(self.get_df(), filepath)
		elif extension == "json":
			json_io.write_json_file(self, filepath)
		else:
			print(f"extension type {extension} not supported as output.")


	def read_file(self, filepath: str):
		extension = filepath.split('.')[-1]
		encodings = ["utf-8", "utf-8-sig", "ISO-8859-1"]

		for encoding in encodings:
			try:
				if extension == "ris":
					df = ris_io.read_ris_file(filepath, encoding)
				elif extension == "csv":
					df = csv_io.read_csv_file(filepath, encoding)
				elif extension == "xlsx":
					df = xlsx_io.read_excel_file(filepath, encoding)
				break
			except UnicodeDecodeError:
				continue
			except Exception as e:
				raise ValueError(f"Error reading file: {e}")

		return df

	def json_encode(self):
		return {
			"dataset": self.records
		}
import pandas as pd
import os
from dataset.record import *

# formats
import dataset.json_io as json_io
import dataset.csv_io as csv_io
import dataset.ris_io as ris_io
import dataset.xlsx_io as xlsx_io


class Author:

	def __init__(self):
		self.name = ""
		self.first_name = ""
		self.last_name = ""
		self.address = ""


class Dataset:

	def __init__(self):
		self.records = []

		# Remember the columns for writing.
		dir_path = os.path.dirname(__file__) + "\\"
		data_format = pd.read_csv(dir_path + "format.csv")
		self.columns = list(data_format["name"])

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
			i = 5 #todo

	# converts records to dataframe
	def get_df(self):
		data = [record.get_row() for record in self.records]
		df = pd.DataFrame(data, columns=self.columns)
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
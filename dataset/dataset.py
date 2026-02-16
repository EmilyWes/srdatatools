import pandas as pd
import os
from dataset.record import *
import dataset.reading as reading
import dataset.writing as writing


class Dataset:

	def __init__(self):
		self.records = []
		self.df = None
		dir_path = os.path.dirname(__file__) + "\\"
		data_format = pd.read_csv(dir_path + "format.csv")
		self.columns = list(data_format["name"])

	# reads input file to records
	def get_data(self, filepath: str):
		df = reading.read_file(filepath)
		cols = list(df)
		for _, row in df.iterrows():
			record = Record()
			for col, val in zip(cols, row):
				record.add_value(col, val)
			self.records.append(record)

	# converts records to dataframe
	def get_df(self):
		data = [record.get_row() for record in self.records]
		df = pd.DataFrame(data, columns=self.columns)
		df = df.dropna(how='all', axis=1)

		return df

	# write output file
	def write_data(self, filepath: str):
		df = self.get_df()
		writing.write_file(df, filepath)

import pandas as pd
import numpy as np
import os

'''

The record class is for a single record, aka paper or book chapter.
It contains all possible fields the record can have, together with modifying functions.

'''


# The field class is a simple data object for field in the record
class Field:

	def __init__(self, name: str, aliases: list[str], value = None, alt_values = []):
		self.name = name
		self.aliases = aliases
		self.value = value
		self.alt_values = []

	def match(self, name: str):
		return name == self.name or name in self.aliases

	def add_value(self, new_value):
		if isinstance(new_value, list):
			for v in new_value:
				self.add_value(v)
		else:
			if pd.isna(self.value):
				self.value = new_value
			else:
				self.alt_values.append(new_value)

class Record:

	def __init__(self):
		self.fields = []
		dir_path = os.path.dirname(__file__) + "\\"
		data_format = pd.read_csv(dir_path + "format.csv")
		for _, row in data_format.iterrows():
			self.fields.append(Field(row["name"], [] if pd.isna(row["aliases"]) else row["aliases"].split("|")))

	def get_row(self):
		return [field.value for field in self.fields]

	# returns true if a new field was created. False if it existed and is now updated.
	def add_value(self, name: str, value):
		low_name = name.lower()
		for field in self.fields:
			if field.match(low_name):
				field.add_value(value)
				return

		# case where we did not have any match:
		# todo: create new field in the record and return 


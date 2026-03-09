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
	
	def is_empty(self):
		return pd.isna(self.value)

	def is_not_empty(self):
		return not self.is_empty()

	def json_encode(self):
		return { self.name:
			{
			"value": self.value,
			"alternatives": self.alt_values
		}
		}
	
class Author:
	def __init__(self, input):
		# determine separator
		sep = ","

		names = input.split(sep)

		self.name = input
		self.firstname = names[0].strip() if len(names) > 1 else ""
		self.lastname = names[-1].strip() if len(names) > 0 else ""
		self.address = ""

	def json_encode(self):
		return {
			self.name:
			{
				"first name": self.firstname,
				"last name": self.lastname,
				"address": self.address
			}
		}

class Authors(Field):

	def __init__(self, name: str, aliases: list[str], value = None, alt_values = []):
		super().__init__(name, aliases, value, alt_values)
		self.value = []

	def is_empty(self):
		return len(self.value) == 0

	def add_value(self, new_value):
		if isinstance(new_value, list):
			for v in new_value:
				self.add_value(v)
		else:

			if not pd.isna(new_value):
				print(new_value)
				# determine format
				sep = ";"
				
				# split into multiple authors
				author_strings = new_value.split(sep)
				for a in author_strings:
					self.value.append(Author(a))		
	

class Record:

	def __init__(self):
		self.fields = []
		dir_path = os.path.dirname(__file__) + "\\"
		data_format = pd.read_csv(dir_path + "format.csv")
		for _, row in data_format.iterrows():
			if row["name"] == "authors":
				self.fields.append(Authors(row["name"], [] if pd.isna(row["aliases"]) else row["aliases"].split("|")))
			else :
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

	def json_encode(self):

		return {
			"record": 
			{
				f.name: {"value": f.value, "alt": f.alt_values} for f in self.fields if not f.is_empty()
		}
		}
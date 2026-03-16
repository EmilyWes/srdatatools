import pandas as pd
from dataset.field import *

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
			"author":
			{
				"name": self.name,
				"first name": self.firstname,
				"last name": self.lastname,
				"address": self.address
			}
		}

class Authors(Field):

	name = "authors"
	aliases = ["author"]

	def __init__(self, value = None, alt_values = []):
		super().__init__(value, alt_values)
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
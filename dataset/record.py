import pandas as pd
import numpy as np
import os

from dataset.field import *
from dataset.fields.authors import *
from dataset.fields.doi import *
from dataset.fields.openalex_id import *
from dataset.fields.title import *

'''

The record class is for a single record, aka paper or book chapter.
It contains all possible fields the record can have, together with modifying functions.

'''
	

class Record:

	def __init__(self):
		self.fields = []
		dir_path = os.path.dirname(__file__) + "\\"
		data_format = pd.read_csv(dir_path + "format.csv")

		# Add fields
		self.fields.append(Doi())
		self.fields.append(OpenalexID())
		self.fields.append(Authors())
		self.fields.append(Title())

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
	
	def add_field(self, field):
		self.fields.append(field)

	def json_encode(self):

		return {
			"record": 
			{
				f.name: {"value": f.value, "alt": f.alt_values} for f in self.fields if not f.is_empty()
		}
		}
	
	@staticmethod
	def create_from_json(record_data):
		record = Record()
		for field in record_data:
			if field == "authors":
				for value in record_data[field]["value"]:
					record.add_value(field, value["author"]["name"])
			else:
				record.add_value(field, record_data[field]["value"])
				for alt in record_data[field]["alt"]:
					record.add_value(field, alt)
		return record


import pandas as pd

# The field class is a simple data object for field in the record
class Field:
	
	name = "empty field"
	aliases = []

	def __init__(self, value = None, alt_values = []):
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
		return { Field.name:
			{
			"value": self.value,
			"alternatives": self.alt_values
		}
		}
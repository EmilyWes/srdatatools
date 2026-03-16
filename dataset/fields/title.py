import pandas as pd
from dataset.field import *

class Title(Field):
		
	name = "title"
	aliases = ["primary_title"]

	def __init__(self, value = None, alt_values = []):
		super().__init__(value, alt_values)


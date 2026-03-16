import pandas as pd
from dataset.field import *

class OpenalexID(Field):
	
	name = "openalex_id"
	aliases = []

	def __init__(self, value = None, alt_values = []):
		super().__init__(value, alt_values)
		

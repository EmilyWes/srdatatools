import pandas as pd
from dataset.field import *

class Doi(Field):
	name = "doi"
	aliases = ["do"]

	def __init__(self, value = None, alt_values = []):
		super().__init__(value, alt_values)


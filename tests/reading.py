from dataset.dataset import *
from os import walk

def test_reading():
	files = [os.path.join(dirpath,f) for (dirpath, dirnames, filenames) in os.walk("tests\\data") for f in filenames] 
	
	for file in files:
		print(f"reading {file}")
		dataset = Dataset()
		dataset.get_data(file)

		file_split = file.split(".")
		output_path = "".join(file_split[:-1]) + "_out." + file_split[-1]
		dataset.write_data(output_path)


from dataset.record import *
from dataset.dataset import *
from os import walk

def test_dataset(): 
	my_rec = Record()
	my_rec.add_value("DOI", "10.15")
	my_rec.add_value("doi", ["10.a", "10.b"])
	my_rec.add_value("title", "woh wat een cool record")
	print(my_rec.get_row())

def test_reading():

	# cleanup old output files
	files = [os.path.join(dirpath,f) for (dirpath, dirnames, filenames) in os.walk("tests\\data") for f in filenames] 
	for file in files:
		if "out" in file:
			os.remove(file)

	# list of input files
	files = [os.path.join(dirpath,f) for (dirpath, dirnames, filenames) in os.walk("tests\\data") for f in filenames] 

	# read file + write to same format
	for file in files:
		print(f"reading {file}")
		dataset = Dataset()
		dataset.get_data(file)

		file_split = file.split(".")
		output_path = "".join(file_split[:-1]) + "_out." + file_split[-1]
		dataset.write_data(output_path)

def run_dataset_tests():
	test_dataset()
	test_reading()
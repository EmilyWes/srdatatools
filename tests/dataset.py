from dataset.record import *

def test_dataset(): 
	my_rec = Record()
	my_rec.add_value("DOI", "10.15")
	my_rec.add_value("doi", ["10.a", "10.b"])
	my_rec.add_value("title", "woh wat een cool record")
	print(my_rec.get_row())
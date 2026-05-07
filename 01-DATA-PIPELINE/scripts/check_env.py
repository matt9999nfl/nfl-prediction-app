import sys
print("Python:", sys.version)
import nfl_data_py
print("nfl_data_py: OK")
import pandas
print("pandas:", pandas.__version__)
from google.cloud import bigquery
print("google-cloud-bigquery: OK")
import pyarrow
print("pyarrow:", pyarrow.__version__)
print("ALL IMPORTS OK")

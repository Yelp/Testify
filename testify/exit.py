"""standardized exit codes for testify"""
import os

# 0 -- successful termination
OK = os.EX_OK

# 65 -- The input data was incorrect in some way.
DISCOVERY_FAILED = os.EX_DATAERR

# 70 -- An internal software error has been detected.
TESTS_FAILED = os.EX_SOFTWARE

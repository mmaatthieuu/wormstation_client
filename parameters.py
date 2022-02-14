import json
import os

class Parameters(dict):
    def __init__(self, filename="./config.json"):
        with open(filename) as f:
            data = json.load(f)

        super(Parameters, self).__init__(data)


    def save(self, file_path):
        pass
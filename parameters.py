import json
import os

class Parameters(dict):
    def __init__(self, filename="./config.json"):
        with open(filename) as f:
            data = json.load(f)

        super().__init__(data)
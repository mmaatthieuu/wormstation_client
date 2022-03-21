import json
import os

class Parameters(dict):
    def __init__(self, filename):
        try:
            with open(filename) as f:
                data = json.load(f)
                super(Parameters, self).__init__(data)
        except FileNotFoundError as e:
            print(e)


        # try:
        #     #data = json.dumps(filename)
        #     with open(filename) as f:
        #        data = json.load(f)
        # except FileNotFoundError as e:
        #     print("file not found but it's ok")
        #     #print(e)
        #     data = json.loads(filename)
        # except Exception as e:
        #     print("reyoups")
        #     print(e)





    def save(self, file_path):
        pass

import json

class Parameters(dict):
    def __init__(self, filename):
        """
        Initialize Parameters by loading from a JSON file.
        :param filename: Path to the JSON file.
        """
        try:
            with open(filename) as f:
                data = json.load(f)
                super(Parameters, self).__init__(data)
        except FileNotFoundError:
            raise FileNotFoundError(f"Error: The file '{filename}' does not exist.")
        except json.JSONDecodeError as e:
            raise ValueError(f"Error: The file '{filename}' contains invalid JSON. {e}")
        except Exception as e:
            raise Exception(f"Unexpected error while loading parameters: {e}")

    def save(self, file_path):
        """
        Save the parameters to a JSON file.
        :param file_path: Path to save the JSON file.
        """
        try:
            with open(file_path, 'w') as f:
                json.dump(self, f, indent=4)
            print(f"Parameters saved to {file_path}")
        except Exception as e:
            raise Exception(f"Error: Unable to save parameters to '{file_path}'. {e}")

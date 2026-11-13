import os

# transformers imports TensorFlow whenever it is installed, adding ~365 MB to every process
# that loads the embedding model. ChangAI only uses PyTorch, so keep TensorFlow out.
os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("TRANSFORMERS_NO_TF", "1")

__version__ = "0.0.1"

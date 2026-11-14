import torch
import numpy as np

print("Torch version:", torch.__version__)
print("NumPy version:", np.__version__)

if torch.cuda.is_available():
    print("\n✅ GPU is available!")
    print("Device Name:", torch.cuda.get_device_name(0))
    print("Total GPU Memory:", round(torch.cuda.get_device_properties(0).total_memory / 1e9, 2), "GB")
    print("Allocated Memory:", round(torch.cuda.memory_allocated(0) / 1e9, 2), "GB")
    print("Cached Memory:", round(torch.cuda.memory_reserved(0) / 1e9, 2), "GB")
else:
    print("\n❌ GPU not available. Using CPU.")

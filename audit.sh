#!/bin/bash
echo "=== PHASE 1: READ-ONLY AUDIT ==="
echo "uname -a"
uname -a
echo ""

echo "cat /etc/nv_tegra_release"
cat /etc/nv_tegra_release 2>/dev/null
echo ""

echo "cat /proc/device-tree/model"
cat /proc/device-tree/model 2>/dev/null
echo ""

echo "dpkg -l | grep -E 'nvidia-l4t-core|nvidia-jetpack|cuda|cudnn|tensorrt|nvinfer'"
dpkg -l | grep -E 'nvidia-l4t-core|nvidia-jetpack|cuda|cudnn|tensorrt|nvinfer'
echo ""

echo "nvcc --version"
/usr/local/cuda/bin/nvcc --version 2>/dev/null || nvcc --version 2>/dev/null
echo ""

echo "python3 --version"
python3 --version
echo ""

echo "python3 platform"
python3 -c "import platform; print(platform.machine())"
echo ""

echo "docker --version"
docker --version
echo ""

echo "docker compose version"
docker compose version 2>/dev/null || docker-compose --version 2>/dev/null
echo ""

echo "docker info"
docker info 2>/dev/null | grep -E 'Runtimes:|Name:|nvidia'
echo ""

echo "=== PHASE 2: HOST CUDA/TENSORRT AUDIT ==="
echo "ls -lah /usr/local/cuda"
ls -lah /usr/local/cuda
echo ""

echo "ldconfig -p | grep -E 'libcuda|libcudart|libcudnn|libnvinfer'"
ldconfig -p | grep -E 'libcuda|libcudart|libcudnn|libnvinfer'
echo ""

echo "find /usr -type f libnvinfer/tensorrt"
find /usr -type f \( -name 'libnvinfer*.so*' -o -name '_tensorrt*.so' -o -name 'tensorrt.py' \) 2>/dev/null
echo ""

echo "apt-cache search tensorrt"
apt-cache search tensorrt | grep -i python
echo ""

echo "apt-cache search python3.*nvinfer"
apt-cache search python3.*nvinfer
echo ""

echo "=== PHASE 3 & 4: NVIDIA CONTAINER AUDIT ==="
sudo docker run --rm --runtime=nvidia nvcr.io/nvidia/l4t-pytorch:r36.2.0-pth2.1-py3 sh -c '
echo "--- Python & PyTorch ---"
python3 --version
python3 -c "import torch; print(\"PyTorch:\", torch.__version__); print(\"CUDA Version:\", torch.version.cuda); print(\"CUDA Available:\", torch.cuda.is_available());"
if python3 -c "import torch; exit(0 if torch.cuda.is_available() else 1)"; then
  python3 -c "import torch; print(\"Device:\", torch.cuda.get_device_name(0))"
fi
echo "--- TensorRT ---"
python3 -c "import tensorrt as trt; print(\"TRT Version:\", trt.__version__ if hasattr(trt, \"__version__\") else \"No __version__\"); print(\"Logger:\", getattr(trt, \"Logger\", \"No Logger\")); print(\"Builder:\", getattr(trt, \"Builder\", \"No Builder\"));" 2>/dev/null || echo "TensorRT import failed"
echo "--- OpenCV ---"
python3 -c "import cv2; print(\"OpenCV:\", cv2.__version__);"
python3 -c "import cv2; print(cv2.getBuildInformation())" | grep -E "Video I/O|GStreamer|FFMPEG|v4l|NVIDIA CUDA" -A 2
'
echo "=== PHASE 7: MINIMAL TEST CHECK ==="
echo "which trtexec"
which trtexec
echo "find /usr/src/tensorrt/bin/trtexec"
ls -l /usr/src/tensorrt/bin/trtexec 2>/dev/null

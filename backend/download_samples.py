import os
import urllib.request

VIDEOS = {
    "face_recognition_test.mp4": "https://raw.githubusercontent.com/intel-iot-devkit/sample-videos/master/face-demographics-walking-and-pause.mp4",
    "people_walking_test.mp4": "https://raw.githubusercontent.com/intel-iot-devkit/sample-videos/master/people-detection.mp4"
}

os.makedirs("videos", exist_ok=True)

for name, url in VIDEOS.items():
    print(f"Downloading {name}...")
    try:
        urllib.request.urlretrieve(url, os.path.join("videos", name))
        print(f"Successfully downloaded {name}")
    except Exception as e:
        print(f"Failed to download {name}: {e}")

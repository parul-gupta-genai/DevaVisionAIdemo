import os
from PIL import Image

def process():
    public_dir = r"C:\Users\Praveen\Downloads\CVSOLUTION\DevaVisionAI\frontend\public"
    os.chdir(public_dir)
    
    # Open the new logo
    new_logo = Image.open("logo.png")
    
    # Process lc_logo.png
    if os.path.exists("lc_logo.png"):
        old_lc = Image.open("lc_logo.png")
        size_lc = old_lc.size
        old_lc.close()
        # Resize exactly to match the old dimensions
        resized_lc = new_logo.resize(size_lc, Image.Resampling.LANCZOS)
        resized_lc.save("lc_logo.png")
        print(f"Resized lc_logo.png to {size_lc}")
        
    # Create favicon.png (64x64 standard)
    favicon_size = (64, 64)
    resized_fav = new_logo.resize(favicon_size, Image.Resampling.LANCZOS)
    resized_fav.save("favicon.png")
    print(f"Created favicon.png {favicon_size}")

if __name__ == "__main__":
    process()

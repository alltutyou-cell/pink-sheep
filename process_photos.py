import os
import glob
import subprocess

def convert_heic_to_jpg(path):
    try:
        # verifying if sips exists
        subprocess.check_call(['which', 'sips'])
        
        new_path = os.path.splitext(path)[0] + ".jpg"
        print(f"Converting {path} to {new_path}...")
        subprocess.check_call(['sips', '-s', 'format', 'jpeg', path, '--out', new_path])
        os.remove(path)
        return new_path
    except Exception as e:
        print(f"Failed to convert {path}: {e}")
        return None

def main():
    folder = "photos"
    # Get all files
    files = []
    for ext in ["*.jpg", "*.JPG", "*.jpeg", "*.JPEG", "*.png", "*.PNG", "*.heic", "*.HEIC"]:
        files.extend(glob.glob(os.path.join(folder, ext)))
    
    # Sort files to keep consistent order if rerunning
    files.sort()
    
    # Process files
    valid_files = []
    for f in files:
        if f.lower().endswith(".heic"):
            new_f = convert_heic_to_jpg(f)
            if new_f:
                valid_files.append(new_f)
        else:
            valid_files.append(f)
            
    # Rename to clean sequence 1.jpg, 2.jpg, etc.
    print(f"Found {len(valid_files)} valid photos.")
    
    # First rename to a temporary pattern to avoid collisions
    for i, f in enumerate(valid_files):
        temp_name = os.path.join(folder, f"temp_rename_{i}.jpg")
        os.rename(f, temp_name)
        
    # Now rename to final sequence
    final_files = []
    for i in range(len(valid_files)):
        old_name = os.path.join(folder, f"temp_rename_{i}.jpg")
        new_name = os.path.join(folder, f"{i+1}.jpg")
        os.rename(old_name, new_name)
        final_files.append(new_name)
        
    print(f"Successfully processed {len(final_files)} photos.")
    
    # Update script.js with the new count
    try:
        with open("script.js", "r") as f:
            content = f.read()
            
        import re
        new_content = re.sub(r"const totalPhotos = \d+;", f"const totalPhotos = {len(final_files)};", content)
        
        with open("script.js", "w") as f:
            f.write(new_content)
        print("Updated script.js with new photo count.")
        
    except Exception as e:
        print(f"Error updating script.js: {e}")

if __name__ == "__main__":
    main()

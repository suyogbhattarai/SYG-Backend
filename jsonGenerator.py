import os
import hashlib
import json

def compute_file_hash(file_path):
    """Compute SHA256 hash of a file"""
    sha256 = hashlib.sha256()
    try:
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
    except Exception as e:
        print(f"Error hashing {file_path}: {e}")
        return ""

def generate_version_json(root_folder, project_name, commit_message="First version"):
    """
    Generate the JSON payload for version upload API
    
    Args:
        root_folder: Absolute path to project folder (e.g., C:/Users/acer/Documents/...)
        project_name: Name of the project
        commit_message: Commit message for this version
    
    Returns:
        Dictionary ready to be sent to the API
    """
    file_list = []
    
    # Walk through all files in the directory
    for root, dirs, files in os.walk(root_folder):
        for file in files:
            # Get full path
            full_path = os.path.join(root, file)
            
            # Get relative path (relative to root_folder)
            relative_path = os.path.relpath(full_path, root_folder)
            
            # Normalize path separators to forward slashes
            relative_path = relative_path.replace('\\', '/')
            
            # Compute hash
            file_hash = compute_file_hash(full_path)
            
            # Add to file list
            file_list.append({
                "relative_path": relative_path,
                "local_path": full_path,
                "hash": file_hash
            })
            
            print(f"Added: {relative_path} ({file_hash[:8]}...)")
    
    # Create the payload
    payload = {
        "project_name": project_name,
        "commit_message": commit_message,
        "file_list": file_list
    }
    
    return payload


# Example usage for your Project_1
if __name__ == "__main__":
    # Your project folder from the screenshot
    project_folder = r"C:\Users\acer\Documents\Image-Line\FL Studio\Projects\indie pop rock happy"
    
    # Generate the JSON
    payload = generate_version_json(
        root_folder=project_folder,
        project_name="tristan",
        commit_message="Initial version from FL Studio"
    )
    
    # Print statistics
    print(f"\n{'='*60}")
    print(f"Project: {payload['project_name']}")
    print(f"Total files: {len(payload['file_list'])}")
    print(f"{'='*60}\n")
    
    # Save to JSON file for Postman
    output_file = "version_upload_payload.json"
    with open(output_file, 'w') as f:
        json.dump(payload, f, indent=2)
    
    print(f"✓ Payload saved to: {output_file}")
    print(f"✓ Ready to import into Postman\n")
    
    # Print sample of first 3 files
    print("Sample file entries:")
    for i, file_entry in enumerate(payload['file_list'][:3], 1):
        print(f"\n{i}. {file_entry['relative_path']}")
        print(f"   Hash: {file_entry['hash'][:16]}...")
        print(f"   Path: {file_entry['local_path']}")
    
    if len(payload['file_list']) > 3:
        print(f"\n... and {len(payload['file_list']) - 3} more files")
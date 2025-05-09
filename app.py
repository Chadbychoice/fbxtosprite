import os
from flask import Flask, render_template, request, redirect, url_for, send_from_directory, jsonify
import subprocess
import uuid
import glob
from PIL import Image # Import Pillow for resizing
import shutil
import zipfile # Added for zipping frames
import time
from PIL import ImageFilter, ImageChops

app = Flask(__name__)
UPLOAD_FOLDER = 'uploads'
OUTPUT_FOLDER = 'output'
ALLOWED_EXTENSIONS = {'fbx'}
PREVIEW_FOLDER = os.path.join('output', 'previews')

# IMPORTANT: Configure Blender path if not in system PATH
# Examples:
# blender_executable = "blender" # Linux/macOS/Windows (if in PATH)
# blender_executable = "/usr/bin/blender" # Example Linux path
# blender_executable = "/Applications/Blender.app/Contents/MacOS/Blender" # Example macOS path
blender_executable = "C:/Program Files/Blender Foundation/Blender 4.3/blender.exe" # Use blender.exe, not launcher

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['OUTPUT_FOLDER'] = OUTPUT_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024 # Increased limit to 100 MB
app.config['PREVIEW_FOLDER'] = PREVIEW_FOLDER

# Ensure upload and output directories exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)
os.makedirs(PREVIEW_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def zip_output_directory(base_dir, output_zip_path, file_extension):
    """Recursively zips the contents of the base_dir matching the extension."""
    if not os.path.isdir(base_dir):
        print(f"Error: Base directory for zipping not found: {base_dir}")
        return False
    
    search_pattern = f"*.{file_extension.lower()}" # Ensure lowercase extension
    all_files_found = glob.glob(os.path.join(base_dir, '**', search_pattern), recursive=True)
    if not all_files_found:
        print(f"Error: No {search_pattern} files found recursively in {base_dir} to zip.")
        return False

    try:
        with zipfile.ZipFile(output_zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, _, files in os.walk(base_dir):
                for file in files:
                    if file.lower().endswith(f".{file_extension.lower()}"):
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, base_dir)
                        zipf.write(file_path, arcname=arcname)
            print(f"Successfully created zip file: {output_zip_path} from {base_dir}")
        return True
    except Exception as e:
        print(f"Error creating zip file: {e}")
        return False
    finally:
        # Cleanup happens in the main function after zipping
        pass 

# --- NEW Upscaling Function ---
def upscale_pixelated_frames(frame_folder_path, target_resolution=1024):
    """Finds PNGs/WebPs, upscales them using Nearest Neighbor, and overwrites them."""
    print(f"DEBUG: Upscaling frames in {frame_folder_path} to {target_resolution}x{target_resolution}...")
    found_frames = 0
    # Support both PNG and WebP for upscaling
    patterns_to_try = ['*.png', '*.webp']
    processed_files = set()
    
    for pattern in patterns_to_try:
        try:
            frame_files = glob.glob(os.path.join(frame_folder_path, pattern))
            if not frame_files:
                continue # Try next pattern
                
            for f_path in frame_files:
                if f_path in processed_files: continue # Avoid processing twice if somehow matched both
                try:
                    with Image.open(f_path) as img:
                        # Convert Paletted images (like some PNGs) to RGBA before resizing
                        if img.mode == 'P':
                            img = img.convert('RGBA')
                            print(f"DEBUG: Converted paletted image {os.path.basename(f_path)} to RGBA.")
                        # Use Image.Resampling.NEAREST for Pillow 9.1.0+
                        img_resized = img.resize((target_resolution, target_resolution), Image.Resampling.NEAREST)
                        # Save back to the original path, overwriting the low-res version
                        # Ensure quality for WebP if needed
                        save_kwargs = {}
                        if f_path.lower().endswith('.webp'):
                            save_kwargs['quality'] = 100 # Use high quality for potentially lossless
                            save_kwargs['lossless'] = True
                            
                        img_resized.save(f_path, **save_kwargs)
                        processed_files.add(f_path)
                        found_frames += 1
                except Exception as e_img:
                     print(f"Warning: Failed to upscale image {f_path}: {e_img}")
                     # Continue attempting other images
                     
        except Exception as e_glob:
             print(f"Error during frame upscaling glob/loop for {pattern}: {e_glob}")
             # Continue to next pattern
             
    print(f"DEBUG: Finished Upscaling. Processed {found_frames} frames in {frame_folder_path}.")
    return found_frames > 0 # Return True if at least one frame was processed
# --- End Upscaling Function ---

# --- Sprite Sheet Creation Function (Re-added and adapted) ---
def create_sprite_sheet(frame_folder, output_sheet_path, base_name, input_file_extension, output_sheet_format):
    """Creates a horizontal sprite sheet from individual frames, saving in the specified format."""
    frame_pattern = os.path.join(frame_folder, f"{base_name}_*.{input_file_extension.lower()}")
    print(f"DEBUG (create_sprite_sheet): Glob pattern: {frame_pattern}") # Added Debug
    frame_files = sorted(glob.glob(frame_pattern))
    print(f"DEBUG (create_sprite_sheet): Found files: {frame_files}") # Added Debug

    if not frame_files:
        print(f"ERROR (create_sprite_sheet): No frame files found matching pattern.") # Added ERROR
        return False

    images = [] 
    try:
        print(f"DEBUG (create_sprite_sheet): Loading {len(frame_files)} image files...") # Added Debug
        for idx, f in enumerate(frame_files):
            try:
                img = Image.open(f)
                images.append(img)
                # print(f"DEBUG (create_sprite_sheet): Loaded frame {idx+1}: {f}") # Can be too verbose
            except Exception as e_open:
                print(f"ERROR (create_sprite_sheet): Failed to open image file {f}: {e_open}") # Added ERROR
                # Close any already opened images before failing
                for opened_img in images: opened_img.close()
                return False # Fail if any image can't be opened
                
        if not images:
             print("ERROR (create_sprite_sheet): Image list is empty after loading attempts.") # Added ERROR
             return False

        # Assuming all frames have the same dimensions (after potential upscale)
        width, height = images[0].size
        total_width = width * len(images)

        sprite_sheet = Image.new('RGBA', (total_width, height))

        x_offset = 0
        for img in images:
            # Ensure image is RGBA for pasting with transparency
            img_rgba = img if img.mode == 'RGBA' else img.convert('RGBA')
            sprite_sheet.paste(img_rgba, (x_offset, 0), img_rgba) # Use alpha mask
            x_offset += width
            img.close() # Close the image file after pasting
        images = [] # Clear list

        # Save in the requested format
        save_kwargs = {}
        if output_sheet_format == 'WEBP':
            # Check for WebP dimension limits before attempting save
            MAX_WEBP_DIMENSION = 16383 
            if total_width > MAX_WEBP_DIMENSION or height > MAX_WEBP_DIMENSION:
                print(f"WARNING (create_sprite_sheet): Image dimensions ({total_width}x{height}) exceed WebP limit ({MAX_WEBP_DIMENSION}px). Falling back to saving as PNG.")
                # Fallback to PNG
                output_sheet_format = 'PNG'
                # No special kwargs needed for PNG save here
                save_kwargs = {}
                # Continue execution to save as PNG below
            else:
                # Proceed with saving as WebP if within limits
                save_kwargs['quality'] = 95 
                save_kwargs['lossless'] = False 
                print(f"DEBUG: Saving sprite sheet as WEBP")
        
        # If format is not WEBP (either originally or due to fallback), ensure it's set to PNG
        if output_sheet_format != 'WEBP':
             output_sheet_format = 'PNG' 
             print(f"DEBUG: Saving sprite sheet as PNG")
             # Ensure kwargs are empty for PNG
             save_kwargs = {}
             
        sprite_sheet.save(output_sheet_path, output_sheet_format, **save_kwargs)
        print(f"Sprite sheet saved to {output_sheet_path}")

        # Clean up individual frames after successful sprite sheet creation
        print(f"Cleaning up {len(frame_files)} source frame files from {frame_folder}...")
        for f in frame_files:
            try: os.remove(f)
            except OSError as e: print(f"Warning: Could not remove frame file {f}: {e}")
        return True

    except Exception as e:
        print(f"ERROR (create_sprite_sheet): Unexpected error during sheet creation for {base_name}: {e}") # Added ERROR
        # ... (cleanup logic similar to zip function) ...
        return False
    finally:
        for img in images: # Ensure cleanup
            try: img.close()
            except: pass

# --- Zipping Function (modified to zip specific files if needed) ---
def zip_output(items_to_zip, output_zip_path, base_arc_dir=None):
    """Zips a list of files or recursively zips a directory.
    If base_arc_dir is specified, archive names for files will be relative to it.
    """
    is_dir_mode = len(items_to_zip) == 1 and os.path.isdir(items_to_zip[0])
    
    if not items_to_zip:
        print("Error: No items provided to zip.")
        return False
    if is_dir_mode and not glob.glob(os.path.join(items_to_zip[0], '**', '*'), recursive=True):
         print(f"Error: Directory {items_to_zip[0]} is empty or contains no files to zip.")
         return False # Prevent empty zips from dirs
         
    try:
        print(f"Creating zip file: {output_zip_path}")
        with zipfile.ZipFile(output_zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            if is_dir_mode:
                base_dir = items_to_zip[0]
                print(f"Zipping directory recursively: {base_dir}")
                for root, _, files in os.walk(base_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, base_dir)
                        zipf.write(file_path, arcname=arcname)
            else: # List of files (sprite sheets)
                print(f"Zipping individual files: {items_to_zip}")
                for item_path in items_to_zip:
                     # Use only the filename as the name inside the zip archive
                     arcname = os.path.basename(item_path)
                     # Check the *original* full path exists before writing
                     if os.path.exists(item_path):
                         zipf.write(item_path, arcname=arcname) # Write full path, store as basename
                     else:
                         print(f"Warning: File not found for zipping: {item_path}")
        print(f"Successfully created zip file: {output_zip_path}")
        return True
    except Exception as e:
        print(f"Error creating zip file: {e}")
        return False

# --- Pillow Post-Processing: Add Thick Black Outline ---
def apply_post_outline_to_frames(frame_folder_path, thickness=10, overlap=8):
    """Adds a thick black outline to all PNGs and WebPs in the folder using Pillow.
    The outline will overlap the object by 'overlap' pixels."""
    print(f"DEBUG: Applying post-process outline to frames in {frame_folder_path} (thickness={thickness}, overlap={overlap})...")
    patterns_to_try = ['*.png', '*.webp']
    processed_files = set()
    for pattern in patterns_to_try:
        for f_path in glob.glob(os.path.join(frame_folder_path, pattern)):
            if f_path in processed_files: continue
            try:
                img = Image.open(f_path).convert('RGBA')
                alpha = img.split()[-1]
                mask = alpha.point(lambda p: 255 if p > 0 else 0, mode='1')
                outline_mask = mask.filter(ImageFilter.MaxFilter(thickness*2+1))
                eroded_mask = mask.filter(ImageFilter.MinFilter(overlap*2+1))
                outline_only = ImageChops.subtract(outline_mask.convert('L'), eroded_mask.convert('L'))
                outline_img = Image.new('RGBA', img.size, (0,0,0,0))
                outline_pixels = outline_only.point(lambda p: 255 if p > 0 else 0)
                outline_img.paste((0,0,0,255), mask=outline_pixels)
                out = Image.alpha_composite(outline_img, img)
                out.save(f_path)
                processed_files.add(f_path)
            except Exception as e:
                print(f"Warning: Failed to apply outline to {f_path}: {e}")
    print(f"DEBUG: Finished post-process outlining in {frame_folder_path}.")

@app.route('/')
def index():
    """Renders the main upload page."""
    return render_template('index.html')

@app.route('/preview', methods=['POST'])
def preview_render():
    """Handles generating a single frame preview."""
    print("--- DEBUG (/preview): Route hit ---") # Added Debug
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    if file and allowed_file(file.filename):
        # Get render style and other parameters
        render_style = request.form.get('render_style', 'bright')
        angle = request.form.get('custom_angle_value') # Get custom angle first
        if not angle or not request.form.get('custom_angle_enabled'):
             # Fallback: Use the first selected standard angle or 0 if none selected
             selected_angles = request.form.getlist('angles')
             angle = selected_angles[0] if selected_angles else '0'
        output_format = request.form.get('output_format', 'PNG')
        pixel_resolution = request.form.get('pixel_resolution', '128') # Get pixel res

        print(f"--- DEBUG (/preview): Received style='{render_style}', angle='{angle}', format='{output_format}', pixel_res='{pixel_resolution}'") # Added Debug

        # Use a unique ID for the preview to prevent conflicts
        preview_id = f"preview_{uuid.uuid4().hex[:8]}"
        fbx_filename = f"{preview_id}.fbx"
        fbx_path = os.path.join(app.config['UPLOAD_FOLDER'], fbx_filename)
        file.save(fbx_path)

        # Define output path for the single preview frame
        preview_output_name = f"{preview_id}_angle_{angle}" 
        # Use absolute path for preview directory to avoid ambiguity
        preview_output_dir = os.path.abspath(app.config['PREVIEW_FOLDER'])
        # Important: Ensure the preview output dir exists
        os.makedirs(preview_output_dir, exist_ok=True)

        # Construct command for Blender script (rendering frame 1)
        cmd_args = [
            blender_executable, 
            '--background', 
            '--python', 'scripts/process_fbx.py', '--',
            '--input', fbx_path,
            '--output_dir', preview_output_dir, # Pass absolute path
            '--output_name', preview_output_name, # Pass base name
            '--num_frames', '1', # Changed from --frames to --num_frames
            '--angle', str(angle),
            '--render_style', render_style,
            '--output_format', output_format, # Pass format
            '--pixel_resolution', pixel_resolution # Pass pixel res
        ]
        print(f"--- DEBUG (/preview): Running command: {cmd_args}") # Added Debug

        try:
            # Run Blender script
            result = subprocess.run(cmd_args, check=True, capture_output=True, text=True)
            print("--- DEBUG (/preview): Blender script STDOUT ---") # Added Debug
            print(result.stdout)
            print("--- DEBUG (/preview): Blender script STDERR ---") # Added Debug
            print(result.stderr)
            print(f"--- DEBUG (/preview): Blender script return code: {result.returncode}") # Added Debug
            
            # --- Add a small delay before checking files --- 
            time.sleep(1.0) # Increased delay to 1 second
            print("--- DEBUG (/preview): Delay finished. Proceeding with file check.")
            # -------------------------------------------
            
            # --- Perform Upscaling if Pixelated Style --- 
            if render_style in ['pixel_cel', 'pixel_outline', 'pixel_post_outline', 'pixel_post_thin_outline']:
                 print(f"--- DEBUG (/preview): Upscaling pixelated preview frame in {preview_output_dir}...")
                 upscale_pixelated_frames(preview_output_dir, 1024) # Upscale to 1024x1024
            # -------------------------------------------
            
            # --- Find the generated preview image (using the specific expected name) --- 
            # IMPORTANT: Blender script adds a frame index (_0000 for the first frame)
            expected_filename = f"{preview_output_name}_0000.{output_format.lower()}"
            output_frame_path = os.path.join(preview_output_dir, expected_filename)
            print(f"--- DEBUG (/preview): Looking for exact preview file (abs path): {output_frame_path}")
            
            # --- List directory contents before check (for debugging) --- 
            try:
                preview_dir_contents = os.listdir(preview_output_dir) # Use absolute path
                print(f"--- DEBUG (/preview): Contents of {preview_output_dir}: {preview_dir_contents}")
            except Exception as e_list:
                print(f"--- DEBUG (/preview): Error listing preview dir: {e_list}")
            # -------------------------------------------

            # Check if the specific file exists
            if os.path.exists(output_frame_path):
                # preview_file = output_frame_path # Variable not really needed
                preview_url = url_for('serve_preview', filename=os.path.basename(output_frame_path))
                # Clean up the uploaded FBX used only for preview
                try: os.remove(fbx_path); print(f"Cleaned up preview FBX: {fbx_path}")
                except OSError as e: print(f"Warning: Could not remove preview FBX {fbx_path}: {e}")
                return jsonify({'success': True, 'preview_url': preview_url})
            else:
                # --- Enhanced Debugging for File Not Found --- 
                debug_details = {
                    "message": "Flask could not find the expected preview file after Blender process.",
                    "expected_file_abs_path": output_frame_path,
                    "preview_dir_abs_path": preview_output_dir,
                    "listdir_of_preview_dir": [],
                    "glob_in_preview_dir": [],
                    "blender_stdout": result.stdout if 'result' in locals() and hasattr(result, 'stdout') else "N/A",
                    "blender_stderr": result.stderr if 'result' in locals() and hasattr(result, 'stderr') else "N/A (or Blender process did not complete)"
                }
                try:
                    debug_details["listdir_of_preview_dir"] = os.listdir(preview_output_dir)
                    debug_details["glob_in_preview_dir"] = glob.glob(os.path.join(preview_output_dir, "*"))
                except Exception as e_debug_fs:
                    debug_details["filesystem_debug_error"] = str(e_debug_fs)
                
                print(f"ERROR (/preview): Preview file not found. Debug details: {debug_details}")
                # ---------------------------------------------
                 # Clean up FBX even on failure
                try: os.remove(fbx_path); print(f"Cleaned up failed preview FBX: {fbx_path}")
                except OSError as e: print(f"Warning: Could not remove failed preview FBX {fbx_path}: {e}")
                return jsonify({'error': 'Preview generation failed (file not found by Flask)', 'details': debug_details}), 500

        except subprocess.CalledProcessError as e:
            print(f"ERROR (/preview): Blender script failed. Return code: {e.returncode}")
            print("--- DEBUG (/preview): Blender failure STDOUT ---")
            print(e.stdout)
            print("--- DEBUG (/preview): Blender failure STDERR ---")
            print(e.stderr)
            # Clean up FBX on failure
            try: os.remove(fbx_path); print(f"Cleaned up failed preview FBX: {fbx_path}")
            except OSError as e_rem: print(f"Warning: Could not remove failed preview FBX {fbx_path}: {e_rem}")
            return jsonify({'error': 'Blender processing failed', 'details': e.stderr}), 500
        except Exception as e:
             print(f"ERROR (/preview): Unexpected error during preview: {e}")
             # Clean up FBX on failure
             try: os.remove(fbx_path); print(f"Cleaned up failed preview FBX: {fbx_path}")
             except OSError as e_rem: print(f"Warning: Could not remove failed preview FBX {fbx_path}: {e_rem}")
             return jsonify({'error': 'Unexpected server error during preview', 'details': str(e)}), 500

    return jsonify({'error': 'Invalid file type'}), 400

@app.route('/output/previews/<filename>')
def serve_preview(filename):
    # Basic security check
    if '..' in filename or filename.startswith('/'):
        return "Invalid filename", 400

    # Use absolute path to ensure correct serving directory
    preview_dir_abs = os.path.abspath(app.config["PREVIEW_FOLDER"])
    
    # --- Add Logging --- 
    file_path_to_serve = os.path.join(preview_dir_abs, filename)
    print(f"--- DEBUG (serve_preview): Attempting to serve file: {file_path_to_serve}")
    print(f"--- DEBUG (serve_preview): File exists check: {os.path.exists(file_path_to_serve)}")
    # -----------------
    
    return send_from_directory(preview_dir_abs, filename)

@app.route('/upload', methods=['POST'])
def upload_file():
    """Handles file upload, triggers Blender processing for angles/styles, and zips frames."""
    if 'file' not in request.files:
        return redirect(request.url)
    file = request.files['file']
    if file.filename == '' or not allowed_file(file.filename):
        return 'Invalid or missing file.', 400

    # --- Get Form Data --- 
    try:
        # Check Auto Angles Mode
        auto_angles_mode = request.form.get('auto_angles_mode', 'off') # default to 'off'
        print(f"DEBUG: Auto Angles Mode = {auto_angles_mode}")

        if auto_angles_mode != 'off':
            num_angles_map = {'16': 16, '32': 32, '64': 64}
            num_auto_angles = num_angles_map.get(auto_angles_mode)
            if not num_auto_angles:
                print(f"Warning: Invalid auto_angles_mode '{auto_angles_mode}'. Defaulting to 16.")
                num_auto_angles = 16
                auto_angles_mode = '16' # Correct the mode if invalid
                
            angle_step = 360.0 / num_auto_angles
            angles_to_process = [i * angle_step for i in range(num_auto_angles)]
            num_frames = 1 # Override num_frames for auto-angles
            print(f"DEBUG: Using Auto Angles Mode '{auto_angles_mode}' ({num_auto_angles} angles). Frames set to {num_frames}")
        else:
            # Manual Mode: Get angles from checkboxes/custom input
            selected_angles = set()
            standard_angles = request.form.getlist('angles')
            for angle_str in standard_angles: selected_angles.add(float(angle_str)) 
            if request.form.get('custom_angle_enabled') == 'true':
                custom_angle_str = request.form.get('custom_angle_value')
                if custom_angle_str: 
                    custom_angle = float(custom_angle_str)
                    selected_angles.add(max(0.0, min(custom_angle, 360.0)))
            if not selected_angles:
                 return "No angles selected for processing.", 400
            angles_to_process = sorted(list(selected_angles))
            
            # Get Num Frames only if auto-angles is off
            num_frames = int(request.form.get('num_frames', 16))
            num_frames = max(1, min(num_frames, 100))

        # Get Render Style and Pixel Resolution
        render_style = request.form.get('render_style', 'bright')
        valid_styles = ['bright', 'cel', 'unlit', 'original_unlit', 'wireframe', 'clay', 'pixel_cel', 'cel_outline', 'cel_thicker_outline', 'pixel_outline', 'pixel_post_outline', 'pixel_post_thin_outline']
        if render_style not in valid_styles: render_style = 'bright'
        pixel_resolution = None
        if render_style in ['pixel_cel', 'pixel_outline', 'pixel_post_outline', 'pixel_post_thin_outline']:
            pixel_resolution = int(request.form.get('pixel_resolution', 128))
            pixel_resolution = max(16, min(pixel_resolution, 256))
            print(f"DEBUG (Process): Pixelation resolution requested: {pixel_resolution}")

        # --- Get Output Format --- 
        output_format = request.form.get('output_format', 'PNG').upper()
        if output_format not in ['PNG', 'WEBP']: output_format = 'PNG'
        output_file_extension = output_format.lower()
        # --- End Get Output Format ---

        # --- Get Output Type --- 
        output_type = request.form.get('output_type', 'zip') # Default to zip
        if output_type not in ['zip', 'sheet']: output_type = 'zip'
        # --- End Get Output Type ---

    except ValueError:
        return "Invalid angle, frame count, or pixel resolution format.", 400
    # --- End Get Form Data --- 

    if file and allowed_file(file.filename):
        unique_id = str(uuid.uuid4())
        input_filename = f"{unique_id}.fbx"
        input_path = os.path.join(app.config['UPLOAD_FOLDER'], input_filename)
        # Base directory for all temporary frames for this request
        base_temp_dir = os.path.join(app.config['OUTPUT_FOLDER'], f"frames_{unique_id}")
        final_output_dir = app.config['OUTPUT_FOLDER']
        final_zip_filename = f"{unique_id}_{render_style}_{output_format}_{output_type}.zip"
        final_zip_path = os.path.join(final_output_dir, final_zip_filename)

        os.makedirs(base_temp_dir, exist_ok=True)
        blender_errors = [] # Store errors from Blender runs

        try:
            file.save(input_path)
            print(f"File saved to {input_path}")
            abs_input_path = os.path.abspath(input_path)
            script_path = os.path.join("scripts", "process_fbx.py")

            # --- Loop through angles and call Blender ---
            print(f"Processing with Output: {output_type}, Style: {render_style}, Format: {output_format}, Angles: {angles_to_process}")
            use_flat_structure = (auto_angles_mode != 'off')
            
            for angle in angles_to_process:
                print(f"--- Processing Angle: {angle} --- ")
                angle_str_safe = f"{angle:.1f}".replace('.', '_') # Format angle for filename
                
                if use_flat_structure:
                    # Save directly into base_temp_dir, angle in filename
                    angle_output_dir = base_temp_dir
                    # Format filename to include angle with one decimal place
                    angle_output_name = f"{unique_id}_angle_{angle_str_safe}" 
                else:
                    # Use angle-specific subdirectories (Manual mode)
                    angle_output_dir = os.path.join(base_temp_dir, f"angle_{angle_str_safe}")
                    angle_output_name = f"{unique_id}_angle_{angle_str_safe}"
                    os.makedirs(angle_output_dir, exist_ok=True)
                    
                abs_angle_output_dir = os.path.abspath(angle_output_dir)
                
                command = [
                    blender_executable,
                    "--background",
                    "--python", script_path,
                    "--", 
                    "--input", abs_input_path,
                    "--output_dir", abs_angle_output_dir, 
                    "--output_name", angle_output_name,
                    "--num_frames", str(num_frames),
                    "--angle", str(angle),
                    "--render_style", render_style,
                    "--output_format", output_format
                ]
                if pixel_resolution is not None and render_style in ['pixel_cel', 'pixel_outline', 'pixel_post_outline', 'pixel_post_thin_outline']:
                     command.extend(["--pixel_resolution", str(pixel_resolution)])
                
                try:
                    print(f"Running Blender command: {' '.join(command)}")
                    process = subprocess.run(command, check=True, capture_output=True, text=True, timeout=300)
                    print(f"Blender STDOUT (Angle {angle}):\n{process.stdout}")
                    if process.stderr:
                        print(f"Blender STDERR (Angle {angle}):\n{process.stderr}")
                except subprocess.CalledProcessError as e:
                    error_msg = f"ERROR: Blender process failed for angle {angle} (Exit code {e.returncode}). STDERR: {e.stderr[:500]}..."
                    print(error_msg)
                    print(f"Blender STDOUT (Angle {angle}):\n{e.stdout}") # Show stdout on error too
                    blender_errors.append(error_msg)
                    # Continue to next angle even if one fails?
                    # Or break here: break 
                except FileNotFoundError:
                     error_msg = f"ERROR: Blender executable not found at '{blender_executable}'. Halting processing."
                     print(error_msg)
                     blender_errors.append(error_msg)
                     break # Stop processing if Blender isn't found
                except subprocess.TimeoutExpired as e:
                     error_msg = f"ERROR: Blender process timed out for angle {angle} after {e.timeout} seconds."
                     print(error_msg)
                     if e.stdout: print(f"Blender STDOUT (partial, Angle {angle}):\n{e.stdout}")
                     if e.stderr: print(f"Blender STDERR (partial, Angle {angle}):\n{e.stderr}")
                     blender_errors.append(error_msg)
                     # Continue or break?
            # --- End Loop ---

            # Proceed only if Blender was found and at least some angles might have succeeded
            if "Blender executable not found" in ''.join(blender_errors):
                 return "Processing failed: Blender not found.", 500

            # --- Post-Processing (Upscale / Create Sheets / Zip) --- 
            zip_created = False
            items_to_finally_zip = []
            base_dir_for_zip_arc = None
            
            if output_type == 'sheet':
                print(f"DEBUG: Creating sprite sheets from {base_temp_dir}...")
                created_sheets = []
                use_flat_structure = (auto_angles_mode != 'off')
                
                if use_flat_structure:
                    # Create ONE sheet from all frames in the flat base directory
                    sheet_output_path = os.path.join(final_output_dir, f"{unique_id}_{auto_angles_mode}angles.{output_file_extension}")
                    base_name_for_glob = f"{unique_id}_angle_*" # Glob pattern for frames
                    
                    # Upscale first if needed (operate on base_temp_dir)
                    if render_style in ['pixel_cel', 'pixel_outline', 'pixel_post_outline', 'pixel_post_thin_outline']:
                         print(f"DEBUG: Upscaling frames in {base_temp_dir} before sheet creation...")
                         upscale_pixelated_frames(base_temp_dir, 1024)
                         
                    sheet_success = create_sprite_sheet(base_temp_dir, sheet_output_path, base_name_for_glob, output_file_extension, output_format)
                    if sheet_success:
                        created_sheets.append(sheet_output_path)
                    else:
                         blender_errors.append("Failed to create single sprite sheet for auto-angles.")
                         
                else: # Not auto_angles (Manual mode) - process angle by angle
                    angle_dirs = sorted(glob.glob(os.path.join(base_temp_dir, 'angle_*'))) 
                    if not angle_dirs:
                         blender_errors.append("No angle directories found after rendering.")
                    else:
                        for angle_dir in angle_dirs:
                            angle_name = os.path.basename(angle_dir) # e.g., "angle_45_0"
                            angle_output_name = f"{unique_id}_{angle_name}" 
                            sheet_output_path = os.path.join(final_output_dir, f"{angle_output_name}.{output_file_extension}") 
                            
                            # Upscale first if needed
                            if render_style in ['pixel_cel', 'pixel_outline', 'pixel_post_outline', 'pixel_post_thin_outline']:
                                 print(f"DEBUG: Upscaling frames in {angle_dir} before sheet creation...")
                                 upscale_pixelated_frames(angle_dir, 1024)
                                 
                            # Pass input extension AND desired output format
                            sheet_success = create_sprite_sheet(angle_dir, sheet_output_path, angle_output_name, output_file_extension, output_format)
                            if sheet_success:
                                created_sheets.append(sheet_output_path)
                            else:
                                 blender_errors.append(f"Failed to create sprite sheet for {angle_name}.")
                
                if created_sheets:
                    items_to_finally_zip = created_sheets
                    # Zip individual sheets directly into the root of the zip
                    base_dir_for_zip_arc = None 
                    print(f"DEBUG: Zipping created sprite sheets: {created_sheets}")
                    zip_created = zip_output(items_to_finally_zip, final_zip_path, base_dir_for_zip_arc)
                else:
                    print("Error: No sprite sheets were successfully created.")
                    # zip_created remains False
                    
            else: # output_type == 'zip' (individual frames)
                # Upscale first if needed
                use_flat_structure = (auto_angles_mode != 'off')
                if render_style in ['pixel_cel', 'pixel_outline', 'pixel_post_outline', 'pixel_post_thin_outline']:
                    print(f"DEBUG: Starting post-render upscaling (Style: {render_style})")
                    if use_flat_structure:
                        # Upscale directly in base_temp_dir
                        upscale_pixelated_frames(base_temp_dir, 1024)
                        if render_style == 'pixel_post_outline':
                            apply_post_outline_to_frames(base_temp_dir, thickness=10, overlap=8)
                        elif render_style == 'pixel_post_thin_outline':
                            apply_post_outline_to_frames(base_temp_dir, thickness=4, overlap=8)
                    else:
                        # Upscale in each angle subdirectory
                        angle_dirs = glob.glob(os.path.join(base_temp_dir, 'angle_*'))
                        for angle_dir in angle_dirs:
                            upscale_pixelated_frames(angle_dir, 1024)
                            if render_style == 'pixel_post_outline':
                                apply_post_outline_to_frames(angle_dir, thickness=10, overlap=8)
                            elif render_style == 'pixel_post_thin_outline':
                                apply_post_outline_to_frames(angle_dir, thickness=4, overlap=8)
                    print("DEBUG: Finished post-render upscaling.")
                    
                # Zip the frames
                items_to_finally_zip = [base_temp_dir]
                # Base dir for zip is None, so it zips contents directly
                print(f"DEBUG: Zipping individual frames directory: {base_temp_dir}")
                zip_created = zip_output(items_to_finally_zip, final_zip_path)
            # --- End Post-Processing ---

            # --- Final Response Handling --- 
            if zip_created and os.path.exists(final_zip_path):
                 final_message = f"Processing complete. Redirecting to download {final_zip_filename}."
                 if blender_errors:
                     final_message += " Note: Some angles may have encountered errors (check server logs)."
                 print(final_message)
                 return redirect(url_for('download_file', filename=final_zip_filename))
            else:
                error_summary = "Processing failed (Zipping step or no frames rendered)." 
                if blender_errors:
                    error_summary += f" Blender errors encountered: {'; '.join(blender_errors)}"
                print(error_summary)
                return error_summary, 500

        except Exception as e:
            # Catch other potential errors during file save or setup
            print(f"ERROR: An unexpected outer error occurred: {e}")
            import traceback
            traceback.print_exc()
            # Ensure cleanup is attempted even for outer errors
            blender_errors.append(f"Outer error: {e}") 
            return f"An unexpected error occurred during setup or processing. Check server logs. Errors: {'; '.join(blender_errors)}", 500
        finally:
            # --- Cleanup ---
            if os.path.exists(input_path):
                try: os.remove(input_path); print(f"Cleaned up input file: {input_path}")
                except OSError as e_rem: print(f"Warning: Could not remove input file {input_path}: {e_rem}")
            # Remove the base temp directory containing all angle subdirs
            if os.path.exists(base_temp_dir):
                try: shutil.rmtree(base_temp_dir); print(f"Cleaned up temporary frame directory: {base_temp_dir}")
                except OSError as e_rem: print(f"Warning: Could not remove temporary frame directory {base_temp_dir}: {e_rem}")
            # Cleanup individual sheets if they were created outside temp dir
            if output_type == 'sheet' and items_to_finally_zip:
                 print(f"Cleaning up individual sprite sheets...")
                 for sheet_path in items_to_finally_zip:
                     if os.path.exists(sheet_path):
                         try: os.remove(sheet_path)
                         except OSError as e: print(f"Warning: Failed to remove sheet {sheet_path}: {e}")

    else:
        return 'Invalid file type.', 400

@app.route('/output/<filename>')
def download_file(filename):
    """Serves the generated zip file for download."""
    allowed_extensions = ('.zip', '.png', '.webp')
    if '..' in filename or filename.startswith('/') or not filename.lower().endswith(allowed_extensions):
         return "Invalid filename or file type for download.", 400
    # Determine mimetype based on extension
    mimetype = 'application/octet-stream' # Default
    if filename.lower().endswith('.zip'): mimetype = 'application/zip'
    elif filename.lower().endswith('.png'): mimetype = 'image/png'
    elif filename.lower().endswith('.webp'): mimetype = 'image/webp'
    
    # Determine correct directory based on filename (preview or main output)
    serve_dir = app.config["OUTPUT_FOLDER"]
    if filename.startswith("preview_"):
        serve_dir = app.config["PREVIEW_FOLDER"]
        
    return send_from_directory(serve_dir, filename, as_attachment=True, mimetype=mimetype)

if __name__ == '__main__':
    # Make sure Blender path is configured above before running!
    print(f"Using Blender executable: {blender_executable}")
    if not os.path.exists(blender_executable) and blender_executable == "blender":
         print("Warning: 'blender' command used, ensure it's in your system's PATH.")
    elif not os.path.exists(blender_executable):
         print(f"ERROR: Blender executable not found at specified path: {blender_executable}")
         print("Please install Blender and/or configure the correct path in app.py")
         # sys.exit(1) # Optionally exit if Blender isn't configured

    app.run(debug=True, port=5001) # debug=True for development (auto-reloads), set to False for production 
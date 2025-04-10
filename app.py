import os
from flask import Flask, render_template, request, redirect, url_for, send_from_directory, jsonify
import subprocess
import uuid
import glob
from PIL import Image # Import Pillow for resizing
import shutil
import zipfile # Added for zipping frames

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

def zip_output_directory(base_dir, output_zip_path):
    """Recursively zips the contents of the base_dir."""
    if not os.path.isdir(base_dir):
        print(f"Error: Base directory for zipping not found: {base_dir}")
        return False
    
    all_files_found = glob.glob(os.path.join(base_dir, '**', '*.png'), recursive=True)
    if not all_files_found:
        print(f"Error: No PNG files found recursively in {base_dir} to zip.")
        return False

    try:
        with zipfile.ZipFile(output_zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, _, files in os.walk(base_dir):
                for file in files:
                    if file.endswith('.png'):
                        file_path = os.path.join(root, file)
                        # arcname determines the path inside the zip file
                        # Make it relative to the base_dir
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
    """Finds PNGs, upscales them using Nearest Neighbor, and overwrites them."""
    print(f"DEBUG: Upscaling frames in {frame_folder_path} to {target_resolution}x{target_resolution}...")
    found_frames = 0
    try:
        frame_files = glob.glob(os.path.join(frame_folder_path, '*.png'))
        if not frame_files:
            print("Warning: No frames found in folder for upscaling.")
            return False
            
        for f_path in frame_files:
            try:
                with Image.open(f_path) as img:
                    # Use Image.Resampling.NEAREST for Pillow 9.1.0+
                    # For older Pillow, use Image.NEAREST
                    img_resized = img.resize((target_resolution, target_resolution), Image.Resampling.NEAREST)
                    # Save back to the original path, overwriting the low-res version
                    img_resized.save(f_path, 'PNG')
                    found_frames += 1
            except Exception as e_img:
                 print(f"Warning: Failed to upscale image {f_path}: {e_img}")
                 # Continue attempting other images
                 
        print(f"DEBUG: Upscaled {found_frames} frames.")
        return found_frames > 0 # Return True if at least one frame was processed
        
    except Exception as e_glob:
         print(f"Error during frame upscaling process: {e_glob}")
         return False
# --- End Upscaling Function ---

@app.route('/')
def index():
    """Renders the main upload page."""
    return render_template('index.html')

@app.route('/preview', methods=['POST'])
def generate_preview():
    """Generates a single frame preview based on form data."""
    if 'file' not in request.files:
        return jsonify({"success": False, "error": "No file part"}), 400
    file = request.files['file']
    if file.filename == '' or not allowed_file(file.filename):
        return jsonify({"success": False, "error": "Invalid file"}), 400

    # --- Get Style, Angle, and Pixel Resolution for Preview ---
    try:
        render_style = request.form.get('render_style', 'bright')
        valid_styles = ['bright', 'cel', 'unlit', 'original_unlit', 'wireframe', 'clay', 'pixel_cel']
        if render_style not in valid_styles: render_style = 'bright'
        
        preview_angle = float(request.form.get('preview_angle', 0.0))
        preview_angle = max(0.0, min(preview_angle, 360.0)) # Clamp

        pixel_resolution = None
        if render_style == 'pixel_cel':
            pixel_resolution = int(request.form.get('pixel_resolution', 128))
            pixel_resolution = max(16, min(pixel_resolution, 256)) # Clamp resolution
            print(f"DEBUG (Preview): Pixelation resolution requested: {pixel_resolution}")

    except ValueError:
         return jsonify({"success": False, "error": "Invalid style, angle, or resolution format"}), 400
    # --- End Get Preview Params ---

    # --- Temporary Save & Process ---
    preview_id = str(uuid.uuid4())
    temp_fbx_filename = f"preview_{preview_id}.fbx"
    temp_fbx_path = os.path.join(app.config['UPLOAD_FOLDER'], temp_fbx_filename) # Use upload folder temporarily
    
    preview_output_filename_base = f"preview_{preview_id}"
    preview_output_dir = os.path.join(app.config['PREVIEW_FOLDER'], f"temp_{preview_id}") # Temp dir for the single frame
    os.makedirs(preview_output_dir, exist_ok=True)

    final_preview_image_name = f"{preview_output_filename_base}_0000.png" # Blender script outputs _0000 for first frame
    final_preview_image_path = os.path.join(app.config['PREVIEW_FOLDER'], final_preview_image_name)
    
    abs_preview_output_dir = os.path.abspath(preview_output_dir)
    abs_temp_fbx_path = os.path.abspath(temp_fbx_path)
    script_path = os.path.join("scripts", "process_fbx.py")

    try:
        file.save(temp_fbx_path)
        print(f"Preview: Saved temp file {temp_fbx_path}")

        command = [
            blender_executable,
            "--background", "--python", script_path, "--",
            "--input", abs_temp_fbx_path,
            "--output_dir", abs_preview_output_dir,
            "--output_name", preview_output_filename_base,
            "--num_frames", "1",
            "--angle", str(preview_angle),
            "--render_style", render_style
        ]
        # Conditionally add pixel resolution argument
        if pixel_resolution is not None:
            command.extend(["--pixel_resolution", str(pixel_resolution)])
        
        print(f"Preview: Running Blender command: {' '.join(command)}")
        # Use a shorter timeout for previews?
        process = subprocess.run(command, check=True, capture_output=True, text=True, timeout=120) 
        print(f"Preview STDOUT:\n{process.stdout}")
        if process.stderr: print(f"Preview STDERR:\n{process.stderr}")

        # --- Upscale if Pixelated ---
        if render_style == 'pixel_cel':
            upscale_success = upscale_pixelated_frames(preview_output_dir, 1024)
            if not upscale_success:
                 print("Warning: Upscaling step failed or found no frames.")
                 # Proceed anyway, might show low-res or fail on file check

        # Check if the expected output frame exists
        rendered_frame_path = os.path.join(preview_output_dir, final_preview_image_name)
        if os.path.exists(rendered_frame_path):
            # Move the single frame to the main preview folder
            shutil.move(rendered_frame_path, final_preview_image_path)
            print(f"Preview: Output frame moved to {final_preview_image_path}")
            # Generate URL path for the preview image
            preview_url = url_for('serve_preview', filename=final_preview_image_name)
            return jsonify({"success": True, "preview_url": preview_url})
        else:
            raise FileNotFoundError(f"Preview output frame not found at {rendered_frame_path}")

    except subprocess.CalledProcessError as e:
        print(f"ERROR (Preview): Blender failed (Code {e.returncode}): {e.stderr[:500]}")
        return jsonify({"success": False, "error": f"Blender processing failed: {e.stderr[:100]}..."}), 500
    except FileNotFoundError as e:
        print(f"ERROR (Preview): File not found: {e}")
        return jsonify({"success": False, "error": "Preview generation failed (file missing)."}), 500
    except Exception as e:
        print(f"ERROR (Preview): Unexpected error: {e}")
        import traceback; traceback.print_exc()
        return jsonify({"success": False, "error": "An unexpected error occurred during preview."}), 500
    finally:
        # --- Cleanup Preview Files ---
        if os.path.exists(temp_fbx_path):
            try: os.remove(temp_fbx_path); print(f"Preview: Cleaned up {temp_fbx_path}")
            except OSError as e: print(f"Warning (Preview): Failed to remove {temp_fbx_path}: {e}")
        if os.path.exists(preview_output_dir):
             try: shutil.rmtree(preview_output_dir); print(f"Preview: Cleaned up {preview_output_dir}")
             except OSError as e: print(f"Warning (Preview): Failed to remove {preview_output_dir}: {e}")

@app.route('/output/previews/<filename>')
def serve_preview(filename):
    # Basic security check
    if '..' in filename or filename.startswith('/'):
        return "Invalid filename", 400
    return send_from_directory(app.config["PREVIEW_FOLDER"], filename)

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
        # Check for Auto Angles first
        auto_angles_enabled = request.form.get('auto_angles') == 'true'
        print(f"DEBUG: Auto Angles Enabled = {auto_angles_enabled}")

        if auto_angles_enabled:
            angles_to_process = [0.0, 45.0, 90.0, 135.0, 180.0, 225.0, 270.0, 315.0]
            num_frames = 1 # Override num_frames for auto-angles
            print(f"DEBUG: Using Auto Angles. Frames set to {num_frames}")
        else:
            # Get angles from checkboxes/custom input
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

        # Get Render Style and Pixel Resolution (applies regardless of auto-angles)
        render_style = request.form.get('render_style', 'bright')
        valid_styles = ['bright', 'cel', 'unlit', 'original_unlit', 'wireframe', 'clay', 'pixel_cel']
        if render_style not in valid_styles: render_style = 'bright'

        pixel_resolution = None
        if render_style == 'pixel_cel':
            pixel_resolution = int(request.form.get('pixel_resolution', 128))
            pixel_resolution = max(16, min(pixel_resolution, 256))
            print(f"DEBUG (Process): Pixelation resolution requested: {pixel_resolution}")

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
        final_zip_filename = f"{unique_id}_{render_style}_angles.zip"
        final_zip_path = os.path.join(final_output_dir, final_zip_filename)

        os.makedirs(base_temp_dir, exist_ok=True)
        blender_errors = [] # Store errors from Blender runs

        try:
            file.save(input_path)
            print(f"File saved to {input_path}")
            abs_input_path = os.path.abspath(input_path)
            script_path = os.path.join("scripts", "process_fbx.py")

            # --- Loop through angles and call Blender ---
            print(f"Processing with Style: {render_style}, Angles: {angles_to_process}, Frames: {num_frames}")
            for angle in angles_to_process:
                print(f"--- Processing Angle: {angle} --- ")
                # Create angle-specific output directory and name
                angle_str_safe = str(angle).replace('.', '_') # Make safe for dir/file names
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
                    "--render_style", render_style
                ]
                if pixel_resolution is not None:
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

            # --- Upscale ALL frames if Pixelated ---
            if render_style == 'pixel_cel':
                print(f"DEBUG: Starting post-render upscaling for all angles in {base_temp_dir}")
                # Loop through angle subdirectories and upscale frames within each
                angle_dirs = glob.glob(os.path.join(base_temp_dir, 'angle_*'))
                total_upscaled = 0
                for angle_dir in angle_dirs:
                    print(f"DEBUG: Upscaling frames in angle directory: {angle_dir}")
                    upscale_success = upscale_pixelated_frames(angle_dir, 1024)
                    if upscale_success:
                         # Count files, maybe? For now just log success per dir
                         pass 
                print("DEBUG: Finished post-render upscaling.")

            # --- Zip ALL Rendered Frames --- 
            print(f"Attempting to zip contents of {base_temp_dir}")
            zip_created = zip_output_directory(base_temp_dir, final_zip_path)

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

    else:
        return 'Invalid file type.', 400

@app.route('/output/<filename>')
def download_file(filename):
    """Serves the generated zip file for download."""
    if '..' in filename or filename.startswith('/') or not filename.lower().endswith('.zip'):
        return "Invalid filename or file type for download.", 400
    # Add appropriate MIME type for zip files
    return send_from_directory(app.config["OUTPUT_FOLDER"], filename, as_attachment=True, mimetype='application/zip')

if __name__ == '__main__':
    # Make sure Blender path is configured above before running!
    print(f"Using Blender executable: {blender_executable}")
    if not os.path.exists(blender_executable) and blender_executable == "blender":
         print("Warning: 'blender' command used, ensure it's in your system's PATH.")
    elif not os.path.exists(blender_executable):
         print(f"ERROR: Blender executable not found at specified path: {blender_executable}")
         print("Please install Blender and/or configure the correct path in app.py")
         # sys.exit(1) # Optionally exit if Blender isn't configured

    app.run(debug=True) # debug=True for development (auto-reloads), set to False for production 
# FBX to Sprite Sheet Converter

A Flask web application to convert FBX files (including animations) into sprite sheets or individual frames, with various styling options powered by Blender.

## Features

*   Upload FBX files.
*   Render animations or static models from multiple angles.
*   Choose from various render styles (e.g., Cel Shaded, Pixelated, Wireframe, Outline styles).
*   Output as individual frames (zipped) or combined sprite sheets (PNG per angle).
*   Adjust number of frames per angle for animations.
*   Automatic angle generation (16, 32, 64 angles) for stationary models.
*   Live preview for a selected angle and style before full processing.
*   Configurable output image format (PNG, WebP).
*   Pixelation with adjustable block size.
*   Post-processing options like outlines applied after pixelation.

## Prerequisites

*   **Python 3.7+**: Make sure Python 3 is installed and added to your system's PATH.
*   **Blender**: Version 4.0 or newer is recommended (specifically, the script uses Eevee Next which is default in Blender 4.1+). Download from [blender.org](https://www.blender.org/download/).

## Setup Instructions

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/Chadbychoice/fbxtosprite.git
    cd fbxtosprite
    ```

2.  **Create and activate a Python virtual environment:**
    *   On Windows:
        ```bash
        python -m venv venv
        .\venv\Scripts\activate
        ```
    *   On macOS/Linux:
        ```bash
        python3 -m venv venv
        source venv/bin/activate
        ```

3.  **Install dependencies:**
    The primary dependencies are Flask (for the web server) and Pillow (for image manipulation like upscaling and sprite sheet generation).
    ```bash
    pip install Flask Pillow
    ```

4.  **Configure Blender Executable Path:**
    Open the `app.py` file in a text editor. Near the top, you'll find a line:
    ```python
    # blender_executable = "blender" # Linux/macOS/Windows (if in PATH)
    # blender_executable = "/usr/bin/blender" # Example Linux path
    # blender_executable = "/Applications/Blender.app/Contents/MacOS/Blender" # Example macOS path
    blender_executable = "C:/Program Files/Blender Foundation/Blender 4.3/blender.exe" # Example Windows path
    ```
    Uncomment the line appropriate for your operating system and **ensure the path points to your Blender executable**. If Blender is in your system PATH, `"blender"` (or `"blender.exe"` on Windows if you call it that way) might work, but providing the full path is more reliable.

## Running the Application

1.  **Start the Flask server:**
    Once the setup is complete and your virtual environment is active, run:
    ```bash
    python app.py
    ```

2.  **Access the application:**
    Open your web browser and go to `http://127.0.0.1:5001` (or the port specified in `app.py` if you changed it).

## Usage

1.  **Select FBX File**: Click "Choose file" to upload your `.fbx` model.
2.  **Number of Frames**: If your model is animated, specify how many frames to render for each selected angle.
3.  **Render Style**: Choose a visual style. Pixelated styles will show an option for block size.
4.  **Image Format**: Select PNG (lossless) or WebP (lossy/lossless).
5.  **Output Type**: 
    *   `Individual Frames (Zip)`: Outputs a zip file containing all rendered frames, organized by angle if not using an auto-angle mode.
    *   `Sprite Sheet (PNG per Angle)`: Outputs a zip file containing one PNG sprite sheet for each processed angle.
6.  **Auto-Angles**: For non-animated models, you can choose to automatically render 16, 32, or 64 angles. This disables manual angle and frame count selection.
7.  **Select Viewing Angles**: If "Auto-Angles" is "Off", manually check the angles you want to render. You can also specify a custom angle.
8.  **Generate Preview**: Click this to see a single frame preview of your selected model, angle, and style.
9.  **Process Full Animation**: Once satisfied with the preview and settings, click this to render all selected angles and frames.

## Notes

*   Processing can be resource-intensive, especially for complex models, high frame counts, or many angles. Be patient.
*   The `uploads/` and `output/` directories are created to store temporary files and final results. They are included in `.gitignore` and should not be committed to the repository.

## To-Do / Future Enhancements (Example)

*   [ ] Add more render styles.
*   [ ] Option for different sprite sheet layouts (e.g., grid).
*   [ ] Progress bar for rendering.
*   [ ] More robust error handling and user feedback. 
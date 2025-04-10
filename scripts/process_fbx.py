import bpy
import sys
import os
import argparse
import math # Added for rotation
import mathutils # Import needed for bounding box calculations

def get_object_world_dimensions(obj):
    """Calculate the world-space dimensions of an object based on its bounding box corners."""
    if not obj or not hasattr(obj, 'bound_box'):
        print("DEBUG: Cannot get world dimensions, object has no bound_box.")
        return None

    # Get bounding box corner coordinates in world space
    try:
        world_bbox_corners = [(obj.matrix_world @ mathutils.Vector(corner)) for corner in obj.bound_box]
        print(f"DEBUG: World bounding box corners: {world_bbox_corners}")
    except Exception as e:
        print(f"DEBUG: Error calculating world corners: {e}")
        return None

    if not world_bbox_corners:
        print("DEBUG: Could not calculate world bounding box corners.")
        return None

    # Find min/max coordinates across all world corners
    try:
        min_coord = mathutils.Vector((min(v[i] for v in world_bbox_corners) for i in range(3)))
        max_coord = mathutils.Vector((max(v[i] for v in world_bbox_corners) for i in range(3)))
        print(f"DEBUG: World min coordinates: {min_coord}")
        print(f"DEBUG: World max coordinates: {max_coord}")
    except Exception as e:
        print(f"DEBUG: Error calculating min/max coords: {e}")
        return None

    dimensions = max_coord - min_coord
    print(f"DEBUG: Calculated world dimensions: {dimensions}")
    return dimensions

def get_animation_world_bounds(obj, start_frame, end_frame):
    """Calculates the overall world-space bounding box across an animation range."""
    print(f"DEBUG: Calculating animation bounds from frame {start_frame} to {end_frame}...")
    overall_min = mathutils.Vector((float('inf'), float('inf'), float('inf')))
    overall_max = mathutils.Vector((float('-inf'), float('-inf'), float('-inf')))
    has_bounds = False
    
    scene = bpy.context.scene
    original_frame = scene.frame_current

    try:
        # Consider sampling frames for performance on long animations (e.g., range(start, end + 1, 5))
        for frame in range(start_frame, end_frame + 1):
            scene.frame_set(frame)
            # We need the evaluated object at this frame. For simple cases, matrix_world might be okay,
            # but for complex rigs/modifiers, using the evaluated dependency graph is safer.
            # depsgraph = bpy.context.evaluated_depsgraph_get()
            # evaluated_obj = obj.evaluated_get(depsgraph)
            # Using matrix_world is simpler for now, might need evaluated_obj if issues persist.
            
            if not hasattr(obj, 'bound_box'): continue
            
            try:
                world_corners = [(obj.matrix_world @ mathutils.Vector(corner)) for corner in obj.bound_box]
                if not world_corners: continue

                # Update overall min/max
                for corner in world_corners:
                    for i in range(3):
                        overall_min[i] = min(overall_min[i], corner[i])
                        overall_max[i] = max(overall_max[i], corner[i])
                has_bounds = True
            except Exception as e_inner:
                print(f"DEBUG: Error getting bounds for frame {frame}: {e_inner}")
                # Continue trying other frames

        # Restore original frame
        scene.frame_set(original_frame)

        if not has_bounds:
            print("DEBUG: Failed to calculate any bounds during animation.")
            return None, None
        
        print(f"DEBUG: Overall animation bounds: Min={overall_min}, Max={overall_max}")
        return overall_min, overall_max

    except Exception as e_outer:
        print(f"ERROR: Failed during animation bounds calculation: {e_outer}")
        scene.frame_set(original_frame) # Ensure frame is reset on error
        return None, None

def setup_scene(render_style, pixel_resolution=None):
    """Clears the default scene and sets up basic render settings and lighting based on style."""
    # Delete default objects
    bpy.ops.object.select_all(action='SELECT')
    if bpy.context.selected_objects:
        bpy.ops.object.delete(use_global=False)
    
    # --- Add Lighting (Conditional) ---
    # Light needed for bright, cel, clay, AND pixel_cel
    if render_style in ['bright', 'cel', 'clay', 'pixel_cel']:
        # Add a Sun light for clear directional lighting
        bpy.ops.object.light_add(type='SUN', location=(0, 0, 5))
        sun_light = bpy.context.object
        sun_light.name = 'KeyLight'
        sun_light.rotation_euler = (math.radians(45), math.radians(-30), math.radians(45))
        sun_light.data.energy = 3.0 
        print(f"DEBUG: Added Sun light for style '{render_style}'")
    else: # 'unlit', 'original_unlit', 'wireframe'
        print(f"DEBUG: Skipping extra lighting for style '{render_style}'")
    # --- End Add Lighting ---

    # Set render settings
    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_EEVEE_NEXT' # Use Eevee Next for Blender 4.x+
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGBA' # For transparency
    scene.render.film_transparent = True
    scene.render.resolution_percentage = 100

    # Set resolution based on style
    if render_style == 'pixel_cel' and pixel_resolution:
        target_res = int(pixel_resolution)
        print(f"DEBUG: Setting render resolution to {target_res}x{target_res} for pixelated style.")
        scene.render.resolution_x = target_res
        scene.render.resolution_y = target_res
    else:
        print("DEBUG: Setting render resolution to 1024x1024 (default).")
        scene.render.resolution_x = 1024
        scene.render.resolution_y = 1024
    
    # Ensure compositor is disabled - we are not using it
    scene.use_nodes = False 

def setup_camera(target_object, overall_min=None, overall_max=None):
    """Creates and positions an orthographic camera based on overall animation bounds."""
    print(f"DEBUG: Setting up camera for target: {target_object.name}")
    print(f"DEBUG: Target object initial world location: {target_object.location}")
    # print(f"DEBUG: Target object world matrix:\n{target_object.matrix_world}") # Can be verbose

    # --- Calculate Center & Dimensions from Overall Bounds ---
    if overall_min is not None and overall_max is not None:
        world_center = (overall_min + overall_max) / 2.0
        world_dims = overall_max - overall_min
        print(f"DEBUG: Using OVERALL animation bounds for camera setup.")
        print(f"DEBUG: Overall Center={world_center}, Overall Dims={world_dims}")
    else:
        # Fallback to single-frame bounds calculation if overall calculation failed
        print("DEBUG: Using FALLBACK single-frame bounds for camera setup.")
        world_dims = get_object_world_dimensions(target_object)
        if world_dims:
            world_center = target_object.matrix_world.translation # Approximate center
        else:
             # Absolute fallback
             world_center = mathutils.Vector((0,0,0))
             world_dims = mathutils.Vector((2,2,2)) # Default size
             print("DEBUG: Critical fallback for camera setup.")
    # --- End Calculate Center & Dimensions ---

    # --- Create and Position Camera ---
    # Position camera in front of the object center along the Y axis
    # Keep Z aligned with the calculated center, adjust Y distance as needed
    camera_location = (world_center.x, world_center.y - 5.0, world_center.z) # Adjust Y offset (-5) if needed
    bpy.ops.object.camera_add(location=camera_location)
    camera_obj = bpy.context.object
    camera = camera_obj.data
    camera.name = "SpriteRenderCam"
    camera.type = 'ORTHO'
    print(f"DEBUG: Camera created at location: {camera_location}")

    # --- Point Camera --- 
    # Point the camera directly towards the calculated world center
    direction = world_center - camera_obj.location
    # Point Z axis up, Y axis forward (standard camera orientation)
    rot_quat = direction.to_track_quat('-Z', 'Y')
    camera_obj.rotation_euler = rot_quat.to_euler()
    print(f"DEBUG: Camera rotation set to look at {world_center}")
    # --- End Point Camera ---

    # --- Dynamic Orthographic Scale (using Overall Dimensions) ---
    try:
        if world_dims and max(world_dims.x, world_dims.z) > 0.001:
            # Use max of X and Z dimensions from OVERALL bounds
            ortho_scale = max(world_dims.x, world_dims.z) * 1.1 # Add 10% padding
            if ortho_scale < 0.1:
                print(f"Warning: Calculated overall ortho_scale ({ortho_scale}) too small, using fallback.")
                ortho_scale = 1
            camera.ortho_scale = ortho_scale
            print(f"DEBUG: Setting ortho_scale based on overall dims (X, Z): {ortho_scale}")
        else:
             print("Warning: Could not calculate valid overall dimensions for scale. Using default ortho_scale.")
             camera.ortho_scale = 5 # Default
    except Exception as e:
        print(f"Error calculating overall dimensions/ortho_scale: {e}. Using default.")
        camera.ortho_scale = 5 # Default
    # --- End Dynamic Scale ---

    bpy.context.scene.camera = camera_obj
    return camera_obj

def apply_toon_bsdf_nodes(material):
    """Modifies a material node tree to apply a basic cel-shading effect using Toon BSDF."""
    if not material or not material.use_nodes:
        print(f"DEBUG: Material '{material.name if material else 'None'}' does not use nodes. Skipping cel shader.")
        return

    print(f"DEBUG: Applying Toon BSDF shader to material: {material.name}")
    nodes = material.node_tree.nodes
    links = material.node_tree.links

    # Find the Material Output node
    output_node = nodes.get("Material Output") # More robust way to get it
    if not output_node:
        # Fallback search if name isn't default
        for node in nodes:
            if node.type == 'OUTPUT_MATERIAL':
                output_node = node
                break
        if not output_node:
             print(f"DEBUG: No Material Output node found in {material.name}. Skipping.")
             return

    # Find the node connected to the output node's Surface input
    surface_input = output_node.inputs.get('Surface')
    original_shader_node = None
    original_color_input_link = None
    original_surface_link = None

    if surface_input and surface_input.is_linked:
        original_surface_link = surface_input.links[0]
        original_shader_node = original_surface_link.from_node
        print(f"DEBUG: Found original shader node '{original_shader_node.name}' connected to Surface.")
        
        # Try to find the original Base Color input link on the original shader
        base_color_input = original_shader_node.inputs.get('Base Color')
        if base_color_input and base_color_input.is_linked:
            original_color_input_link = base_color_input.links[0]
            print(f"DEBUG: Found original Base Color link from node '{original_color_input_link.from_node.name}'")
        else:
             print(f"DEBUG: No linked Base Color input found on '{original_shader_node.name}'")
    else:
         print(f"DEBUG: Material Output 'Surface' input not linked in {material.name}. Cannot apply Toon BSDF intelligently.")
         # Optionally, could still create a default Toon BSDF, but might look bad
         return

    # --- Create and Configure Toon BSDF --- 
    toon_node = nodes.new(type='ShaderNodeBsdfToon')
    # Position it near the original shader
    toon_node.location = (original_shader_node.location.x + 200, original_shader_node.location.y)
    # Configure Toon BSDF (optional - adjust Smoothness, etc.)
    toon_node.inputs['Smooth'].default_value = 0.05 # Sharper cutoff
    toon_node.component = 'DIFFUSE' # Or 'GLOSSY' or combined
    print(f"DEBUG: Created Toon BSDF node for {material.name}")

    # --- Reconnect Nodes ---
    # 1. Connect original Base Color source to Toon BSDF Color input (if found)
    if original_color_input_link:
        try:
            # Link from the original source node/socket to the Toon node's color input
            links.new(original_color_input_link.from_socket, toon_node.inputs['Color'])
            print("DEBUG: Linked original Base Color source to Toon BSDF Color.")
        except Exception as e:
            print(f"DEBUG: Error linking original Base Color to Toon BSDF: {e}")
            # Fallback: Set default color? Toon node defaults to greyish.
    else:
        # If no original color link, leave Toon BSDF color as default (or set one)
        # toon_node.inputs['Color'].default_value = (0.8, 0.8, 0.8, 1.0) # Example default
        print("DEBUG: Using default color for Toon BSDF.")

    # 2. Disconnect original shader from Material Output Surface
    if original_surface_link:
        try:
            links.remove(original_surface_link)
            print("DEBUG: Disconnected original shader from Material Output.")
        except Exception as e:
            print(f"DEBUG: Error removing original surface link: {e}")
            # May already be disconnected if Base Color link failed badly?

    # 3. Connect Toon BSDF output to Material Output Surface
    try:
        links.new(toon_node.outputs['BSDF'], output_node.inputs['Surface'])
        print("DEBUG: Connected Toon BSDF to Material Output.")
    except Exception as e:
        print(f"DEBUG: Error connecting Toon BSDF to Material Output: {e}")
        # If this fails, the material will likely be broken.

def apply_unlit_shader_nodes(material):
    """Modifies a material node tree to apply a basic unlit (Emission) effect."""
    if not material or not material.use_nodes:
        print(f"DEBUG: Material '{material.name if material else 'None'}' does not use nodes. Skipping unlit shader.")
        return

    print(f"DEBUG: Applying Unlit (Emission) shader to material: {material.name}")
    nodes = material.node_tree.nodes
    links = material.node_tree.links

    output_node = nodes.get("Material Output")
    if not output_node: # Fallback search
        for node in nodes: 
            if node.type == 'OUTPUT_MATERIAL': output_node = node; break
        if not output_node: print(f"DEBUG: No Material Output node found in {material.name}. Skipping."); return

    surface_input = output_node.inputs.get('Surface')
    original_shader_node = None
    original_color_input_link = None
    original_surface_link = None

    if surface_input and surface_input.is_linked:
        original_surface_link = surface_input.links[0]
        original_shader_node = original_surface_link.from_node
        print(f"DEBUG: Found original shader node '{original_shader_node.name}' connected to Surface.")
        base_color_input = original_shader_node.inputs.get('Base Color')
        if base_color_input and base_color_input.is_linked:
            original_color_input_link = base_color_input.links[0]
            print(f"DEBUG: Found original Base Color link from node '{original_color_input_link.from_node.name}'")
        else: print(f"DEBUG: No linked Base Color input found on '{original_shader_node.name}'")
    else: print(f"DEBUG: Material Output 'Surface' input not linked in {material.name}. Cannot apply unlit shader intelligently."); return
    
    # --- Create Emission Shader ---
    emission_node = nodes.new(type='ShaderNodeEmission')
    emission_node.location = (original_shader_node.location.x + 200, original_shader_node.location.y)
    print(f"DEBUG: Created Emission node for {material.name}")

    # --- Reconnect Nodes ---
    # 1. Connect original Base Color source to Emission Color input (if found)
    if original_color_input_link:
        try:
            links.new(original_color_input_link.from_socket, emission_node.inputs['Color'])
            print("DEBUG: Linked original Base Color source to Emission Color.")
        except Exception as e: print(f"DEBUG: Error linking original Base Color to Emission: {e}")
    else: print("DEBUG: Using default color for Emission.")

    # 2. Disconnect original shader from Material Output Surface
    if original_surface_link: 
        try: links.remove(original_surface_link); print("DEBUG: Disconnected original shader from Material Output.")
        except Exception as e: print(f"DEBUG: Error removing original surface link: {e}")

    # 3. Connect Emission output to Material Output Surface
    try:
        links.new(emission_node.outputs['Emission'], output_node.inputs['Surface'])
        print("DEBUG: Connected Emission to Material Output.")
    except Exception as e: print(f"DEBUG: Error connecting Emission to Material Output: {e}")

def apply_wireframe_material(material):
    """Replaces the material node tree with a simple wireframe setup."""
    if not material or not material.use_nodes:
        print(f"DEBUG: Material '{material.name if material else 'None'}' does not use nodes. Skipping wireframe.")
        return
    print(f"DEBUG: Applying Wireframe material to: {material.name}")
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    # Clear existing nodes
    for node in nodes: nodes.remove(node)
    
    # Create new nodes
    output_node = nodes.new(type='ShaderNodeOutputMaterial')
    wire_node = nodes.new(type='ShaderNodeWireframe')
    wire_node.inputs['Size'].default_value = 0.01 # Adjust thickness
    wire_node.use_pixel_size = True # Use pixels for consistent thickness regardless of zoom
    emission_node = nodes.new(type='ShaderNodeEmission')
    emission_node.inputs['Color'].default_value = (1.0, 1.0, 1.0, 1.0) # White wireframe
    emission_node.inputs['Strength'].default_value = 1.0

    # Position nodes (optional)
    wire_node.location = (-200, 0)
    emission_node.location = (0, 0)

    # Link nodes: Wireframe Factor -> Emission Strength, Emission -> Output
    links.new(wire_node.outputs['Fac'], emission_node.inputs['Strength'])
    links.new(emission_node.outputs['Emission'], output_node.inputs['Surface'])
    print(f"DEBUG: Wireframe material applied to {material.name}")

def apply_clay_material(material):
    """Replaces the material node tree with a simple grey diffuse BSDF."""
    if not material or not material.use_nodes:
        print(f"DEBUG: Material '{material.name if material else 'None'}' does not use nodes. Skipping clay.")
        return
    print(f"DEBUG: Applying Clay material to: {material.name}")
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    # Clear existing nodes
    for node in nodes: nodes.remove(node)

    # Create new nodes
    output_node = nodes.new(type='ShaderNodeOutputMaterial')
    diffuse_node = nodes.new(type='ShaderNodeBsdfDiffuse')
    diffuse_node.inputs['Color'].default_value = (0.6, 0.6, 0.6, 1.0) # Medium grey
    diffuse_node.location = (-200, 0)

    # Link nodes: Diffuse -> Output
    links.new(diffuse_node.outputs['BSDF'], output_node.inputs['Surface'])
    print(f"DEBUG: Clay material applied to {material.name}")

def render_animation(fbx_path, output_dir, output_name, num_frames_to_render, angle_degrees, render_style, pixel_resolution=None):
    """Imports FBX, sets up scene/camera based on style, and renders animation frames."""
    setup_scene(render_style, pixel_resolution)

    try:
        bpy.ops.import_scene.fbx(filepath=fbx_path)
    except Exception as e:
        print(f"Error importing FBX: {e}")
        sys.exit(1) # Exit script with error status

    # Find the imported object(s) - often the first armature or mesh
    imported_object = None
    for obj in bpy.context.scene.objects:
        if obj.type == 'ARMATURE' or obj.type == 'MESH': # Prioritize armature if present
             imported_object = obj
             if obj.type == 'ARMATURE':
                 break # Found armature, likely the main object

    if not imported_object:
        print("Error: Could not find suitable object (Armature/Mesh) in imported FBX.")
        sys.exit(1)

    # Ensure object is selected and active
    bpy.context.view_layer.objects.active = imported_object
    imported_object.select_set(True)

    # --- Calculate Animation Bounds BEFORE Setting Up Camera ---
    overall_min_coord, overall_max_coord = None, None
    start_frame, end_frame = 1, 1 # Defaults
    if imported_object:
        if imported_object.animation_data and imported_object.animation_data.action:
            action = imported_object.animation_data.action
            start_frame = int(action.frame_range[0])
            end_frame = int(action.frame_range[1])
            print(f"Found animation: '{action.name}'. Frames: {start_frame} to {end_frame}")
            # Calculate overall bounds
            overall_min_coord, overall_max_coord = get_animation_world_bounds(imported_object, start_frame, end_frame)
        else:
            print("Warning: No animation data found. Camera bounds based on single frame.")
            # Fallback bounds calculation can happen inside setup_camera
    # --- End Calculate Animation Bounds ---

    # --- Apply Rotation ---
    if imported_object:
        print(f"Applying rotation: {angle_degrees} degrees around Z-axis")
        radians = math.radians(angle_degrees)
        imported_object.rotation_euler[2] += radians # Add to existing Z rotation
    # --- End Apply Rotation ---

    # Setup camera targeting the imported object, passing overall bounds
    setup_camera(imported_object, overall_min_coord, overall_max_coord)

    # Find animation range
    scene = bpy.context.scene
    start_frame = 1
    end_frame = 1
    if imported_object.animation_data and imported_object.animation_data.action:
        action = imported_object.animation_data.action
        start_frame = int(action.frame_range[0])
        end_frame = int(action.frame_range[1])
        scene.frame_start = start_frame
        scene.frame_end = end_frame
        print(f"Found animation: '{action.name}'. Frames: {start_frame} to {end_frame}")
    else:
        print("Warning: No animation data found on the primary object. Rendering frame 1 only.")

    # Determine frames to render
    frames_to_render = []
    total_source_frames = end_frame - start_frame + 1

    if total_source_frames <= 1 or num_frames_to_render <= 1:
        frames_to_render.append(start_frame) # Render only the start frame
        print(f"Rendering single frame: {start_frame}")
    else:
        # Ensure num_frames_to_render is not more than available frames
        num_frames_to_render = min(num_frames_to_render, total_source_frames)
        print(f"Calculating {num_frames_to_render} frames between {start_frame} and {end_frame}")
        # Calculate step, ensuring float division
        step = float(total_source_frames -1) / (num_frames_to_render - 1)
        for i in range(num_frames_to_render):
             current_frame = int(round(start_frame + i * step))
             # Clamp frame number just in case of rounding issues
             current_frame = max(start_frame, min(end_frame, current_frame))
             frames_to_render.append(current_frame)
        # Remove duplicates if rounding causes them, though unlikely with this method
        frames_to_render = sorted(list(set(frames_to_render)))
        print(f"Frames to render: {frames_to_render}")

    # --- Apply Shader based on Style ---
    if imported_object:
        print(f"DEBUG: Processing materials for object: {imported_object.name} with style '{render_style}'")
        materials_to_process = set()
        objects_to_check = [imported_object] + list(imported_object.children)
        for obj in objects_to_check:
            if hasattr(obj, 'material_slots'):
                for slot in obj.material_slots:
                    if slot.material: materials_to_process.add(slot.material)
        
        if not materials_to_process:
             print("DEBUG: No materials found.")
        else:
             print(f"DEBUG: Found materials: {[m.name for m in materials_to_process]}")
             for mat in materials_to_process:
                  # Note: 'cel' and 'unlit' calls are swapped based on user feedback
                  if render_style == 'cel': 
                      apply_unlit_shader_nodes(mat)
                      print(f"DEBUG: Applying UNLIT (Emission) nodes for selected style 'cel' to {mat.name}")
                  elif render_style == 'unlit':
                      apply_toon_bsdf_nodes(mat)
                      print(f"DEBUG: Applying TOON BSDF nodes for selected style 'unlit' to {mat.name}")
                  elif render_style == 'wireframe':
                      apply_wireframe_material(mat)
                  elif render_style == 'clay':
                      apply_clay_material(mat)
                  elif render_style == 'original_unlit':
                      print(f"DEBUG: Using original material for 'original_unlit' style for {mat.name}")
                  elif render_style == 'pixel_cel':
                      # Use the same node logic as 'cel' (which is currently apply_unlit_shader_nodes)
                      apply_unlit_shader_nodes(mat) # RESTORED this call
                      print(f"DEBUG: Applying UNLIT (Emission) nodes for selected style 'pixel_cel' to {mat.name}")
                  # else 'bright': do nothing
                  
    # --- End Apply Shader ---
    
    # Render the selected frames
    print(f"Rendering {len(frames_to_render)} frames to {output_dir} with base name {output_name}...")
    frame_index = 0
    for frame in frames_to_render:
        scene.frame_set(frame)
        # Use a consistent index for output filenames, not the actual frame number
        output_file_path = os.path.join(output_dir, f"{output_name}_{frame_index:04d}.png")
        frame_index += 1
        scene.render.filepath = output_file_path
        try:
            bpy.ops.render.render(write_still=True)
            print(f"Rendered source frame {frame} to {output_file_path}")
        except Exception as e:
             print(f"Error rendering frame {frame}: {e}")

    print("Rendering finished.")

if __name__ == "__main__":
    # Blender scripts need to parse args after '--'
    argv = sys.argv
    if "--" not in argv:
        argv = [] # no arguments passed
    else:
        argv = argv[argv.index("--") + 1:] # get all args after "--"

    parser = argparse.ArgumentParser(description='Render FBX animation frames using Blender.')
    parser.add_argument("--input", help="Path to the input FBX file", required=True)
    parser.add_argument("--output_dir", help="Directory to save rendered PNG frames", required=True)
    parser.add_argument("--output_name", help="Base name for output PNG files (e.g., 'sprite')", required=True)
    parser.add_argument("--num_frames", type=int, default=16, help="Number of frames to render for the sprite sheet (default: 16)")
    parser.add_argument("--angle", type=float, default=0.0, help="Viewing angle rotation around Z-axis in degrees (default: 0)")
    parser.add_argument("--render_style", default='bright', 
                        choices=['bright', 'cel', 'unlit', 'original_unlit', 'wireframe', 'clay', 'pixel_cel'],
                        help="Rendering style (default: bright)")
    parser.add_argument("--pixel_resolution", type=int, default=None, 
                        help="Target resolution for pixelated style (e.g., 128)")

    args = parser.parse_args(argv)

    # Ensure output directory exists
    os.makedirs(args.output_dir, exist_ok=True)

    render_animation(args.input, args.output_dir, args.output_name, args.num_frames, args.angle, args.render_style, args.pixel_resolution) 
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

def setup_scene(render_style, output_format, pixel_resolution=None):
    """Clears the default scene, sets up render settings (incl. format, pixelation) and lighting."""
    print(f"--- DEBUG (setup_scene): Received render_style = '{render_style}'") # Added Debug
    # Delete default objects
    bpy.ops.object.select_all(action='SELECT')
    if bpy.context.selected_objects:
        bpy.ops.object.delete(use_global=False)
    
    # --- Add Lighting (Conditional) ---
    # Light needed for bright, cel, clay, pixel_cel, cel_outline, cel_thicker_outline, pixel_outline
    if render_style in ['bright', 'cel', 'clay', 'pixel_cel', 'cel_outline', 'cel_thicker_outline', 'pixel_outline', 'pixel_post_outline']:
        # Add a Sun light for clear directional lighting
        bpy.ops.object.light_add(type='SUN', location=(0, 0, 5))
        sun_light = bpy.context.object
        sun_light.name = 'KeyLight'
        sun_light.rotation_euler = (math.radians(45), math.radians(-30), math.radians(45))
        sun_light.data.energy = 3.0 
        print(f"DEBUG: Added Sun light for style '{render_style}'")
    # --- Blueprint: Set Background --- 
    elif render_style == 'blueprint':
        print("--- DEBUG (setup_scene): ENTERING BLUEPRINT BACKGROUND SETUP ---") # Added Debug
        print("DEBUG: Setting blue world background for Blueprint style.")
        bpy.context.scene.world.use_nodes = True
        bg_node = bpy.context.scene.world.node_tree.nodes.get("Background")
        if bg_node: 
            bg_node.inputs['Color'].default_value = (0.05, 0.1, 0.3, 1.0) # Dark Blue
            bg_node.inputs['Strength'].default_value = 1.0
        else:
            print("Warning: Could not find Background node to set blueprint color.")
    else: # 'unlit', 'original_unlit', 'wireframe'
        print(f"DEBUG: Skipping extra lighting for style '{render_style}'")
    # --- End Add Lighting ---

    # Set render settings
    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_EEVEE_NEXT' # Use Eevee Next for Blender 4.x+
    scene.render.film_transparent = True
    scene.render.resolution_percentage = 100

    # Set resolution based on style
    if render_style in ['pixel_cel', 'pixel_outline', 'pixel_post_outline', 'pixel_post_thin_outline'] and pixel_resolution: # Apply low-res to all pixel styles
        target_res = int(pixel_resolution)
        print(f"DEBUG: Setting render resolution to {target_res}x{target_res} for pixelated style.")
        scene.render.resolution_x = target_res
        scene.render.resolution_y = target_res
    else:
        print("DEBUG: Setting render resolution to 1024x1024 (default).")
        scene.render.resolution_x = 1024
        scene.render.resolution_y = 1024
    
    # Set Output Format
    if output_format == 'WEBP':
        scene.render.image_settings.file_format = 'WEBP'
        # Optional: Configure WebP settings (quality, lossless)
        # scene.render.image_settings.quality = 90 
        # scene.render.image_settings.webp_lossless = True 
        print(f"DEBUG: Setting output format to WEBP")
    else: # Default to PNG
        scene.render.image_settings.file_format = 'PNG'
        scene.render.image_settings.color_mode = 'RGBA' # Ensure RGBA for PNG
        print(f"DEBUG: Setting output format to PNG")

    # --- Freestyle Setup (Conditional) ---
    if render_style == 'blueprint':
        print("--- DEBUG (setup_scene): ENTERING BLUEPRINT FREESTYLE SETUP ---") # Added Debug
        print("DEBUG: Enabling and configuring Freestyle for Blueprint style.")
        scene.render.use_freestyle = True
        freestyle_settings = scene.view_layers["ViewLayer"].freestyle_settings
        # Try getting existing or add new
        lineset = freestyle_settings.linesets.get("BlueprintLines")
        if not lineset:
            lineset = freestyle_settings.linesets.new("BlueprintLines")
            
        # Configure which lines to draw
        lineset.select_silhouette = True
        lineset.select_border = True
        lineset.select_crease = True # Draw lines on sharp edges
        lineset.select_edge_mark = False # Don't use manually marked edges for now
        lineset.select_material_boundary = False
        
        # Configure line appearance
        linestyle = lineset.linestyle
        linestyle.color = (1.0, 1.0, 1.0) # White lines (RGB)
        linestyle.alpha = 1.0 # Set alpha separately
        linestyle.thickness = 1.5 # Adjust thickness as needed
        # linestyle.use_alpha = False # Removed: Alpha controlled via color
    else:
         scene.render.use_freestyle = False # Ensure it's off for other styles
    # --- End Freestyle Setup ---

    # Ensure compositor is disabled - we are not using it
    scene.use_nodes = False 

def setup_camera(target_object, angle_degrees, anim_min=None, anim_max=None):
    """Creates and positions an orthographic camera rotated around the target object.
       Uses overall animation bounds if provided, otherwise falls back to frame 1 bounds.
    """
    print(f"DEBUG: Setting up camera for target: {target_object.name}")
    print(f"DEBUG: Target object initial world location: {target_object.location}")
    # print(f"DEBUG: Target object world matrix:\n{target_object.matrix_world}") # Can be verbose

    # --- Determine Center and Dimensions (Animation Bounds or Frame 1 Fallback) ---
    cam_world_center = mathutils.Vector((0.0, 0.0, 0.0))
    cam_world_dims = mathutils.Vector((1.0, 1.0, 1.0)) # Default size
    bounds_source = "Default"

    if anim_min and anim_max:
        # Use provided animation bounds
        cam_world_center = (anim_min + anim_max) / 2.0
        cam_world_dims = anim_max - anim_min
        bounds_source = "Animation Bounds"
        print(f"DEBUG: Using provided Animation Bounds for camera setup.")
        print(f"DEBUG: Animation Center: {cam_world_center}")
        print(f"DEBUG: Animation Dimensions: {cam_world_dims}")
    else:
        # Fallback to Frame 1 bounds
        print("DEBUG: No animation bounds provided or calc failed. Falling back to Frame 1 bounds.")
        bounds_source = "Frame 1"
        try:
            scene = bpy.context.scene
            original_frame = scene.frame_current
            scene.frame_set(1) 
            
            frame1_world_dims = get_object_world_dimensions(target_object)
            if frame1_world_dims:
                frame1_bbox_corners = [(target_object.matrix_world @ mathutils.Vector(corner)) for corner in target_object.bound_box]
                if frame1_bbox_corners:
                    min_coord = mathutils.Vector((min(v[i] for v in frame1_bbox_corners) for i in range(3)))
                    max_coord = mathutils.Vector((max(v[i] for v in frame1_bbox_corners) for i in range(3)))
                    cam_world_center = (min_coord + max_coord) / 2.0
                    cam_world_dims = frame1_world_dims # Use calculated dims
                    print(f"DEBUG: Calculated Frame 1 Center: {cam_world_center}")
                    print(f"DEBUG: Calculated Frame 1 Dimensions: {cam_world_dims}")
                else:
                     print("DEBUG: Could not get Frame 1 corners, using object origin/default dims.")
                     cam_world_center = target_object.matrix_world.translation
                     cam_world_dims = mathutils.Vector((2,2,2))
            else:
                 print("DEBUG: Could not get Frame 1 dims, using object origin/default dims.")
                 cam_world_center = target_object.matrix_world.translation
                 cam_world_dims = mathutils.Vector((2,2,2))
                 
            scene.frame_set(original_frame)
        except Exception as e_fc:
             print(f"Error getting Frame 1 center/dims: {e_fc}. Using object origin/default dims.")
             cam_world_center = target_object.matrix_world.translation # Fallback
             cam_world_dims = mathutils.Vector((2,2,2))
    # --- End Determine Center & Dimensions ---

    # --- Determine Orthographic Scale (Using selected bounds: cam_world_dims) ---
    calculated_ortho_scale = 5.0 # Default fallback scale
    try:
        if cam_world_dims and cam_world_dims.length > 0.001: 
            scene = bpy.context.scene
            aspect_ratio = scene.render.resolution_x / scene.render.resolution_y
            padding_multiplier = 2.2 # Keep increased padding

            max_world_dim = max(cam_world_dims.x, cam_world_dims.y, cam_world_dims.z)

            base_scale = max_world_dim / 2.0
            if aspect_ratio < 1.0: 
                 scale_factor = 1.0 / aspect_ratio
                 base_scale *= scale_factor
            calculated_ortho_scale = base_scale * padding_multiplier

            print(f"DEBUG: Max World Dim ({bounds_source}): {max_world_dim:.4f}")
            print(f"DEBUG: Aspect Ratio: {aspect_ratio:.4f}")

            if calculated_ortho_scale < 0.01:
                print(f"Warning: Calculated ortho_scale ({calculated_ortho_scale}) from {bounds_source} is very small, clamping to 0.1.")
                calculated_ortho_scale = 0.1
            print(f"DEBUG: Determined final ortho_scale from {bounds_source}: {calculated_ortho_scale:.4f}")
        else:
             print(f"Warning: Could not calculate valid {bounds_source} dimensions for scale. Using default ortho_scale 5.")
             # calculated_ortho_scale remains 5.0

    except ZeroDivisionError:
        print("Error: Render resolution Y is zero, cannot calculate aspect ratio. Using default scale 5.")
        # calculated_ortho_scale remains 5.0
    except Exception as e:
        print(f"Error calculating ortho_scale from {bounds_source} dims: {e}. Using default 5.")
        # calculated_ortho_scale remains 5.0
    # --- End Determine Orthographic Scale ---

    # --- Create and Position Camera (Relative to Calculated Center: cam_world_center) ---
    camera_distance_multiplier = 2.5 
    camera_y_offset = calculated_ortho_scale * camera_distance_multiplier
    min_camera_distance = 1.0 
    effective_camera_distance = max(min_camera_distance, camera_y_offset)
    
    initial_offset = mathutils.Vector((0, -effective_camera_distance, 0))
    radians = math.radians(angle_degrees)
    rot_matrix = mathutils.Matrix.Rotation(radians, 4, 'Z')
    rotated_offset = rot_matrix @ initial_offset
    
    # Calculate final camera location relative to the determined world center
    camera_location = cam_world_center + rotated_offset 
    print(f"DEBUG: Setting camera angle={angle_degrees} deg, location={camera_location} (relative to {bounds_source} center)")

    bpy.ops.object.camera_add(location=camera_location)
    camera_obj = bpy.context.object
    camera = camera_obj.data
    camera.name = "SpriteRenderCam"
    camera.type = 'ORTHO'
    camera.ortho_scale = calculated_ortho_scale 

    # --- Point Camera (Towards Calculated Center: cam_world_center) --- 
    camera_target_point = cam_world_center 
    print(f"DEBUG: Using {bounds_source} center for camera target: {camera_target_point}")

    # Calculate direction from camera location to the target point
    direction = camera_target_point - camera_obj.location 
    rot_quat = direction.to_track_quat('-Z', 'Y')
    camera_obj.rotation_euler = rot_quat.to_euler()
    print(f"DEBUG: Camera rotation set to look at {bounds_source} target: {camera_target_point}")
    # --- End Point Camera ---

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

def create_outline_material():
    """Creates a black, shadeless material for the inverted hull outline."""
    mat_name = "OutlineMaterial"
    outline_mat = bpy.data.materials.get(mat_name)
    if outline_mat is None:
        outline_mat = bpy.data.materials.new(name=mat_name)
        outline_mat.use_nodes = True
        nodes = outline_mat.node_tree.nodes
        links = outline_mat.node_tree.links
        for node in nodes: nodes.remove(node) # Clear default nodes

        output_node = nodes.new(type='ShaderNodeOutputMaterial')
        emission_node = nodes.new(type='ShaderNodeEmission')
        emission_node.inputs['Color'].default_value = (0.0, 0.0, 0.0, 1.0) # Black
        emission_node.inputs['Strength'].default_value = 1.0
        emission_node.location = (-200, 0)
        links.new(emission_node.outputs['Emission'], output_node.inputs['Surface'])
        
        outline_mat.use_backface_culling = True # Crucial for outline effect
        print("DEBUG: Created Outline material.")
    return outline_mat

def apply_outline_modifier(obj, outline_material, thickness=-0.005):
    """Adds and configures a Solidify modifier for the inverted hull outline.
       Accepts an optional thickness parameter.
    """
    if obj.type != 'MESH':
        print(f"DEBUG: Skipping outline modifier for non-mesh object: {obj.name}")
        return
    
    print(f"DEBUG: Applying outline modifier to mesh object: {obj.name}")
    
    # Add new material slot if needed and assign outline material
    if outline_material.name not in obj.material_slots:
        obj.data.materials.append(outline_material)
        print(f"DEBUG: Added outline material slot to {obj.name}")
    else:
        print(f"DEBUG: Outline material slot already exists on {obj.name}")
    outline_slot_index = obj.material_slots.find(outline_material.name)
    if outline_slot_index == -1:
        print(f"ERROR: Could not find outline material slot index on {obj.name} after adding it!")
        return # Should not happen
    
    # Add Solidify Modifier
    mod_name = "OutlineSolidify"
    solidify_mod = obj.modifiers.get(mod_name)
    if not solidify_mod:
        solidify_mod = obj.modifiers.new(name=mod_name, type='SOLIDIFY')
        print(f"DEBUG: Added Solidify modifier to {obj.name}")
    else:
        print(f"DEBUG: Solidify modifier already exists on {obj.name}")
        
    # Configure Solidify Modifier
    solidify_mod.thickness = thickness # Use passed thickness value
    solidify_mod.offset = 0 
    solidify_mod.use_flip_normals = True 
    solidify_mod.material_offset = outline_slot_index 
    solidify_mod.use_rim = False 
    print(f"DEBUG: Configured Solidify modifier for {obj.name} with thickness {thickness}")

def render_animation(fbx_path, output_dir, output_name, num_frames_to_render, angle_degrees, render_style, output_format, pixel_resolution=None):
    """Imports FBX, sets up scene/camera/style/format, and renders animation frames."""
    print(f"--- DEBUG (render_animation): Received render_style = '{render_style}'") # Added Debug
    setup_scene(render_style, output_format, pixel_resolution)

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

    # --- Get Animation Range ---
    scene = bpy.context.scene
    start_frame = 1
    end_frame = 1
    action = None
    if imported_object.animation_data and imported_object.animation_data.action:
        action = imported_object.animation_data.action
        start_frame = int(action.frame_range[0])
        end_frame = int(action.frame_range[1])
        scene.frame_start = start_frame
        scene.frame_end = end_frame
        print(f"Found animation: '{action.name}'. Frames: {start_frame} to {end_frame}")
    else:
        print("Warning: No animation data found on the primary object. Will use frame 1 bounds.")
    # --- End Get Animation Range ---
    
    # --- Calculate Overall Animation Bounds (if animation exists) ---
    overall_min = None
    overall_max = None
    if action and end_frame > start_frame: # Only calculate if there's an animation > 1 frame
        print("Attempting to calculate overall animation bounds...")
        overall_min, overall_max = get_animation_world_bounds(imported_object, start_frame, end_frame)
        if overall_min and overall_max:
             print(f"Successfully calculated animation bounds: Min={overall_min}, Max={overall_max}")
        else:
             print("Failed to calculate overall animation bounds, will fall back to frame 1.")
    # --- End Calculate Overall Animation Bounds ---

    # Setup camera targeting the imported object, passing angle and optional animation bounds
    setup_camera(imported_object, angle_degrees, anim_min=overall_min, anim_max=overall_max)

    # Determine frames to render (Original logic moved after camera setup)
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

    # --- Create Outline Material (if needed) ---
    outline_material_instance = None
    if render_style in ['cel_outline', 'cel_thicker_outline', 'pixel_outline']: # Add pixel_outline
        outline_material_instance = create_outline_material()
    # --- End Create Outline Material ---
    
    # --- Apply Shaders / Modifiers based on Style ---
    if imported_object:
        print(f"DEBUG: Processing materials/modifiers for object: {imported_object.name} with style '{render_style}'")
        objects_to_process = [imported_object] # Start with main object
        # If main object is Armature or Empty, process its children instead/as well
        if imported_object.type in ['ARMATURE', 'EMPTY']:
             objects_to_process.extend(child for child in imported_object.children if child.type == 'MESH')
        elif imported_object.type != 'MESH': # If main is not mesh/armature/empty, skip? 
             objects_to_process = [] # Safety
             print(f"WARNING: Imported object {imported_object.name} is not Mesh/Armature/Empty, shader/modifier application might be limited.")
             # Only process mesh children if main object isn't a mesh itself
             objects_to_process.extend(child for child in imported_object.children if child.type == 'MESH') 

        # Remove duplicates and ensure we only process MESH objects for modifiers/materials
        mesh_objects_to_process = list({obj for obj in objects_to_process if obj.type == 'MESH'})
        print(f"DEBUG: Found MESH objects to process: {[obj.name for obj in mesh_objects_to_process]}")

        # Process Materials FIRST (unless clay/wireframe)
        if render_style not in ['clay', 'wireframe']:
            all_materials = set()
            for obj in mesh_objects_to_process:
                for slot in obj.material_slots: 
                    if slot.material: all_materials.add(slot.material)
            
            print(f"DEBUG: Found materials for style '{render_style}': {[m.name for m in all_materials]}")
            for mat in all_materials:
                  # --- Restore original material-based style logic ---
                  if render_style in ['cel', 'cel_outline', 'cel_thicker_outline']:
                      # For outline styles, we want unlit original colors + an outline modifier later
                      apply_unlit_shader_nodes(mat) 
                      print(f"DEBUG: Applying UNLIT (Emission) nodes for selected style '{render_style}' to {mat.name}")
                  elif render_style == 'unlit':
                      # For plain unlit, we apply unlit shader nodes
                      apply_unlit_shader_nodes(mat)
                      print(f"DEBUG: Applying UNLIT (Emission) nodes for selected style '{render_style}' to {mat.name}")
                      # apply_toon_bsdf_nodes(mat) # This was likely incorrect for 'unlit'
                  elif render_style == 'original_unlit':
                      # Leave material as is (it's already unlit if imported correctly)
                      print(f"DEBUG: Using original material for 'original_unlit' style for {mat.name}")
                  elif render_style in ['pixel_cel', 'pixel_outline', 'pixel_post_outline', 'pixel_post_thin_outline']:
                      # Treat pixel_post_outline and pixel_post_thin_outline the same as pixel_cel for Blender
                      if render_style in ['pixel_post_outline', 'pixel_post_thin_outline']:
                          print(f"DEBUG: Treating '{render_style}' as 'pixel_cel' for Blender rendering.")
                      # Use unlit for pixelated base colors
                      apply_unlit_shader_nodes(mat)
                      print(f"DEBUG: Applying UNLIT (Emission) nodes for selected style '{render_style}' to {mat.name}")
                  # --- Blueprint Material Handling (Correct Location) ---
                  elif render_style == 'blueprint':
                      print(f"--- DEBUG (render_animation): ENTERING BLUEPRINT MATERIAL SETUP for {mat.name} ---") # Added Debug
                      apply_unlit_shader_nodes(mat) # Apply base unlit setup first
                      # Explicitly set emission color to white
                      try:
                          emission_node = mat.node_tree.nodes.get("Emission")
                          if emission_node and 'Color' in emission_node.inputs:
                              emission_node.inputs['Color'].default_value = (1.0, 1.0, 1.0, 1.0) # White
                              print(f"DEBUG: Set Blueprint emission color to WHITE for {mat.name}")
                          else:
                              print(f"Warning: Could not find Emission node or Color input for Blueprint style on {mat.name}")
                      except Exception as e_bp_mat:
                          print(f"Warning: Error setting Blueprint emission color for {mat.name}: {e_bp_mat}")
                  # ---------------------------------------------------
                  elif render_style == 'halftone': # Placeholder
                      apply_halftone_dots_nodes(mat)
                      print(f"DEBUG: Applying HALFTONE placeholder to {mat.name}")
                  elif render_style == 'hatched': # Placeholder
                       apply_toon_bsdf_nodes(mat) # Use Toon as base
                       print(f"DEBUG: Applying HATCHED placeholder (Toon) to {mat.name}")
                  elif render_style == 'glitch': # Placeholder
                       apply_unlit_shader_nodes(mat) # Unlit base
                       print(f"DEBUG: Applying GLITCH placeholder (Unlit) to {mat.name}")
                  elif render_style == 'ascii_art': # Placeholder
                       apply_high_contrast_nodes(mat)
                       print(f"DEBUG: Applying ASCII_ART placeholder (High Contrast) to {mat.name}")
                  # else 'bright': do nothing to material nodes here, lighting is handled

        # Process Modifiers / Full Material Overrides (Clay, Wireframe, Outlines)
        for obj in mesh_objects_to_process:
             if render_style == 'cel_outline' and outline_material_instance:
                  apply_outline_modifier(obj, outline_material_instance) # Default thickness
             elif render_style == 'cel_thicker_outline' and outline_material_instance:
                  apply_outline_modifier(obj, outline_material_instance, thickness=-0.015)
             elif render_style == 'pixel_outline' and outline_material_instance:
                  apply_outline_modifier(obj, outline_material_instance, thickness=-0.015) # Use thicker outline for pixel style too
             elif render_style == 'clay':
                  # Clay needs to replace existing materials on the object
                  if obj.material_slots:
                      clay_mat = bpy.data.materials.get("ClayMaterial")
                      if clay_mat is None: # Create if doesn't exist
                          clay_mat = bpy.data.materials.new(name="ClayMaterial")
                          apply_clay_material(clay_mat) # This clears nodes and adds diffuse
                      for slot in obj.material_slots:
                          slot.material = clay_mat
                      print(f"DEBUG: Applied clay material override to {obj.name}")
                  else: print(f"DEBUG: No material slots on {obj.name} to apply clay override.")
             elif render_style == 'wireframe':
                  # Wireframe needs to replace existing materials
                  if obj.material_slots:
                      wire_mat = bpy.data.materials.get("WireframeMaterial")
                      if wire_mat is None: # Create if doesn't exist
                          wire_mat = bpy.data.materials.new(name="WireframeMaterial")
                          apply_wireframe_material(wire_mat) # This clears nodes and adds wireframe setup
                      for slot in obj.material_slots:
                          slot.material = wire_mat
                      print(f"DEBUG: Applied wireframe material override to {obj.name}")
                  else: print(f"DEBUG: No material slots on {obj.name} to apply wireframe override.")
             # Placeholder logic for object-specific parts of new styles (if any)
             elif render_style == 'halftone': pass
             elif render_style == 'hatched': pass
             elif render_style == 'glitch': pass
             elif render_style == 'ascii_art': pass
             # Fallback/Unknown
             else:
                  print(f"Warning: Unknown or default render style '{render_style}'. Using default Bright lighting.")
                  # Default behavior (bright lighting) is already handled by add_sun_light()

    # --- End Apply Shader / Modifiers ---
    
    # Determine file extension
    file_extension = output_format.lower()
    
    # Render the selected frames
    print(f"Rendering {len(frames_to_render)} frames to {output_dir} with base name {output_name} (Format: {output_format})...")
    frame_index = 0
    for frame in frames_to_render:
        scene.frame_set(frame)
        # Set filepath WITHOUT extension (Blender adds it based on format)
        frame_filename_base = f"{output_name}_{frame_index:04d}"
        scene.render.filepath = os.path.join(output_dir, frame_filename_base)
        
        print(f"--- DEBUG (render_animation): Rendering frame {frame_index} to base path: {scene.render.filepath} with format {scene.render.image_settings.file_format} ---") # Added Debug
        
        # Render the frame
        bpy.ops.render.render(write_still=True)
        
        # --- Verify file existence --- 
        expected_filepath = f"{scene.render.filepath}.{file_extension}"
        if os.path.exists(expected_filepath):
            print(f"DEBUG (render_animation): Verified file exists at: {expected_filepath}")
        else:
            print(f"ERROR (render_animation): File NOT found after render at expected path: {expected_filepath}")
        # ---------------------------
            
        print(f"DEBUG (render_animation): Frame {frame_index} render complete.")
        frame_index += 1

    print("Rendering finished.")

# --- Placeholder Functions for New Styles --- 
def apply_halftone_dots_nodes(material):
    """Placeholder: Modifies material nodes for halftone effect."""
    print(f"Placeholder: Applying Halftone Dots nodes to {material.name}")
    # TODO: Implement actual halftone node setup (e.g., using Voronoi or OSL)
    apply_unlit_shader_nodes(material) # Fallback to unlit for now

def apply_high_contrast_nodes(material):
    """Placeholder: Modifies material for high-contrast B&W output (for ASCII)."""
    print(f"Placeholder: Applying High Contrast nodes to {material.name}")
    # TODO: Implement B&W thresholding node setup
    apply_unlit_shader_nodes(material) # Fallback to unlit for now
    # Set emission color to white temporarily
    try:
        emission_node = material.node_tree.nodes.get("Emission")
        if emission_node: 
            emission_node.inputs['Color'].default_value = (1.0, 1.0, 1.0, 1.0) 
    except Exception:
        pass # Ignore if nodes don't exist as expected

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
                        choices=['bright', 'cel', 'unlit', 'original_unlit', 'wireframe', 'clay', 'pixel_cel', 'cel_outline', 'cel_thicker_outline', 'pixel_outline', 'pixel_post_outline', 'pixel_post_thin_outline', 'blueprint', 'halftone', 'hatched', 'glitch', 'ascii_art'],
                        help="Rendering style (default: bright)")
    parser.add_argument("--output_format", default='PNG', choices=['PNG', 'WEBP'], 
                        help="Output image format (default: PNG)")
    parser.add_argument("--pixel_resolution", type=int, default=None,
                        help="Target resolution for pixelated style (e.g., 128)")

    args = parser.parse_args(argv)

    # Ensure output directory exists
    os.makedirs(args.output_dir, exist_ok=True)

    render_animation(args.input, args.output_dir, args.output_name, args.num_frames, args.angle, args.render_style, args.output_format, args.pixel_resolution) 
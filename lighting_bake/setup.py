import math

import bpy

# Create bake UV maps, blank images, and image nodes. Does not bake.

_UV_PACK_MARGIN = 0.01
_SMART_ANGLE = math.radians(66.0)


class BakeJob:
    def __init__(self, objects, image, uv_name, label):
        self.objects = tuple(objects)
        self.image = image
        self.uv_name = uv_name
        self.label = label


class SetupResult:
    def __init__(self):
        self.messages = []
        self.warnings = []
        self.completed = 0
        self.jobs = []

    @property
    def ok(self):
        return self.completed > 0


def setup_bake_targets(context, targets):
    result = SetupResult()
    if not targets:
        result.warnings.append("No meshes left to bake.")
        return result

    settings = context.scene.lighting_bake
    individual = settings.bake_mode == 'INDIVIDUAL'
    resolution = int(settings.resolution)
    method = settings.unwrap_method
    preview = settings.node_setup == 'PREVIEW'
    margin_px = settings.margin_px
    previous_selected = list(context.selected_objects)
    previous_active = context.view_layer.objects.active

    try:
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        for obj in targets:
            _make_mesh_single_user(obj, result)

        users = _material_users(targets)
        if individual:
            for obj in targets:
                _privatize_individual(obj, users, result)
        else:
            _privatize_group(targets, users, result)

        for obj in targets:
            _ensure_material(obj, result)

        if individual:
            for obj in targets:
                _setup_one_object(context, obj, resolution, method, preview, margin_px, result)
        else:
            _setup_one_map(context, targets, settings, resolution, method, preview, margin_px, result)
    finally:
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        _restore_selection(context, previous_selected, previous_active)

    if result.ok:
        noun = "mesh" if result.completed == 1 else "meshes"
        result.messages.append(f"Created bake UVs and images for {result.completed} {noun}.")
    else:
        result.warnings.append("No bake UVs or images were created.")
    return result


def _setup_one_object(context, obj, resolution, method, preview, margin_px, result):
    uv_name = _uv_name_for_object(obj, f"{obj.name}LightingBaked", method)
    image = _new_image(f"{obj.name}LightingBakedTexture", resolution, margin_px, uv_name)
    _write_object_map(context, obj, uv_name, image, method, preview, result)


def _setup_one_map(context, targets, settings, resolution, method, preview, margin_px, result):
    group_name = settings.group_name.strip() or "Group"
    base_uv = f"{group_name}LightingBaked"
    uv_name = base_uv if method == 'KEEP' else _unique_name(base_uv, _uv_names(targets))
    image = _new_image(f"{group_name}LightingBakedTexture", resolution, margin_px, uv_name)

    for obj in targets:
        _ensure_uv_layer(obj.data, uv_name)
        if method == 'KEEP':
            continue
        try:
            _unwrap_object(context, obj, method)
        except RuntimeError as exc:
            result.warnings.append(f"{obj.name} could not be unwrapped: {exc}")

    if method != 'KEEP' and len(targets) > 1:
        try:
            _pack_group(context, targets, uv_name)
        except RuntimeError as exc:
            result.warnings.append(f"Could not pack the shared UV map, so islands may overlap: {exc}")

    for obj in targets:
        _add_object_nodes(obj, image, uv_name, preview)
        result.completed += 1
        result.messages.append(f"{obj.name}: UV {uv_name}, image {image.name}.")
    result.jobs.append(BakeJob(targets, image, uv_name, group_name))


def _write_object_map(context, obj, uv_name, image, method, preview, result):
    _ensure_uv_layer(obj.data, uv_name)
    if method != 'KEEP':
        try:
            _unwrap_object(context, obj, method)
        except RuntimeError as exc:
            result.warnings.append(f"{obj.name} could not be unwrapped: {exc}")
    _add_object_nodes(obj, image, uv_name, preview)
    result.completed += 1
    result.messages.append(f"{obj.name}: UV {uv_name}, image {image.name}.")
    result.jobs.append(BakeJob((obj,), image, uv_name, obj.name))


def _uv_name_for_object(obj, base_name, method):
    if method == 'KEEP' and base_name in obj.data.uv_layers:
        return base_name
    return _unique_name(base_name, set(obj.data.uv_layers.keys()))


def _make_mesh_single_user(obj, result):
    if obj.data is None or obj.data.users <= 1:
        return
    obj.data = obj.data.copy()
    result.messages.append(f"Made {obj.name} mesh data single-user so the new UV stays on this object.")


def _material_users(targets):
    wanted = set()
    for obj in targets:
        for slot in obj.material_slots:
            if slot.material is not None:
                wanted.add(slot.material)
    users = {material: [] for material in wanted}
    for obj in bpy.data.objects:
        if obj.type != 'MESH':
            continue
        for slot in obj.material_slots:
            material = slot.material
            if material in users and obj not in users[material]:
                users[material].append(obj)
    return users


def _privatize_individual(obj, users, result):
    replacements = {}
    for slot in obj.material_slots:
        material = slot.material
        if material is None:
            continue
        others = [user for user in users.get(material, []) if user != obj]
        if not others:
            continue
        if material not in replacements:
            replacements[material] = material.copy()
            shared = ", ".join(user.name for user in others)
            result.messages.append(f"Duplicated material {material.name} for {obj.name}. It is also on {shared}.")
        slot.material = replacements[material]


def _privatize_group(targets, users, result):
    target_ids = {obj.as_pointer() for obj in targets}
    replacements = {}
    for obj in targets:
        for slot in obj.material_slots:
            material = slot.material
            if material is None:
                continue
            outsiders = [user for user in users.get(material, []) if user.as_pointer() not in target_ids]
            if not outsiders:
                continue
            if material not in replacements:
                replacements[material] = material.copy()
                names = ", ".join(user.name for user in outsiders)
                result.messages.append(
                    f"Duplicated material {material.name} for the bake set. Still used by {names}."
                )
            slot.material = replacements[material]


def _ensure_material(obj, result):
    mesh = obj.data
    if len(obj.material_slots) == 0:
        material = bpy.data.materials.new(_unique_name(f"{obj.name}LightingBakedMaterial", set(bpy.data.materials.keys())))
        mesh.materials.append(material)
        result.messages.append(f"Created material {material.name} for {obj.name}.")
        return

    for slot in obj.material_slots:
        if slot.material is not None:
            continue
        material = bpy.data.materials.new(_unique_name(f"{obj.name}LightingBakedMaterial", set(bpy.data.materials.keys())))
        slot.material = material
        result.messages.append(f"Created material {material.name} for an empty slot on {obj.name}.")


def _new_image(base_name, resolution, margin_px, uv_name):
    name = _unique_name(base_name, set(bpy.data.images.keys()))
    image = bpy.data.images.new(name=name, width=resolution, height=resolution, alpha=False, float_buffer=False)
    image.colorspace_settings.name = "sRGB"
    image.generated_color = (0.0, 0.0, 0.0, 1.0)
    # Pixel bake margin is applied when the bake runs. Keep it with the image.
    image["lighting_bake_margin_px"] = margin_px
    image["lighting_bake_uv"] = uv_name
    return image


def _ensure_uv_layer(mesh, name):
    if name in mesh.uv_layers:
        mesh.uv_layers[name].active = True
        return
    render_names = [layer.name for layer in mesh.uv_layers if layer.active_render]
    mesh.uv_layers.new(name=name)
    for render_name in render_names:
        if render_name in mesh.uv_layers:
            mesh.uv_layers[render_name].active_render = True
    mesh.uv_layers[name].active = True


def _unwrap_object(context, obj, method):
    _set_selection(context, [obj])
    bpy.ops.object.mode_set(mode='EDIT')
    _call(context, bpy.ops.mesh.select_all, action='SELECT')
    if method == 'LIGHTMAP':
        _call(
            context,
            bpy.ops.uv.lightmap_pack,
            PREF_CONTEXT='SEL_FACES',
            PREF_PACK_IN_ONE=True,
            PREF_NEW_UVLAYER=False,
            PREF_BOX_DIV=12,
            PREF_MARGIN_DIV=_UV_PACK_MARGIN,
        )
    else:
        _call(
            context,
            bpy.ops.uv.smart_project,
            angle_limit=_SMART_ANGLE,
            island_margin=_UV_PACK_MARGIN,
            area_weight=0.0,
            correct_aspect=True,
            scale_to_bounds=False,
        )
    bpy.ops.object.mode_set(mode='OBJECT')


def _pack_group(context, objects, uv_name):
    for obj in objects:
        obj.data.uv_layers[uv_name].active = True
    _set_selection(context, objects)
    bpy.ops.object.mode_set(mode='EDIT')
    previous_sync = context.scene.tool_settings.use_uv_select_sync
    context.scene.tool_settings.use_uv_select_sync = True
    try:
        _call(context, bpy.ops.mesh.select_all, action='SELECT')
        _call(context, bpy.ops.uv.average_islands_scale)
        _call(
            context,
            bpy.ops.uv.pack_islands,
            rotate=False,
            scale=True,
            merge_overlap=False,
            margin_method='FRACTION',
            margin=_UV_PACK_MARGIN,
        )
    finally:
        context.scene.tool_settings.use_uv_select_sync = previous_sync
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')


def _add_object_nodes(obj, image, uv_name, preview):
    for slot in obj.material_slots:
        if slot.material is None:
            continue
        _add_bake_nodes(slot.material, image, uv_name, preview)


def _add_bake_nodes(material, image, uv_name, preview):
    tree = material.node_tree
    if tree is None:
        material.use_nodes = True
        tree = material.node_tree
    nodes = tree.nodes
    links = tree.links
    origin_x = max((node.location.x for node in nodes), default=-200.0) + 350.0

    uv_node = nodes.new("ShaderNodeUVMap")
    uv_node.label = "Bake UV"
    uv_node.location = (origin_x, 120.0)
    uv_node.uv_map = uv_name

    image_node = nodes.new("ShaderNodeTexImage")
    image_node.label = "Bake Image"
    image_node.location = (origin_x + 220.0, 300.0)
    image_node.image = image

    links.new(uv_node.outputs["UV"], image_node.inputs["Vector"])

    if preview:
        principled = nodes.new("ShaderNodeBsdfPrincipled")
        principled.label = "Bake Preview"
        principled.location = (origin_x + 520.0, 300.0)
        principled.inputs["Roughness"].default_value = 1.0
        principled.inputs["IOR"].default_value = 1.0
        # Leave this unplugged until the bake finishes. Plugging the target
        # image into the shader makes Cycles report a circular dependency.

    for node in nodes:
        node.select = False
    image_node.select = True
    nodes.active = image_node


def _active_output(nodes):
    for node in nodes:
        if node.type == 'OUTPUT_MATERIAL' and node.is_active_output:
            return node
    for node in nodes:
        if node.type == 'OUTPUT_MATERIAL':
            node.is_active_output = True
            return node
    output = nodes.new("ShaderNodeOutputMaterial")
    output.location = (1100.0, 300.0)
    return output


def _uv_names(objects):
    taken = set()
    for obj in objects:
        taken.update(obj.data.uv_layers.keys())
    return taken


def _unique_name(base, taken):
    if base not in taken:
        return base
    index = 1
    while True:
        candidate = f"{base}.{index:03d}"
        if candidate not in taken:
            return candidate
        index += 1


def _set_selection(context, objects):
    selected = {obj.as_pointer() for obj in objects}
    for obj in context.view_layer.objects:
        obj.select_set(obj.as_pointer() in selected)
    context.view_layer.objects.active = objects[0]


def _restore_selection(context, selected, active):
    visible = {obj.as_pointer(): obj for obj in context.view_layer.objects}
    for obj in context.view_layer.objects:
        obj.select_set(False)
    for obj in selected:
        found = visible.get(obj.as_pointer())
        if found is not None:
            found.select_set(True)
    if active is not None and active.as_pointer() in visible:
        context.view_layer.objects.active = visible[active.as_pointer()]


def _view3d_override(context):
    window = context.window or context.window_manager.windows[0]
    screen = window.screen
    for area in screen.areas:
        if area.type != 'VIEW_3D':
            continue
        for region in area.regions:
            if region.type == 'WINDOW':
                return {"window": window, "screen": screen, "area": area, "region": region}
    raise RuntimeError("Open a 3D View before creating bake UVs.")


def _call(context, operator, **kwargs):
    with context.temp_override(**_view3d_override(context)):
        result = operator(**kwargs)
    if 'CANCELLED' in result:
        raise RuntimeError("UV operator was cancelled")
    return result

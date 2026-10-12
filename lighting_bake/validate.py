import bpy

from .properties import sync_object_list

# Bake-button checks. This phase reports problems and does not change meshes or materials.

TESTING_WARNING = "This plugin is in testing. Save the file first. Results may not be perfect."

_MODE_LABELS = {
    'EDIT_MESH': "Edit Mode",
    'EDIT_CURVE': "Edit Mode",
    'EDIT_SURFACE': "Edit Mode",
    'EDIT_TEXT': "Edit Mode",
    'EDIT_ARMATURE': "Edit Mode",
    'EDIT_METABALL': "Edit Mode",
    'EDIT_LATTICE': "Edit Mode",
    'EDIT_CURVES': "Edit Mode",
    'EDIT_GREASE_PENCIL': "Edit Mode",
    'EDIT_POINT_CLOUD': "Edit Mode",
    'SCULPT': "Sculpt Mode",
    'SCULPT_CURVES': "Sculpt Mode",
    'POSE': "Pose Mode",
    'PAINT_WEIGHT': "Weight Paint",
    'PAINT_VERTEX': "Vertex Paint",
    'PAINT_TEXTURE': "Texture Paint",
    'PARTICLE': "Particle Edit",
}


class BakeCheck:
    def __init__(self):
        self.blocking = []
        self.warnings = []
        self.skipped = []
        self.targets = []

    @property
    def blocked(self):
        return bool(self.blocking)


def validate_bake(context):
    scene = context.scene
    check = BakeCheck()
    _leave_object_mode(context, check)

    settings = scene.lighting_bake
    sync_object_list(scene)
    _check_engine(scene, check)
    _check_file_path(settings, check)

    checked = _checked_meshes(settings)
    _skip_selected_non_meshes(context, checked, check)
    for obj in checked:
        _classify_mesh(obj, context.view_layer, check)

    if not check.targets:
        if checked or check.skipped:
            check.blocking.append("No meshes left to bake.")
        else:
            check.blocking.append("Check at least one mesh to bake.")

    if not check.blocked:
        _check_lighting(scene, context.view_layer, check)
        _warn_shared_meshes(check)
        _warn_shared_materials(check, scene.lighting_bake.bake_mode == 'INDIVIDUAL')
        _warn_zero_area(check)

    return check


def _leave_object_mode(context, check):
    if context.mode == 'OBJECT':
        return
    label = _MODE_LABELS.get(context.mode, context.mode.replace("_", " ").title())
    if context.active_object is not None:
        bpy.ops.object.mode_set(mode='OBJECT')
    check.warnings.append(f"Switched from {label} to Object Mode.")


def _check_engine(scene, check):
    if scene.render.engine == 'CYCLES':
        return
    label = _engine_label(scene)
    check.blocking.append(f"Set the render engine to Cycles. It is {label} now.")


def _engine_label(scene):
    engine = scene.render.engine
    engine_prop = scene.render.bl_rna.properties["engine"]
    items = getattr(engine_prop, "enum_items_static", engine_prop.enum_items)
    for item in items:
        if item.identifier == engine:
            return item.name
    return engine


def _check_file_path(settings, check):
    if bpy.data.filepath:
        return
    if settings.output_folder.strip():
        check.warnings.append("The file is not saved. PNGs will use the output folder you set.")
        return
    check.blocking.append(
        "Save the .blend, or set an output folder. An unsaved file has nowhere to put bakedLightingTextures."
    )


def _checked_meshes(settings):
    meshes = []
    for item in settings.mesh_items:
        if item.include and item.mesh is not None:
            meshes.append(item.mesh)
    return meshes


def _skip_selected_non_meshes(context, checked, check):
    checked_ids = {obj.as_pointer() for obj in checked}
    for obj in context.selected_objects:
        if obj is None or obj.as_pointer() in checked_ids or obj.type == 'MESH':
            continue
        check.skipped.append(f"{obj.name} is not a mesh, so it was skipped.")


def _classify_mesh(obj, view_layer, check):
    if obj.type != 'MESH':
        check.skipped.append(f"{obj.name} is not a mesh, so it was skipped.")
        return
    if obj.data is None or len(obj.data.polygons) == 0:
        check.skipped.append(f"{obj.name} has no faces, so it was skipped.")
        return
    if obj.hide_render:
        check.skipped.append(f"{obj.name} is hidden from render, so it was skipped.")
        return
    if view_layer.objects.get(obj.name) != obj:
        check.skipped.append(f"{obj.name} is not in the current view layer, so it was skipped.")
        return
    if not obj.visible_get():
        check.skipped.append(f"{obj.name} is hidden in the viewport, so it was skipped.")
        return
    check.targets.append(obj)


def _check_lighting(scene, view_layer, check):
    if _scene_has_light(scene, view_layer) or _world_contributes(scene):
        return
    check.warnings.append("No lights or world lighting found. The bake may come out black.")


def _scene_has_light(scene, view_layer):
    for obj in scene.objects:
        if obj.type != 'LIGHT' or obj.hide_render:
            continue
        if view_layer.objects.get(obj.name) == obj:
            return True
    return False


def _world_contributes(scene):
    world = scene.world
    if world is None:
        return False
    if not world.use_nodes or world.node_tree is None:
        return any(channel > 0.0 for channel in world.color[:3])

    for node in world.node_tree.nodes:
        if node.type != 'BACKGROUND':
            continue
        strength = node.inputs.get("Strength")
        color = node.inputs.get("Color")
        if strength is not None and strength.is_linked:
            return True
        strength_value = 1.0 if strength is None else strength.default_value
        if strength_value <= 0.0:
            continue
        if color is not None and color.is_linked:
            return True
        color_value = (1.0, 1.0, 1.0) if color is None else color.default_value
        if any(channel > 0.0 for channel in color_value[:3]):
            return True
    return False


def _warn_shared_meshes(check):
    seen = set()
    for obj in check.targets:
        data = obj.data
        if data is None or data.users <= 1 or data.as_pointer() in seen:
            continue
        seen.add(data.as_pointer())
        others = [
            other.name
            for other in bpy.data.objects
            if other != obj and getattr(other, "data", None) == data
        ]
        shared_with = ", ".join(others) if others else "another datablock"
        check.warnings.append(
            f"{obj.name} shares mesh data with {shared_with}. This run will make it single-user before unwrapping."
        )


def _warn_shared_materials(check, individual):
    seen = set()
    target_names = {obj.name for obj in check.targets}
    for obj in check.targets:
        for slot in obj.material_slots:
            material = slot.material
            if material is None or material.as_pointer() in seen:
                continue
            users = _mesh_users(material)
            if len(users) <= 1:
                continue
            outsiders = [name for name in users if name not in target_names]
            if not individual and not outsiders:
                continue
            seen.add(material.as_pointer())
            if individual:
                check.warnings.append(
                    f"Material {material.name} is on {', '.join(users)}. This run will give each baked mesh its own copy."
                )
            else:
                check.warnings.append(
                    f"Material {material.name} is on {', '.join(users)}. This run will copy it for the baked meshes so the others keep the original."
                )


def _mesh_users(material):
    users = []
    for obj in bpy.data.objects:
        if obj.type != 'MESH':
            continue
        for slot in obj.material_slots:
            if slot.material == material:
                users.append(obj.name)
                break
    return users


def _warn_zero_area(check):
    for obj in check.targets:
        mesh = obj.data
        if mesh is None:
            continue
        for poly in mesh.polygons:
            if poly.area <= 1e-8:
                check.warnings.append(f"{obj.name} has zero-area faces. The unwrap may look poor.")
                break

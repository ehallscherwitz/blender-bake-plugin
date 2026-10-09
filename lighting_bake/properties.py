import bpy

# Scene settings and the mesh checklist.


def object_list_is_current(scene):
    settings = scene.lighting_bake
    meshes = [obj for obj in scene.objects if obj.type == 'MESH']
    items = settings.mesh_items
    return len(items) == len(meshes) and all(item.mesh == obj for item, obj in zip(items, meshes))


def sync_object_list(scene):
    """Rebuild the checklist when meshes are added or removed. Keep checkbox state."""
    if object_list_is_current(scene):
        return

    settings = scene.lighting_bake
    meshes = [obj for obj in scene.objects if obj.type == 'MESH']
    items = settings.mesh_items

    include_by_id = {}
    for item in items:
        if item.mesh is not None:
            include_by_id[item.mesh.as_pointer()] = item.include

    items.clear()
    for obj in meshes:
        item = items.add()
        item.mesh = obj
        stored = include_by_id.get(obj.as_pointer())
        item.include = obj.select_get() if stored is None else stored

    if settings.mesh_index >= len(items):
        settings.mesh_index = max(0, len(items) - 1)


def checked_meshes(scene):
    sync_object_list(scene)
    meshes = []
    for item in scene.lighting_bake.mesh_items:
        if item.include and item.mesh is not None and item.mesh.type == 'MESH':
            meshes.append(item.mesh)
    return meshes


class LightingBakeObjectItem(bpy.types.PropertyGroup):
    mesh: bpy.props.PointerProperty(
        name="Mesh",
        type=bpy.types.Object,
    )
    include: bpy.props.BoolProperty(
        name="Include",
        description="Bake this mesh",
        default=False,
    )


class LightingBakeSettings(bpy.types.PropertyGroup):
    mesh_items: bpy.props.CollectionProperty(type=LightingBakeObjectItem)
    mesh_index: bpy.props.IntProperty(name="Active mesh", default=0)

    group_name: bpy.props.StringProperty(
        name="Group name",
        description="Name for the shared UV map and image when baking onto one map",
        default="Group",
    )
    bake_mode: bpy.props.EnumProperty(
        name="Mode",
        description="Bake each mesh on its own image, or pack the checked meshes onto one map",
        items=(
            ('INDIVIDUAL', "Individual", "Each mesh gets its own UV map and image"),
            ('ONE_MAP', "One map", "Checked meshes share one UV map and one image"),
        ),
        default='INDIVIDUAL',
    )
    resolution: bpy.props.EnumProperty(
        name="Resolution",
        description="Square size of the bake image",
        items=(
            ('512', "512", "512 × 512"),
            ('1024', "1024", "1024 × 1024"),
            ('2048', "2048", "2048 × 2048"),
            ('4096', "4096", "4096 × 4096"),
            ('8192', "8192", "8192 × 8192"),
        ),
        default='1024',
    )
    margin_px: bpy.props.IntProperty(
        name="Margin",
        description="Pixel margin around UV islands when baking",
        default=16,
        min=0,
        max=64,
    )
    unwrap_method: bpy.props.EnumProperty(
        name="Unwrap",
        description="How to build the new bake UV map",
        items=(
            ('SMART', "Smart UV Project", "Smart UV Project at 66° with a 0.01 pack margin"),
            ('LIGHTMAP', "Lightmap Pack", "Pack islands with Lightmap Pack"),
            ('KEEP', "Keep existing", "Leave UVs already on the bake map as they are"),
        ),
        default='SMART',
    )
    node_setup: bpy.props.EnumProperty(
        name="Shader",
        description="Leave the bake image unconnected, or preview it through a new Principled BSDF",
        items=(
            (
                'UNCONNECTED',
                "Unconnected",
                "Add the image node and leave it unconnected",
            ),
            (
                'PREVIEW',
                "Preview",
                "Connect the bake to a new Principled BSDF (IOR 1, roughness 1) and Material Output",
            ),
        ),
        default='UNCONNECTED',
    )
    output_folder: bpy.props.StringProperty(
        name="Output",
        description="Folder for PNG bakes. Empty uses bakedLightingTextures next to the .blend",
        default="",
        subtype='DIR_PATH',
        maxlen=1024,
    )

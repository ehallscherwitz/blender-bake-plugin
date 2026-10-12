import bpy

from .properties import object_list_is_current, sync_object_list
from .version import version_string

# Sidebar panel and the mesh checklist.


def schedule_object_sync(scene):
    if object_list_is_current(scene):
        return
    if bpy.app.timers.is_registered(run_object_sync):
        return
    bpy.app.timers.register(run_object_sync, first_interval=0.0)


def run_object_sync():
    for scene in bpy.data.scenes:
        if hasattr(scene, "lighting_bake"):
            sync_object_list(scene)
    return None


class LIGHTINGBAKE_UL_objects(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        row.prop(item, "include", text="")
        if item.mesh is not None:
            row.label(text=item.mesh.name, icon='MESH_DATA')
        else:
            row.label(text="Missing mesh", icon='ERROR')


class LIGHTINGBAKE_PT_main(bpy.types.Panel):
    bl_label = f"Lighting Bake {version_string()}"
    bl_idname = "LIGHTINGBAKE_PT_main"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Lighting Bake"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.lighting_bake
        schedule_object_sync(context.scene)

        layout.label(text="Bake a combined look onto a new UV map.")

        # Bake options.
        col = layout.column()
        col.use_property_split = True
        col.use_property_decorate = False
        col.prop(settings, "bake_mode")
        group_row = col.row()
        group_row.enabled = settings.bake_mode == 'ONE_MAP'
        group_row.prop(settings, "group_name")
        col.prop(settings, "resolution")
        col.prop(settings, "margin_px")
        col.prop(settings, "unwrap_method")
        col.prop(settings, "node_setup")
        col.prop(settings, "output_folder")

        if not settings.output_folder:
            layout.label(text="Empty saves to bakedLightingTextures beside the file.")

        # Mesh checklist.
        layout.separator()
        row = layout.row()
        row.template_list(
            "LIGHTINGBAKE_UL_objects",
            "",
            settings,
            "mesh_items",
            settings,
            "mesh_index",
            rows=4,
        )
        side = row.column(align=True)
        side.operator("lighting_bake.objects_all", text="", icon='CHECKBOX_HLT')
        side.operator("lighting_bake.objects_none", text="", icon='CHECKBOX_DEHLT')
        side.operator("lighting_bake.refresh_objects", text="", icon='FILE_REFRESH')

        checked = sum(1 for item in settings.mesh_items if item.include and item.mesh is not None)
        layout.label(text=f"{checked} checked")
        layout.operator("lighting_bake.bake", icon='RENDER_STILL')

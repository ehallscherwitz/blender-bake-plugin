import bpy

from .properties import checked_meshes, sync_object_list

# Operators for the checklist and the bake button.
# The bake operator only validates the checklist until a later phase.


class LIGHTINGBAKE_OT_bake(bpy.types.Operator):
    bl_idname = "lighting_bake.bake"
    bl_label = "Bake Lighting"
    bl_description = "Bake a combined lighting look onto a new UV map and save PNG textures"
    bl_options = {'REGISTER'}

    def execute(self, context):
        meshes = checked_meshes(context.scene)
        if not meshes:
            self.report({'WARNING'}, "Check at least one mesh to bake")
            return {'CANCELLED'}

        names = ", ".join(mesh.name for mesh in meshes)
        noun = "mesh" if len(meshes) == 1 else "meshes"
        self.report(
            {'INFO'},
            f"Checked {len(meshes)} {noun}: {names}. Baking is not implemented yet",
        )
        return {'FINISHED'}


class LIGHTINGBAKE_OT_objects_all(bpy.types.Operator):
    bl_idname = "lighting_bake.objects_all"
    bl_label = "Check All"
    bl_description = "Check every mesh in the list"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        sync_object_list(context.scene)
        for item in context.scene.lighting_bake.mesh_items:
            item.include = True
        return {'FINISHED'}


class LIGHTINGBAKE_OT_objects_none(bpy.types.Operator):
    bl_idname = "lighting_bake.objects_none"
    bl_label = "Check None"
    bl_description = "Uncheck every mesh in the list"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        sync_object_list(context.scene)
        for item in context.scene.lighting_bake.mesh_items:
            item.include = False
        return {'FINISHED'}


class LIGHTINGBAKE_OT_refresh_objects(bpy.types.Operator):
    bl_idname = "lighting_bake.refresh_objects"
    bl_label = "Refresh"
    bl_description = "Refresh the mesh checklist from the scene"
    bl_options = {'REGISTER'}

    def execute(self, context):
        sync_object_list(context.scene)
        return {'FINISHED'}

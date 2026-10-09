import textwrap

import bpy

from .properties import sync_object_list
from .validate import TESTING_WARNING, validate_bake

# Operators for the checklist and the bake button.
# The bake operator validates and stops. A later phase performs the bake.


def _wrap(text):
    lines = []
    for paragraph in text.split("\n"):
        if paragraph:
            lines.extend(textwrap.wrap(paragraph, width=68))
    return lines


class LIGHTINGBAKE_OT_bake(bpy.types.Operator):
    bl_idname = "lighting_bake.bake"
    bl_label = "Bake Lighting"
    bl_description = "Bake a combined lighting look onto a new UV map and save PNG textures"
    bl_options = {'REGISTER', 'UNDO'}

    validated: bpy.props.BoolProperty(options={'HIDDEN', 'SKIP_SAVE'})
    is_blocked: bpy.props.BoolProperty(options={'HIDDEN', 'SKIP_SAVE'})
    testing_text: bpy.props.StringProperty(default="", maxlen=4096, options={'HIDDEN', 'SKIP_SAVE'})
    blocking_text: bpy.props.StringProperty(default="", maxlen=4096, options={'HIDDEN', 'SKIP_SAVE'})
    warning_text: bpy.props.StringProperty(default="", maxlen=4096, options={'HIDDEN', 'SKIP_SAVE'})
    skip_text: bpy.props.StringProperty(default="", maxlen=4096, options={'HIDDEN', 'SKIP_SAVE'})
    ready_text: bpy.props.StringProperty(default="", maxlen=4096, options={'HIDDEN', 'SKIP_SAVE'})

    def invoke(self, context, event):
        self._apply(validate_bake(context))
        return context.window_manager.invoke_props_dialog(self, width=520)

    def execute(self, context):
        if not self.validated:
            self._apply(validate_bake(context))
        self._report()
        if self.is_blocked:
            return {'CANCELLED'}
        return {'FINISHED'}

    def draw(self, context):
        del context
        layout = self.layout
        col = layout.column(align=True)
        for line in _wrap(self.testing_text):
            col.label(text=line, icon='INFO')

        if self.blocking_text:
            box = layout.box()
            box.alert = True
            for paragraph in self.blocking_text.split("\n"):
                for line in _wrap(paragraph):
                    box.label(text=line, icon='ERROR')

        if self.warning_text:
            col = layout.column(align=True)
            for paragraph in self.warning_text.split("\n"):
                for line in _wrap(paragraph):
                    col.label(text=line, icon='ERROR')

        if self.skip_text:
            col = layout.column(align=True)
            for paragraph in self.skip_text.split("\n"):
                for line in _wrap(paragraph):
                    col.label(text=line, icon='INFO')

        if self.ready_text:
            layout.separator()
            for line in _wrap(self.ready_text):
                layout.label(text=line)

    def _apply(self, check):
        self.validated = True
        self.is_blocked = check.blocked
        self.testing_text = TESTING_WARNING
        self.blocking_text = "\n".join(check.blocking)
        self.warning_text = "\n".join(check.warnings)
        self.skip_text = "\n".join(check.skipped)
        if check.blocked:
            self.ready_text = ""
            return
        names = ", ".join(obj.name for obj in check.targets)
        noun = "mesh" if len(check.targets) == 1 else "meshes"
        self.ready_text = f"Ready to bake {len(check.targets)} {noun}: {names}. Baking is not implemented yet."

    def _report(self):
        self.report({'WARNING'}, self.testing_text)
        for paragraph in self.warning_text.split("\n"):
            if paragraph:
                self.report({'WARNING'}, paragraph)
        for paragraph in self.skip_text.split("\n"):
            if paragraph:
                self.report({'INFO'}, paragraph)
        if self.is_blocked:
            self.report({'ERROR'}, self.blocking_text.replace("\n", " "))
            return
        self.report({'INFO'}, self.ready_text)


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

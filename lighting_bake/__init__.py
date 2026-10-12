import bpy
from bpy.app.handlers import persistent

from .bake import clear_bake_session
from .operators import (
    LIGHTINGBAKE_OT_bake,
    LIGHTINGBAKE_OT_objects_all,
    LIGHTINGBAKE_OT_objects_none,
    LIGHTINGBAKE_OT_refresh_objects,
)
from .panel import LIGHTINGBAKE_PT_main, LIGHTINGBAKE_UL_objects, run_object_sync
from .properties import LightingBakeObjectItem, LightingBakeSettings, sync_object_list

bl_info = {
    "name": "Lighting Bake",
    "author": "Lighting Bake",
    "version": (0, 4, 2),
    "blender": (5, 1, 0),
    "location": "View3D > Sidebar > Lighting Bake",
    "description": "Bake a combined lighting look onto a new UV map and save PNG textures",
    "category": "Render",
}

# Register classes, scene settings, and list refresh handlers.

_CLASSES = (
    LightingBakeObjectItem,
    LightingBakeSettings,
    LIGHTINGBAKE_UL_objects,
    LIGHTINGBAKE_OT_bake,
    LIGHTINGBAKE_OT_objects_all,
    LIGHTINGBAKE_OT_objects_none,
    LIGHTINGBAKE_OT_refresh_objects,
    LIGHTINGBAKE_PT_main,
)


_syncing = False


def _on_depsgraph_update(scene, depsgraph):
    global _syncing
    del depsgraph
    if _syncing or scene is None or not hasattr(scene, "lighting_bake"):
        return
    _syncing = True
    try:
        sync_object_list(scene)
    finally:
        _syncing = False


@persistent
def _on_load_post(dummy):
    del dummy
    run_object_sync()


def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)

    bpy.types.Scene.lighting_bake = bpy.props.PointerProperty(type=LightingBakeSettings)

    if _on_depsgraph_update not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_on_depsgraph_update)
    if _on_load_post not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_on_load_post)


def unregister():
    clear_bake_session()
    if _on_depsgraph_update in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_on_depsgraph_update)
    if _on_load_post in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_on_load_post)

    if hasattr(bpy.types.Scene, "lighting_bake"):
        del bpy.types.Scene.lighting_bake

    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)

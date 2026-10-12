import os

import bpy

# Bake Combined lighting into the prepared images and save PNG files.
# Samples stay on the current Render settings.

_INVALID_FILENAME = '<>:"/\\|?*'


class BakeResult:
    def __init__(self):
        self.messages = []
        self.warnings = []
        self.saved = []
        # True while Cycles is still baking and this call has already returned.
        self.pending = False

    @property
    def ok(self):
        return self.pending or bool(self.saved)


# One bake queue. Blender only runs a single OBJECT_BAKE job at a time.
_session = None


def clear_bake_session():
    global _session
    _session = None
    for handlers, callback in (
        (bpy.app.handlers.object_bake_complete, _on_bake_complete),
        (bpy.app.handlers.object_bake_cancel, _on_bake_cancel),
    ):
        if callback in handlers:
            handlers.remove(callback)


def bake_prepared(context, jobs, report):
    global _session
    result = BakeResult()
    if _session is not None and not _session.finished:
        result.warnings.append("A bake is already running.")
        return result
    if not jobs:
        result.warnings.append("Nothing was prepared to bake.")
        return result

    folder = _output_directory(context.scene.lighting_bake)
    os.makedirs(folder, exist_ok=True)
    _session = _BakeSession(jobs, folder, context.scene.lighting_bake.margin_px)
    _ensure_handlers()
    if bpy.app.background:
        # Background mode runs the bake inside the call, so save before returning.
        _session.pump(context, report)
    else:
        # Leave the operator first. A bake started from inside it can still freeze the window.
        job = jobs[0]
        position = f"1/{len(jobs)}"
        result.messages.append(f"Baking {job.label} ({position}).")
        _set_status(context, f"Baking {job.label} ({position})")
        bpy.app.timers.register(_pump_session, first_interval=0.01)
    result.pending = not _session.finished
    result.messages.extend(_session.messages)
    result.warnings.extend(_session.warnings)
    result.saved.extend(_session.saved)
    if _session.finished:
        _session = None
    return result


class _BakeSession:
    def __init__(self, jobs, folder, margin_px):
        self.jobs = list(jobs)
        self.folder = folder
        self.margin_px = margin_px
        self.index = 0
        self.saved = []
        self.messages = []
        self.warnings = []
        self.finished = False
        self.launching = False
        self.job_settled = False
        self.timer_armed = False
        self.pending_kind = None
        self.summarized = False

    def pump(self, context, report):
        while self.index < len(self.jobs) and not self.finished:
            if self._launch(context, report) == 'async':
                job = self.jobs[self.index]
                _set_status(context, f"Baking {job.label} ({self.index + 1}/{len(self.jobs)})")
                return
        self._summarize()

    def _launch(self, context, report):
        job = self.jobs[self.index]
        position = f"{self.index + 1}/{len(self.jobs)}"
        self.job_settled = False
        self.pending_kind = None
        try:
            if context.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
            if not _activate_image_nodes(job):
                raise RuntimeError(f"{job.label} has no bake image node")
            _select_objects(context, job.objects)
            self.launching = True
            try:
                result = _start_bake_job(context, job, self.margin_px)
            finally:
                self.launching = False
        except RuntimeError as exc:
            self.warnings.append(f"{job.label} failed and was skipped: {_one_line(exc)}")
            self.index += 1
            return 'sync'

        if _bake_job_running():
            return 'async'

        if 'CANCELLED' in result:
            # A failed bake is skipped. The next mesh still runs.
            self.warnings.append(f"{job.label} failed and was skipped: bake was cancelled")
            self.index += 1
            return 'sync'

        self._store_current(context, report, position)
        self.index += 1
        return 'sync'

    def _store_current(self, context, report, position):
        job = self.jobs[self.index]
        try:
            path = _save_png(job.image, self.folder, context.scene)
            _connect_preview(job)
        except RuntimeError as exc:
            self.warnings.append(f"{job.label} failed and was skipped: {_one_line(exc)}")
            return
        self.saved.append(path)
        done_message = f"Baked {job.label} ({position})"
        _set_status(context, done_message)
        _tell(report, 'INFO', done_message)
        _tell(report, 'INFO', f"Saved {os.path.basename(path)}")

    def _summarize(self):
        if self.summarized:
            return
        self.summarized = True
        self.finished = True
        if self.saved:
            noun = "file" if len(self.saved) == 1 else "files"
            self.messages.append(f"Saved {len(self.saved)} PNG {noun} to {self.folder}.")
        elif not any("cancelled" in warning for warning in self.warnings):
            self.warnings.append("No PNG files were saved.")

    def _finish_from_job(self, kind):
        if self.finished or self.job_settled or self.index >= len(self.jobs):
            return
        self.job_settled = True
        context = bpy.context
        if kind == 'cancel':
            # Esc stops the queue. A per-object error does not.
            job = self.jobs[self.index]
            self.warnings.append(f"{job.label} was cancelled. Remaining meshes were not baked.")
            self._summarize()
            _set_status(context, None)
            _popup(self.messages, self.warnings)
            return
        position = f"{self.index + 1}/{len(self.jobs)}"
        self._store_current(context, None, position)
        self.index += 1
        try:
            self.pump(context, None)
        except RuntimeError as exc:
            self.warnings.append(str(exc))
            self._summarize()
        if self.finished:
            _set_status(context, None)
            _popup(self.messages, self.warnings)


def _pump_session():
    session = _session
    if session is None or session.finished:
        return None
    try:
        session.pump(bpy.context, None)
    except RuntimeError as exc:
        session.warnings.append(str(exc))
        session._summarize()
    if session is _session and session.finished:
        _set_status(bpy.context, None)
        _popup(session.messages, session.warnings)
    return None


def _ensure_handlers():
    if _on_bake_complete not in bpy.app.handlers.object_bake_complete:
        bpy.app.handlers.object_bake_complete.append(_on_bake_complete)
    if _on_bake_cancel not in bpy.app.handlers.object_bake_cancel:
        bpy.app.handlers.object_bake_cancel.append(_on_bake_cancel)


def _on_bake_complete(*_args):
    _schedule_job_end('complete')


def _on_bake_cancel(*_args):
    _schedule_job_end('cancel')


def _schedule_job_end(kind):
    session = _session
    if session is None or session.launching or session.finished:
        return
    if kind == 'cancel':
        session.pending_kind = 'cancel'
    elif session.pending_kind != 'cancel':
        session.pending_kind = 'complete'
    if session.timer_armed:
        return
    session.timer_armed = True
    bpy.app.timers.register(_on_bake_timer, first_interval=0.05)


def _on_bake_timer():
    session = _session
    if session is None:
        return None
    session.timer_armed = False
    kind = session.pending_kind
    session.pending_kind = None
    if kind is not None:
        session._finish_from_job(kind)
    return None


def _bake_job_running():
    return bpy.app.is_job_running('OBJECT_BAKE')


def _start_bake_job(context, job, margin_px):
    # Invoke, matching the Bake button. Exec would freeze the window until Cycles finishes.
    # Samples stay on the current Render settings.
    context.scene.cycles.bake_type = 'COMBINED'
    with context.temp_override(**_view3d_override(context)):
        return bpy.ops.object.bake(
            'INVOKE_DEFAULT',
            type='COMBINED',
            margin=margin_px,
            margin_type='ADJACENT_FACES',
            use_clear=True,
            use_selected_to_active=False,
            target='IMAGE_TEXTURES',
            save_mode='INTERNAL',
            uv_layer=job.uv_name,
        )


def _one_line(exc):
    text = " ".join(str(exc).split())
    if text.startswith("Error: "):
        text = text[len("Error: "):]
    return text or "the bake failed"


def _tell(report, level, text):
    if report is not None:
        report({level}, text)
    else:
        print(text)


def _popup(messages, warnings):
    lines = list(messages) + list(warnings)
    if not lines:
        return

    def draw(self, context):
        del context
        column = self.layout.column(align=True)
        for line in lines:
            column.label(text=line)

    window_manager = getattr(bpy.context, "window_manager", None)
    if window_manager is None:
        return
    try:
        window_manager.popup_menu(draw, title="Lighting Bake", icon='INFO')
    except RuntimeError:
        print("\n".join(lines))


def _activate_image_nodes(job):
    found = False
    for obj in job.objects:
        for slot in obj.material_slots:
            material = slot.material
            if material is None or material.node_tree is None:
                continue
            image_node = None
            for node in material.node_tree.nodes:
                if node.type == 'TEX_IMAGE' and node.image == job.image:
                    image_node = node
            if image_node is None:
                continue
            for node in material.node_tree.nodes:
                node.select = False
            image_node.select = True
            material.node_tree.nodes.active = image_node
            found = True
    return found


def _save_png(image, folder, scene):
    path = _unique_png(folder, _filename_stem(image.name))
    settings = scene.render.image_settings
    view = scene.view_settings
    previous = (
        settings.file_format,
        settings.color_mode,
        settings.color_depth,
        settings.compression,
        view.view_transform,
        view.look,
    )
    try:
        settings.file_format = 'PNG'
        settings.color_mode = 'RGB'
        settings.color_depth = '8'
        settings.compression = 15
        view.view_transform = 'Standard'
        view.look = 'None'
        # Assigning filepath before this would replace the bake with a blank generated image.
        image.save_render(path, scene=scene)
    finally:
        (
            settings.file_format,
            settings.color_mode,
            settings.color_depth,
            settings.compression,
            view.view_transform,
            view.look,
        ) = previous
    image.filepath_raw = path
    image.file_format = 'PNG'
    image.source = 'FILE'
    image.colorspace_settings.name = 'sRGB'
    image.reload()
    return path


def _connect_preview(job):
    for obj in job.objects:
        for slot in obj.material_slots:
            material = slot.material
            tree = None if material is None else material.node_tree
            if tree is None:
                continue
            preview = None
            for node in tree.nodes:
                if node.type != 'BSDF_PRINCIPLED' or node.label != 'Bake Preview':
                    continue
                if node.inputs['Base Color'].is_linked:
                    continue
                preview = node
            image_node = None
            for node in tree.nodes:
                if node.type == 'TEX_IMAGE' and node.image == job.image:
                    image_node = node
            if preview is None or image_node is None:
                continue
            tree.links.new(image_node.outputs['Color'], preview.inputs['Base Color'])
            surface = _material_output(tree).inputs['Surface']
            for link in list(surface.links):
                tree.links.remove(link)
            tree.links.new(preview.outputs['BSDF'], surface)


def _material_output(tree):
    for node in tree.nodes:
        if node.type == 'OUTPUT_MATERIAL' and node.is_active_output:
            return node
    for node in tree.nodes:
        if node.type == 'OUTPUT_MATERIAL':
            node.is_active_output = True
            return node
    return tree.nodes.new('ShaderNodeOutputMaterial')


def _output_directory(settings):
    chosen = settings.output_folder.strip()
    if chosen:
        return bpy.path.abspath(chosen)
    blend_dir = os.path.dirname(bpy.path.abspath(bpy.data.filepath))
    return os.path.join(blend_dir, "bakedLightingTextures")


def _filename_stem(name):
    cleaned = "".join("_" if char in _INVALID_FILENAME else char for char in name).rstrip(" .")
    return cleaned or "Bake"


def _unique_png(folder, stem):
    candidate = os.path.join(folder, f"{stem}.png")
    if not os.path.exists(candidate):
        return candidate
    index = 1
    while True:
        candidate = os.path.join(folder, f"{stem}.{index:03d}.png")
        if not os.path.exists(candidate):
            return candidate
        index += 1


def _select_objects(context, objects):
    chosen = {obj.as_pointer() for obj in objects}
    for obj in context.view_layer.objects:
        obj.select_set(obj.as_pointer() in chosen)
    context.view_layer.objects.active = objects[0]


def _set_status(context, text):
    workspace = getattr(context, "workspace", None)
    if workspace is not None:
        workspace.status_text_set(text)


def _view3d_override(context):
    window = context.window or context.window_manager.windows[0]
    screen = window.screen
    for area in screen.areas:
        if area.type != 'VIEW_3D':
            continue
        for region in area.regions:
            if region.type == 'WINDOW':
                return {"window": window, "screen": screen, "area": area, "region": region}
    raise RuntimeError("Open a 3D View before baking.")

# Memory — lighting bake addon

Source of truth for later sessions. Do not treat `README.md` as the spec.

Product: a Blender addon that bakes a **Combined** look (color + lighting in one texture) onto a **new UV map**, saves **PNG (sRGB)**, and leaves the original shader nodes in place. The result should look lit in an unlit viewer. This is not a lightmap.

---

## Locked decisions

1. **What the bake writes.** Fully baked Combined. One texture carries albedo and lighting. Original materials stay in the node tree. The bake lives on a new UV map and a new image. Do not build a lighting-only lightmap in v1.

2. **What gets baked.** A mini UI lists objects the user checks. A switch chooses:
   - **Individual** — each object gets its own UV map and its own image.
   - **One map** — every checked object shares one UV map name and one image (atlas).

3. **What happens in the shader.** Always create the blank image and an Image Texture node, and make that node the active bake target in every material that will bake. The user picks what else happens:
   - **Unconnected** — drop the node in the tree and do not wire it. Original look is unchanged.
   - **Preview** — add a new Principled BSDF (IOR 1, roughness 1), feed the baked image into Base Color, and connect that Principled to Material Output. Original nodes stay; only the output connection changes so the user can see the bake.

4. **Multiple materials, no merging.** Do not merge albedo maps. Cycles Combined already evaluates the shader.
   - Several materials on one object: one shared bake image, and an Image Texture node (active) in **each** material.
   - Several objects sharing one material, **individual** mode: each object gets its own image. That means the shared material must be made single-user (duplicate) so one object’s image does not overwrite another’s.
   - **One map** mode: one image for the whole set. Still put the node in each material. Duplicate a material if something **outside** the set still uses it, so outsiders are not retargeted.

---

## Naming

| Thing | Individual | One map |
| --- | --- | --- |
| UV map | `{objectName}LightingBaked` | `{groupName}LightingBaked` |
| Image | `{objectName}LightingBakedTexture` | `{groupName}LightingBakedTexture` |
| File | same name + `.png` in `bakedLightingTextures` | same |

- Group name comes from a text field on the panel (the set is the checked objects, not a Blender collection).
- If a file or datablock name is taken, append `.001`, `.002`, and so on. Never overwrite.
- Do not reuse or replace an existing UV layer with the planned name unless the user explicitly chooses that. Default is a new name with the suffix above.
- Folder: `bakedLightingTextures` next to the `.blend` when the file is saved.

---

## UV and bake target

- New UV only. Do not delete or rename existing UV maps.
- Default unwrap: Smart UV Project, angle limit 66°, pack margin 0.01. Panel should still offer unwrap method: Smart UV Project, Lightmap Pack, or keep existing UVs on the bake map (user already unwrapped).
- Islands on a bake map must not overlap. Overlap is a pack bug.
- Pixel bake margin is separate from the UV pack margin. Freeze a default (16 px) and expose it. Without it, seams show up.
- One-map bakes: scale islands by mesh surface area before packing so a small prop does not eat the atlas and a large mesh does not go muddy.
- Create the image first. Add an Image Texture node in each participating material. Set that node active, then call bake. The addon selects the node; the user should not have to.
- One-map: every object in the set uses that same image.
- Image color space: sRGB. Format: PNG.

---

## Bake settings

- Engine must be Cycles. Bake type is always Combined. Do not follow whatever bake type happens to be selected in the UI.
- Samples, denoising, and the rest of the render sampling setup: use the current Render properties. Do not silently force 4096.
- Self-bake only (lighting on the same mesh). No selected-to-active, cage, or high-to-low in v1.
- Clear the image before baking it.
- Exit Edit Mode before baking if the user is not already in Object Mode, and say that we did. Baking from Edit Mode is a footgun. Prefer a clear warning if they are not in Object Mode.

---

## Warnings and skips

Warnings are obvious (popup or a loud report the user cannot miss). Skips do not abort the rest of the job.

**Clear warning, do not bake, when:**

- Render engine is Eevee, Workbench, or anything other than Cycles.
- File has never been saved and there is no output folder. Tell them to save. Plugin is in testing; results may not be perfect even after a save — show that testing warning whenever a bake starts.
- Nothing usable is checked.

**Warn, then continue or fix, when:**

- Not in Object Mode: warn, switch to Object Mode, then continue.
- No lights and no world contribution: warn that the bake may come out black.
- Object is hidden from render, or excluded from the view layer: warn and skip.
- Mesh data is shared with another object (`data.users > 1`): make the mesh single-user before adding or unwrapping the bake UV, and report that. An unwrap on linked duplicates would change every user.
- A material is shared and we duplicate it so images stay per object (or so outsiders are not affected): report that.

**Skip with a non-blocking message (keep going):**

- Non-mesh objects.
- Meshes with no faces, or empty mesh data.
- Zero-area faces: warn; do not crash. Unwrap may be poor.

---

## Progress

Constant feedback for the whole job, similar to Blender’s own bake:

- A percentage bar for the set (object index / count, and stage: validate, UV, bake, save).
- A status message when each object starts and when it finishes (`Baking Chair (2/5)`).
- Cycles’ own progress can show during a single `bake()` call. Between objects the addon must update the bar and the message so a multi-object job is not silent.
- One 4k Combined bake is slow. Do not hide that behind a frozen UI with no text.

---

## Shader details (preview mode)

When the user chooses preview:

- New Principled BSDF, not a rewrite of the existing one.
- Base Color = baked Image Texture (vector from the new UV map).
- IOR = 1, roughness = 1.
- That Principled’s output goes to Material Output.
- Leave every pre-existing node where it is. The user can plug the old shader back into Material Output later.
- Unconnected mode: Image Texture + UV Map node only, image node active, nothing linked to Material Output.

Image node must use the new UV map (UV Map node or the image node’s UV input). Do not sample the bake with the original UV.

---

## v1 supports

- Checked mesh objects, Object Mode, Cycles.
- Individual or one shared map.
- New UV, new blank image, active Image Texture node per material.
- Multi-material objects (shared image, node in each slot).
- Shared materials (duplicate so images stay correct).
- Shared mesh datablocks (make single-user before UV edits).
- Name collisions via `.001`.
- PNG, sRGB, folder `bakedLightingTextures`.
- Progress bar and per-object messages.

## Explicitly not v1

Leave these out of the bake operator. A short note in a future README is enough; do not put a tutorial in the panel.

- Lightmaps, second-UV lighting multiply, Three.js export.
- Merging stacked albedo textures.
- UDIM.
- Geometry Nodes / baking the evaluated mesh vs the original.
- Instanced collections.
- Transparency and alpha hashed.
- Volumes.
- Animated lighting (current frame only if they bake; do not advertise animation support).
- High-poly to low-poly cage bake.
- OpenEXR / HDR, denoising as its own feature, KTX2, Draco.
- Publishing, `blender_manifest.toml`, and install docs (later; user asked not to edit `README.md` yet).

Panel copy: one line on the operator. Options stay on the panel (object checklist, individual vs one map, resolution, margin px, unwrap method, preview vs unconnected, output folder).

---

## Notes for later sessions

- **Active node is per material.** `bpy.ops.object.bake()` writes to the selected Image Texture in each material slot. Selecting it on only the first slot leaves the other slots empty or writing at the wrong target.
- **Shared material is the highest-risk bug.** Image nodes live on the material. Individual mode cannot put two images on one shared material. Duplicate first, then add the node.
- **Shared mesh is the other high-risk bug.** UV layers live on the mesh. `object.data.copy()` (single-user) before creating `{name}LightingBaked` if `users > 1`.
- **Group name typo in the old README** (`grougName`) is wrong. Use `groupName` from the panel field.
- **“Original materials left untouched”** means do not delete or rewire existing shader nodes. Preview mode is allowed to move the Material Output link to the new Principled. Unconnected mode does not.
- **Do not follow the Render bake type.** Combined is locked. Sampling still comes from Render.
- **Texel density** on one-map bakes matters as much as the unwrap operator. Equal pack of a crate and a building looks wrong. Scale by area, then pack.
- **Lightmap Pack** is the fallback when Smart UV Project looks bad. Keep-existing is the other fallback. Do not auto-merge textures to “fix” a bad unwrap.
- **Three.js, when it exists, is a second operator.** This addon only has to guarantee a new UV, a saved Combined PNG, and a known node setup. Export (glTF, unlit or emissive so the engine does not relight, apply scale) is separate.
- **Unsaved .blend:** no directory beside the file. Warning plus block until they save or pick a folder.
- **Testing warning** on every bake start: save first; plugin is in testing; results may not be perfect.
- Target Blender when packaging later: check the user’s installed version before writing `bl_info` / extension manifest. Do not guess now.
- Addon layout when implementation starts (not created yet): package folder, `__init__.py` with `bl_info`, panel, properties, one bake operator. Short comments per section. No README edits unless the user asks.

---

## Implementation plan

Each phase is shippable inside Blender. Stop and test before the next phase. Do not code phase N+1 while phase N is still wrong.

### Phase 1 — Addon shows up

- Installable addon, panel in the 3D View sidebar.
- Properties: object checklist (scene meshes, checkboxes), group name, individual vs one map, resolution, margin px, unwrap method, preview vs unconnected, output folder.
- Operator button with one description line. Button can no-op except validation.

**Test:** enable the addon, open the panel, toggle every control, disable the addon and confirm it unregisters cleanly.

### Phase 2 — Validation only

- Cycles check with a blocking warning.
- Unsaved-file warning.
- Testing warning.
- Object Mode warning; switch to Object Mode if they confirm or if we auto-switch (auto-switch plus message is the default).
- Skip non-meshes and empty meshes with a message; list what was skipped.
- Warn on hide-render and on shared mesh / shared material (do not duplicate yet).

**Test:** Eevee scene (must refuse). Unsaved file (must warn). Empty + camera + mesh selected (camera skipped, mesh kept). Edit Mode (warned, returned to Object Mode). No crash.

### Phase 3 — UV, image, nodes (no bake)

- Individual: create UV `{object}LightingBaked`, image `{object}LightingBakedTexture`, UV Map node + Image Texture, set active.
- One map: one image, same UV name on each object, node in every material.
- Duplicate shared materials and make shared meshes single-user before UV work.
- Unwrap with the chosen method. One-map: scale islands by area, then pack. Margin 0.01 UV, and record the pixel margin for later.
- Collision names get `.001`.
- Preview vs unconnected matches the spec. Do not delete old nodes.

**Test:** one mesh, two materials. Confirm both materials have an active Image Texture on the new UV, image is blank, old Principled still exists. Second object sharing the material: individual mode must not point both at one image. Run twice: second run must not overwrite the first image name. Switch preview on and off.

### Phase 4 — Individual Combined bake + save

- Set Cycles Combined, clear image, margin px, samples from Render.
- Bake each mesh. Progress percent and `Baking {name} (i/n)` before and after each object.
- Save PNG sRGB into `bakedLightingTextures`. `.001` if the file exists.
- Skip failures per object; finish the rest.

**Test:** one lit mesh, then three meshes. Watch the bar and the per-object message. Open the PNG. Confirm sRGB and that a second bake writes `.001`. Compare viewport preview mode to the lit render. Unconnected mode: original viewport look unchanged, image still filled.

### Phase 5 — One map

- Same pipeline, one image, all checked objects.
- Area-weighted islands, no overlaps, pixel margin.
- Shared image node on each material.

**Test:** small object + large object. The large one should get more pixels. Seams at the margin should be thin, not black. An object left unchecked must not appear on the image and must not gain the bake node if it did not already share a material (if it shared, the duplicate should protect it).

### Phase 6 — Failure pass

- Linked duplicate meshes.
- Object with zero-area faces.
- Hidden mesh in the checklist.
- Multi-material + one map together.
- Cancel or error on object 2 of 4 still saves object 1 and continues or stops cleanly with a message (pick one behavior and keep it: **continue after a per-object failure, abort the whole job only for Cycles / no output folder / empty list**).

**Test:** the cases above. No silent overwrite, no crash, warnings readable.

After phase 6, v1 is usable. Three.js export, EXR, and publishing stay out until the user asks.

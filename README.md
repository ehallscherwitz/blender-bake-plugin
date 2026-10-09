Blender Plugin For Lighting Baking Plan

For individual item lighting bake:
Give each object new uv map called:
	nameLightingBaked

For group lighting bake (multiple on one texture map):
	grougNameLightingBaked

In the objects texture nodes,
Assign the new UV map to a blank texture called nameLightingBakedTexture for individual or groupNameLightingBakedTexture

For this new uv map:
Do the auto unwrap 66* and fit with .01 margin

Bake all the lighting automatically

Save all of the image textures in blender (saved to folder called bakedLightingTextures)

Options:
Bake all to one texture
Bake each selected item individually
Texture size selection
Options on how to unwrap and uv pack (could be auto with better logic)

All of this should be able to be done in a simple UI in blender with the options available and a quick descriptor of what it does

Default bake settings: Whatever you have selected in render

Let me know if theres any clarification on the process before starting.
Create a simple read me. Keep short comments on what section of the code does what
Publish the plugin with specific instructions

special cases:
what if an object contains multiple textures?
what if smart project doesn't apply well here?

If an object contains multiple textures on top of each other, merge them together.

To expand it: entire scene to three.js pipeline
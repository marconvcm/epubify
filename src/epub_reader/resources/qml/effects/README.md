# Native page effects

The BookPage item displays an application-owned page image in the Qt Quick scene
graph. Page layout and rasterization use QTextDocument/QPainter on the CPU; native
QML animates the composed texture. Current transitions are a short fade and slide.

Future page curls can use cached previous/next images, ShaderEffectSource and a
mesh/shader. Preserve high-DPI resolution and an instant/reduced-motion path.
Measure rasterization, image upload and full-screen effect costs first. Selection
and accessibility must remain usable while adding decorative effects.

Compile future GLSL sources with the matching Qt Shader Tools:

```sh
qsb --glsl "100 es,120,150" --hlsl 50 --msl 12 -o page.frag.qsb page.frag
```

Use Qt uniform-block/input conventions; include compiled .qsb assets in package
data so users do not need a compiler. Test relevant OpenGL/Vulkan, Metal and
Direct3D backends. No curl shader or elaborate effect engine is implemented yet.

"""Generate the Windows icon from Truecell's simple vector brand geometry."""

from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 256
image = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
draw = ImageDraw.Draw(image)
draw.rounded_rectangle((8, 8, 248, 248), radius=62, fill="#087f78")

width = 12
draw.rectangle((65, 72, 191, 176), outline="white", width=width)
draw.line((65, 112, 191, 112), fill="white", width=width)
draw.line((112, 72, 112, 176), fill="white", width=width)
draw.line((137, 143, 158, 164, 203, 111), fill="#b5f2dc", width=17, joint="curve")

target = Path(__file__).with_name("truecell.ico")
image.save(
    target,
    format="ICO",
    sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
)
print(target)

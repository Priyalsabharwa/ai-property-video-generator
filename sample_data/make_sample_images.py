"""Generate 6 synthetic 'property photos' (stylised illustrations) for demo/testing.

No real photos or customer data are used. Run:  python sample_data/make_sample_images.py
"""
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

W, H = 1600, 1000
OUT = Path(__file__).parent / "images"
random.seed(7)


def vgrad(top, bottom, w=W, h=H):
    g = Image.linear_gradient("L").resize((w, h))
    return Image.composite(Image.new("RGB", (w, h), bottom), Image.new("RGB", (w, h), top), g)


def finish(im: Image.Image, name: str):
    noise = Image.effect_noise((W, H), 12).convert("RGB")
    im = Image.blend(im.filter(ImageFilter.GaussianBlur(1.2)), noise, 0.04)
    im.save(OUT / name, quality=92)


def exterior():
    im = vgrad((120, 175, 235), (235, 225, 205))
    d = ImageDraw.Draw(im)
    d.ellipse((1150, 90, 1250, 190), fill=(255, 240, 190))
    d.rectangle((0, 780, W, H), fill=(95, 130, 85))
    d.rectangle((0, 840, W, 900), fill=(70, 70, 78))
    d.rectangle((420, 160, 1180, 800), fill=(226, 214, 196))
    for r in range(7):
        for c in range(5):
            x, y = 470 + c * 140, 200 + r * 86
            d.rectangle((x, y, x + 80, y + 54), fill=(70, 110, 150))
            d.rectangle((x - 6, y + 54, x + 86, y + 62), fill=(190, 178, 160))
    d.rectangle((740, 700, 860, 800), fill=(110, 80, 55))
    for x in (250, 1330):
        d.rectangle((x, 640, x + 16, 790), fill=(90, 65, 40))
        d.ellipse((x - 70, 520, x + 86, 680), fill=(60, 130, 70))
    finish(im, "01_exterior.jpg")


def living():
    im = vgrad((238, 230, 218), (214, 196, 170))
    d = ImageDraw.Draw(im)
    d.rectangle((0, 700, W, H), fill=(168, 128, 92))
    d.rectangle((900, 140, 1480, 600), fill=(150, 200, 240))
    d.line((1190, 140, 1190, 600), fill=(250, 250, 250), width=10)
    d.rectangle((900, 140, 1480, 600), outline=(250, 250, 250), width=12)
    d.rounded_rectangle((180, 520, 860, 760), 40, fill=(70, 100, 130))
    d.rounded_rectangle((180, 440, 860, 580), 40, fill=(85, 118, 150))
    d.rounded_rectangle((300, 800, 740, 880), 30, fill=(120, 90, 65))
    d.rectangle((1120, 640, 1160, 780), fill=(60, 60, 60))
    d.ellipse((1070, 520, 1210, 660), fill=(250, 220, 140))
    finish(im, "02_living_room.jpg")


def bedroom():
    im = vgrad((226, 220, 235), (200, 190, 210))
    d = ImageDraw.Draw(im)
    d.rectangle((0, 720, W, H), fill=(150, 118, 92))
    d.rounded_rectangle((300, 420, 1100, 780), 30, fill=(245, 245, 250))
    d.rounded_rectangle((300, 300, 1100, 470), 30, fill=(120, 90, 130))
    d.rounded_rectangle((340, 470, 700, 560), 24, fill=(255, 255, 255))
    d.rounded_rectangle((720, 470, 1060, 560), 24, fill=(255, 255, 255))
    d.rectangle((1180, 460, 1300, 780), fill=(130, 100, 80))
    d.ellipse((1190, 380, 1290, 470), fill=(250, 220, 140))
    d.rectangle((1360, 100, 1560, 560), fill=(160, 205, 240))
    finish(im, "03_bedroom.jpg")


def kitchen():
    im = vgrad((240, 238, 232), (220, 214, 204))
    d = ImageDraw.Draw(im)
    d.rectangle((0, 760, W, H), fill=(185, 170, 150))
    d.rectangle((100, 120, 1500, 340), fill=(70, 90, 80))
    for x in range(100, 1500, 200):
        d.rectangle((x + 6, 126, x + 194, 334), outline=(110, 130, 118), width=5)
    d.rectangle((100, 520, 1500, 760), fill=(60, 80, 70))
    d.rectangle((100, 490, 1500, 530), fill=(235, 235, 235))
    d.rectangle((600, 380, 900, 480), fill=(40, 40, 44))
    d.rectangle((1060, 440, 1180, 490), fill=(170, 175, 180))
    d.rectangle((1110, 400, 1130, 450), fill=(170, 175, 180))
    d.rectangle((300, 820, 1300, 900), fill=(205, 205, 205))
    finish(im, "04_kitchen.jpg")


def balcony():
    im = vgrad((250, 170, 110), (120, 150, 210))
    d = ImageDraw.Draw(im)
    random.seed(3)
    x = 0
    while x < W:
        w, h = random.randint(70, 150), random.randint(180, 420)
        d.rectangle((x, 640 - h, x + w, 640), fill=(60 + random.randint(0, 25),) * 2 + (95,))
        x += w + 6
    d.rectangle((0, 640, W, H), fill=(120, 110, 105))
    d.rectangle((0, 560, W, 580), fill=(35, 35, 40))
    for x in range(40, W, 90):
        d.rectangle((x, 580, x + 8, 900), fill=(35, 35, 40))
    d.rectangle((0, 900, W, H), fill=(95, 88, 85))
    d.ellipse((1180, 250, 1380, 450), fill=(255, 215, 150))
    finish(im, "05_balcony.jpg")


def entrance():
    im = vgrad((150, 190, 235), (200, 205, 195))
    d = ImageDraw.Draw(im)
    d.rectangle((0, 760, W, H), fill=(80, 82, 90))
    for x in range(100, W, 400):
        d.rectangle((x, 880, x + 200, 900), fill=(235, 235, 235))
    d.rectangle((200, 300, 280, 760), fill=(200, 190, 175))
    d.rectangle((1320, 300, 1400, 760), fill=(200, 190, 175))
    d.rectangle((200, 280, 1400, 340), fill=(185, 120, 70))
    d.rectangle((560, 640, 760, 760), fill=(60, 120, 180))
    d.rounded_rectangle((520, 600, 800, 700), 30, fill=(70, 135, 195))
    d.ellipse((560, 720, 620, 780), fill=(30, 30, 30))
    d.ellipse((720, 720, 780, 780), fill=(30, 30, 30))
    d.rectangle((1000, 560, 1140, 760), fill=(110, 110, 120))
    finish(im, "06_entrance_parking.jpg")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for fn in (exterior, living, bedroom, kitchen, balcony, entrance):
        fn()
    print("Wrote", len(list(OUT.glob('*.jpg'))), "images to", OUT)

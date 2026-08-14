from PIL import Image

from capture import make_bbox, sample_pixel, sample_points


def test_make_bbox_pads_points():
    bbox = make_bbox([(10, 20), (30, 40)], pad=2)
    assert bbox == (8, 18, 32, 42)


def test_make_bbox_single_point():
    bbox = make_bbox([(100, 100)], pad=0)
    assert bbox == (100, 100, 101, 101)


def test_sample_pixel():
    img = Image.new("RGB", (4, 4), (1, 2, 3))
    assert sample_pixel(img, 2, 2) == (1, 2, 3)


def test_sample_points_relative():
    img = Image.new("RGB", (10, 10), (0, 0, 0))
    img.putpixel((2, 3), (255, 0, 0))
    img.putpixel((5, 6), (0, 255, 0))
    colors = sample_points(img, [(2, 3), (5, 6)])
    assert colors == [(255, 0, 0), (0, 255, 0)]

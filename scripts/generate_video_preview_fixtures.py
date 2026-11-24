"""Generate deterministic detailed H.264 clips with long GOPs for preview qualification."""
from __future__ import annotations

import argparse
import json
import random
from fractions import Fraction
from pathlib import Path

import av
from PIL import Image, ImageDraw


def repeat_clip(source: Path, directory: Path, count: int):
    """Remux complete GOPs without re-encoding to exercise long-video cache policy."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f'{source.stem}-repeat{count}.mp4'
    if path.exists():
        raise FileExistsError(path)
    with av.open(str(source)) as template, av.open(str(path), 'w') as output:
        video = template.streams.video[0]
        target = output.add_stream_from_template(video)
        duration = video.duration
        for index in range(count):
            with av.open(str(source)) as clip:
                for packet in clip.demux(video=0):
                    if packet.dts is None:
                        continue
                    packet.pts += index * duration
                    packet.dts += index * duration
                    packet.stream = target
                    output.mux(packet)
    print(json.dumps({'path': str(path.resolve()), 'bytes': path.stat().st_size,
                      'repetitions': count, 'source': str(source.resolve())}))


def generate(directory: Path, sizes, seconds=12, fps=30, gop=120):
    directory.mkdir(parents=True, exist_ok=True)
    outputs = []
    for width, height in sizes:
        path = directory / f'preview-{width}x{height}-{seconds}s-gop{gop}.mp4'
        if path.exists():
            raise FileExistsError(f'Refusing to replace existing fixture: {path}')
        base = Image.new('RGB', (width, height))
        draw = ImageDraw.Draw(base)
        rng = random.Random(42)
        for y in range(0, height, 16):
            for x in range(0, width, 16):
                color = tuple(rng.randrange(30, 225) for _ in range(3))
                draw.rectangle((x, y, x + 15, y + 15), fill=color)
        with av.open(str(path), 'w') as output:
            stream = output.add_stream('libx264', rate=fps)
            stream.width, stream.height = width, height
            stream.pix_fmt = 'yuv420p'
            stream.codec_context.thread_count = 2
            stream.codec_context.gop_size = gop
            stream.codec_context.max_b_frames = 3
            stream.options = {'preset': 'fast', 'crf': '20',
                              'x264-params': f'keyint={gop}:min-keyint={gop}:scenecut=0'}
            for index in range(seconds * fps):
                image = base.copy()
                overlay = ImageDraw.Draw(image)
                left = index * 13 % width
                top = index * 7 % height
                overlay.rectangle((left, top, left + width // 3, top + height // 3),
                                  fill=(20, 50, 150))
                overlay.rectangle((15, 15, 650, 110), fill='black')
                overlay.text((30, 30), f'{width}x{height} frame {index:04d} / {index / fps:.3f}s',
                             fill='white', font_size=40)
                frame = av.VideoFrame.from_image(image)
                frame.pts, frame.time_base = index, Fraction(1, fps)
                for packet in stream.encode(frame):
                    output.mux(packet)
            for packet in stream.encode():
                output.mux(packet)
        outputs.append({'path': str(path.resolve()), 'bytes': path.stat().st_size,
                        'width': width, 'height': height, 'fps': fps, 'seconds': seconds,
                        'gop': gop, 'seed': 42,
                        'content': 'detailed colored grid and moving panel'})
        print(json.dumps(outputs[-1]), flush=True)
    (directory / 'fixtures.json').write_text(json.dumps(outputs, indent=2), encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, default=Path('build/video-release-fixtures'))
    parser.add_argument('--seconds', type=int, default=12)
    parser.add_argument('--sizes', nargs='+', default=['1920x1080', '3840x2160'])
    parser.add_argument('--repeat-source', type=Path)
    parser.add_argument('--repeat-count', type=int, default=30)
    args = parser.parse_args()
    if args.repeat_source:
        repeat_clip(args.repeat_source, args.directory, args.repeat_count)
    else:
        sizes = [tuple(map(int, size.split('x'))) for size in args.sizes]
        generate(args.directory, sizes, args.seconds)

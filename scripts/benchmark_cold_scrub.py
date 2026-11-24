"""Prototype cold-source scrubbing; deliberately does not modify application code.

One decode is allowed to finish while pointer input replaces one pending target.
Measures decoder results, not screen presentation. BIDIR omits B frames and must
never populate an exact-frame cache or be used for release/playback decoding.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from poptools.infrastructure.video_media import VideoReader  # noqa: E402


def stats(values):
    if not values:
        return None
    ordered = sorted(values)
    return {'count': len(values), 'median': statistics.median(values),
            'p95': ordered[min(len(values) - 1, int(len(values) * .95))],
            'max': max(values)}


def read_preview(reader, target, nearest):
    if not nearest:
        return reader.seek(target, lambda: None)
    frame = reader.seek_raw(target, lambda: None)
    following = reader._pending
    if following is not None and (frame is None or
            abs(reader.timestamp(following) - target) < abs(reader.timestamp(frame) - target)):
        frame = following
    return reader.picture(frame) if frame is not None else None


def quality_audit(source, mode, height, thread_type, threads, nearest=False):
    """Check actual reconstruction, not just resolution and timestamps."""
    from PIL import Image, ImageChops, ImageStat

    fast, reference = VideoReader(str(source)), VideoReader(str(source))
    rows = []
    try:
        fast.stream.thread_type = thread_type
        fast.stream.codec_context.thread_count = threads
        fast.stream.codec_context.skip_frame = mode
        fast.output_height = reference.output_height = height
        for fraction in (.05, .11, .29, .47, .71, .89):
            preview = read_preview(fast, fast.duration * fraction, nearest)
            exact = reference.seek(preview.time, lambda: None)
            size = (preview.image.width(), preview.image.height())
            # Bench fixtures have RGB rows divisible by four; honor arbitrary
            # QImage row padding as well for use with other source videos.
            images = [Image.frombytes('RGB', size, bytes(p.image.bits()), 'raw',
                                      'RGB', p.image.bytesPerLine()) for p in (preview, exact)]
            difference = ImageStat.Stat(ImageChops.difference(*images))
            rows.append({'time': preview.time, 'reference_time': exact.time,
                         'equal_pixels': preview.image == exact.image,
                         'mean_absolute_error_rgb': difference.mean,
                         'maximum_error_rgb': [maximum for _, maximum in difference.extrema],
                         'preview_interval_seconds': preview.end - preview.time,
                         'actual_interval_seconds': exact.end - exact.time})
    finally:
        fast.close()
        reference.close()
    return rows


def run(source, mode, height, samples=60, deadline_ms=150,
        thread_type='SLICE', threads=2, nearest=False, source_speed=None):
    condition = threading.Condition()
    pending = [None]
    current = [None]
    stopped = [False]
    ready = threading.Event()
    metadata = {}
    results = []
    errors = []

    def worker():
        reader = None
        try:
            reader = VideoReader(str(source))
            reader.stream.thread_type = thread_type
            reader.stream.codec_context.thread_count = threads
            reader.stream.codec_context.skip_frame = mode
            reader.output_height = height
            reader.seek(0, lambda: None)
            metadata.update(reader.info())
            ready.set()
            while True:
                with condition:
                    condition.wait_for(lambda: pending[0] is not None or stopped[0])
                    if stopped[0]:
                        return
                    number, target, sent = pending[0]
                    pending[0] = None
                started = time.perf_counter()
                picture = read_preview(reader, target, nearest)
                finished = time.perf_counter()
                with condition:
                    latest = current[0]
                age_ms = (finished - sent) * 1000
                error = abs(picture.time - target) if picture else None
                results.append({'input': number, 'target': target, 'finished': finished,
                                'request_age_ms': age_ms,
                                'decode_ms': (finished - started) * 1000,
                                'source_frame_time': picture.time if picture else None,
                                'source_error_seconds': error,
                                'pointer_error_seconds': (abs(picture.time - latest[1])
                                                          if picture else None),
                                'size': ([picture.image.width(), picture.image.height()]
                                         if picture else None),
                                'usable': picture is not None
                                and (deadline_ms <= 0 or age_ms <= deadline_ms)
                                and error <= .12})
        except Exception as error:
            errors.append(str(error))
            ready.set()
        finally:
            if reader:
                reader.close()

    thread = threading.Thread(target=worker)
    thread.start()
    if not ready.wait(30) or errors:
        raise RuntimeError(errors or 'Decoder did not start')
    started = time.perf_counter()
    for index in range(samples):
        scheduled = started + index * .016
        time.sleep(max(0, scheduled - time.perf_counter()))
        phase = index % 30
        fraction = .05 + .9 * (phase if phase <= 15 else 30 - phase) / 15
        target = fraction * metadata['duration']
        if source_speed is not None:
            span = .9 * metadata['duration']
            travelled = (index * .016 * source_speed) % (2 * span)
            target = .05 * metadata['duration'] + (travelled if travelled <= span
                                                  else 2 * span - travelled)
        with condition:
            pending[0] = current[0] = (index, target, time.perf_counter())
            condition.notify()
    motion_ended = time.perf_counter()
    with condition:
        stopped[0] = True
        condition.notify()
    thread.join(30)
    if thread.is_alive() or errors:
        raise RuntimeError(errors or 'Decoder did not stop')
    in_motion = [row for row in results if row['finished'] <= motion_ended]
    usable = [row for row in in_motion if row['usable']]
    distinct = [row for index, row in enumerate(in_motion)
                if not index or row['source_frame_time']
                != in_motion[index - 1]['source_frame_time']]
    after_three = None
    if len(in_motion) > 3:
        steady_started = in_motion[2]['finished']
        steady = in_motion[3:]
        steady_usable = [row for row in steady if row['usable']]
        steady_distinct = [row for index, row in enumerate(in_motion)
                           if index >= 3 and row['source_frame_time']
                           != in_motion[index - 1]['source_frame_time']]
        after_three = {
            'exclusion': 'first three completed decode jobs, not first three pointer events',
            'duration_ms': (motion_ended - steady_started) * 1000,
            'completed': len(steady), 'useful': len(steady_usable),
            'fps': len(steady_usable) / (motion_ended - steady_started),
            'distinct_source_fps': len(steady_distinct) / (motion_ended - steady_started),
            'request_age_ms': stats([row['request_age_ms'] for row in steady]),
            'decode_ms': stats([row['decode_ms'] for row in steady])}
    times = [started, *[row['finished'] for row in usable], motion_ended]
    final_target = current[0][1]
    # A fresh DEFAULT decoder models safe release after a separate fast reader.
    release_started = time.perf_counter()
    reader = VideoReader(str(source))
    try:
        reader.output_height = height
        final = reader.seek(final_target, lambda: None)
        release_ms = (time.perf_counter() - release_started) * 1000
    finally:
        reader.close()
    for row in results:
        row['finished_ms'] = (row.pop('finished') - started) * 1000
    duration = motion_ended - started
    return {'mode': mode, 'height': height, 'thread_type': thread_type,
            'threads': threads, 'nearest': nearest, 'input_samples': samples,
            'source_speed': source_speed,
            'motion_ms': duration * 1000, 'decoded_during_motion': len(in_motion),
            'distinct_source_frames': len(distinct),
            'distinct_source_fps': len(distinct) / duration,
            'useful_frames': len(usable), 'useful_fps': len(usable) / duration,
            'useful_deadline_ms': deadline_ms,
            'useful_gap_ms': stats([(b - a) * 1000
                                    for a, b in zip(times, times[1:], strict=False)]),
            'request_age_ms': stats([row['request_age_ms'] for row in in_motion]),
            'decode_ms': stats([row['decode_ms'] for row in in_motion]),
            'source_error_ms': stats([row['source_error_seconds'] * 1000 for row in in_motion]),
            'after_first_three_decodes': after_three,
            'release_source_ms': release_ms,
            'release_exact_coverage': final.time <= final_target < final.end,
            'results': results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--modes', nargs='+', default=['DEFAULT', 'BIDIR', 'NONREF'])
    parser.add_argument('--height', type=int, default=0)
    parser.add_argument('--samples', type=int, default=60)
    parser.add_argument('--deadline-ms', type=float, default=150,
                        help='Maximum accepted request age; zero accepts all completed frames')
    parser.add_argument('--source-speed', type=float,
                        help='Timeline seconds per wall second, reflected at the 5/95%% points')
    parser.add_argument('--thread-type', default='SLICE')
    parser.add_argument('--threads', type=int, default=2)
    parser.add_argument('--nearest', action='store_true')
    parser.add_argument('--audit', action='store_true',
                        help='Compare retained frames against DEFAULT decoding at the same PTS')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = {'measurement': 'prototype decoder completion; not GUI or display swaps',
              'source': str(args.source.resolve()),
              'runs': [run(args.source, mode, args.height, args.samples, args.deadline_ms,
                           args.thread_type, args.threads, args.nearest, args.source_speed)
                       for mode in args.modes]}
    if args.audit:
        report['reconstruction_audit'] = {
            mode: quality_audit(args.source, mode, args.height, args.thread_type, args.threads,
                                args.nearest)
            for mode in dict.fromkeys(args.modes)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps([{key: value for key, value in row.items() if key != 'results'}
                      for row in report['runs']], indent=2))


if __name__ == '__main__':
    main()

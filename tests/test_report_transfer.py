import base64
from dataclasses import replace
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from dashpi.models import IncidentMetadata, IncidentState
from dashpi.reports import MAX_TRANSFER_BYTES, build_transfer_report, create_transfer_artifact
from dashpi.storage import IncidentStore, atomic_write
from tests.test_reports import complete_report_fixture


def jpeg_images(shape=(270, 480), noisy=False):
    rng = np.random.default_rng(7)
    images = []
    for _ in range(3):
        image = rng.integers(0, 256, (*shape, 3), dtype=np.uint8) if noisy else np.full((*shape, 3), 120, np.uint8)
        ok, encoded = cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, 95])
        assert ok
        images.append(encoded.tobytes())
    return images


def transfer_source():
    report = complete_report_fixture()
    report['digests']['clip.mp4'] = 'a' * 64
    report['keyframe_timestamps'] = {'before': 20.5, 'moment': 22.5, 'after': 24.5}
    return report


def make_stored_legacy(root):
    store = IncidentStore(root)
    item = IncidentMetadata.new('legacy-incident', '2026-09-06T00:00:00Z', 0.0, 15.0)
    directory = store.directory(item.incident_id)
    item.clip = replace(atomic_write(directory / 'clip.mp4', b'original evidence'), duration=30.0)
    report = transfer_source()
    report.pop('keyframe_timestamps')
    report['incident_id'] = item.incident_id
    report['digests']['clip.mp4'] = item.clip.sha256
    for role, content in zip(('before', 'moment', 'after'), jpeg_images(), strict=True):
        artifact = atomic_write(directory / 'keyframes' / f'{role}.jpg', content)
        report['digests'][artifact.path.name] = artifact.sha256
    item.report_json = atomic_write(directory / 'report.json', json.dumps(report).encode())
    item.report_html = atomic_write(directory / 'report.html', b'<html>legacy video report</html>')
    item.transition(IncidentState.READY, '2026-09-06T00:01:00Z')
    store.save(item)
    return store, item, report


@pytest.mark.parametrize('shape,noisy', [((270, 480), False), ((360, 480), False), ((270, 480), True)])
def test_transfer_fits_utf8_budget_preserves_aspect_and_hashes(shape, noisy):
    images = jpeg_images(shape, noisy)
    unchanged = list(images)
    source = transfer_source()
    payload = build_transfer_report(source, images, 30.0)
    result = json.loads(payload)
    assert len(payload) <= MAX_TRANSFER_BYTES
    assert images == unchanged
    assert result['format'] == 'dashpi.report' and result['version'] == 1
    assert result['summary'] == source['summary']
    assert result['digests'] == {'clip.mp4': 'a' * 64}
    assert len(result['major_negligence_review']) == 12
    for frame in result['keyframes']:
        content = base64.b64decode(frame['jpeg_base64'], validate=True)
        assert hashlib.sha256(content).hexdigest() == frame['sha256']
        image = cv2.imdecode(np.frombuffer(content, np.uint8), cv2.IMREAD_COLOR)
        height, width = image.shape[:2]
        assert width <= 480 and abs(height / width - shape[0] / shape[1]) <= 1 / width
        assert frame['timestamp'] == source['keyframe_timestamps'][frame['role']]
    if not noisy:
        assert width == 480
    assert not result['warnings']


def test_resolution_reduces_only_after_quality_candidates_are_exhausted(monkeypatch):
    real_encode = cv2.imencode
    candidates = []
    def record_encode(extension, image, params):
        candidates.append((image.shape[1], params[1]))
        return real_encode(extension, image, params)
    images = jpeg_images(noisy=True)
    monkeypatch.setattr(cv2, 'imencode', record_encode)
    build_transfer_report(transfer_source(), images, 30.0)
    tried = candidates[::3]
    assert tried[:4] == [(480, quality) for quality in (75, 60, 45, 30)]
    assert tried[4][0] < 480


def test_budget_boundary_counts_utf8_bytes_without_shortening_text(monkeypatch):
    import dashpi.reports as reports
    source = transfer_source()
    source['summary'] = '장면 설명' * 50
    images = jpeg_images()
    payload = build_transfer_report(source, images, 30.0)
    monkeypatch.setattr(reports, 'MAX_TRANSFER_BYTES', len(payload))
    assert build_transfer_report(source, images, 30.0) == payload
    source['summary'] = '영상' * 31_000
    with pytest.raises(ValueError, match='60,000'):
        build_transfer_report(source, images, 30.0)
    assert len(source['summary']) == 62_000


@pytest.mark.parametrize('moment,expected', [(0.0, [0.0, 0.0, 2.0]), (30.0, [27.9, 29.9, 29.9])])
def test_legacy_timestamps_use_clip_boundaries_and_warn(moment, expected):
    source = transfer_source()
    source.pop('keyframe_timestamps')
    source['incident_timestamp'] = moment
    source['transfer_window'] = {'start': 0.0, 'end': 10.0} if moment == 0 else {'start': 20.0, 'end': 30.0}
    result = json.loads(build_transfer_report(source, jpeg_images(), 30.0))
    assert [frame['timestamp'] for frame in result['keyframes']] == expected
    assert any('추정' in warning for warning in result['warnings'])


@pytest.mark.parametrize('change', ['bad_jpeg', 'missing_role', 'nan', 'bad_date', 'bad_warnings'])
def test_invalid_transfer_sources_fail(change):
    source, images = transfer_source(), jpeg_images()
    if change == 'bad_jpeg':
        images[0] = b'not jpeg'
    elif change == 'missing_role':
        source['keyframe_timestamps'].pop('after')
    elif change == 'nan':
        source['keyframe_timestamps']['moment'] = float('nan')
    elif change == 'bad_date':
        source['generated_at'] = '2026-10-04T12:00:00'
    else:
        source['warnings'] = 'not a list'
    with pytest.raises(ValueError):
        build_transfer_report(source, images, 30.0)


def test_legacy_conversion_preserves_original_files_and_round_trips_artifact(tmp_path):
    store, item, _ = make_stored_legacy(tmp_path)
    directory = store.directory(item.incident_id)
    originals = {path: path.read_bytes() for path in directory.rglob('*') if path.is_file() and path.name != 'metadata.json'}
    with store.open_incident(item.incident_id) as (current, descriptor, directory):
        artifact = create_transfer_artifact(store, current, descriptor, directory)
    assert store.load(item.incident_id).report_transfer == artifact
    assert store.load(item.incident_id).state is IncidentState.READY
    assert all(path.read_bytes() == content for path, content in originals.items())
    result = json.loads(artifact.path.read_bytes())
    assert all(review['status'] == 'not_determinable' for review in result['major_negligence_review'].values())
    assert any('추정' in warning for warning in result['warnings'])


@pytest.mark.parametrize('damage', ['report_path', 'report_hash', 'report_symlink', 'image_hash', 'image_symlink', 'directory_symlink'])
def test_legacy_conversion_rejects_unverified_sources(tmp_path, damage):
    store, item, _ = make_stored_legacy(tmp_path / 'data')
    directory = store.directory(item.incident_id)
    image = directory / 'keyframes' / 'before.jpg'
    if damage == 'report_path':
        item.report_json = atomic_write(tmp_path / 'outside.json', item.report_json.path.read_bytes())
        store.save(item)
    elif damage == 'report_hash':
        item.report_json.path.write_bytes(b'{}')
    elif damage == 'report_symlink':
        outside = tmp_path / 'outside.json'
        outside.write_bytes(item.report_json.path.read_bytes())
        item.report_json.path.unlink()
        item.report_json.path.symlink_to(outside)
    elif damage == 'image_hash':
        image.write_bytes(jpeg_images((100, 100))[0])
    elif damage == 'image_symlink':
        outside = tmp_path / 'outside.jpg'
        outside.write_bytes(image.read_bytes())
        image.unlink()
        image.symlink_to(outside)
    else:
        original = directory / 'keyframes'
        outside = tmp_path / 'outside-frames'
        original.rename(outside)
        original.symlink_to(outside, target_is_directory=True)
    with store.open_incident(item.incident_id) as (current, descriptor, directory):
        with pytest.raises(Exception):
            create_transfer_artifact(store, current, descriptor, directory)
    assert store.load(item.incident_id).state is IncidentState.READY
    assert store.load(item.incident_id).report_transfer is None
    assert item.report_html.path.read_bytes().startswith(b'<html>')


def test_python_report_fixture_survives_late_join_loss_duplicates_and_reordering():
    from dashpi.optical.container import unpack_container
    from dashpi.optical.fountain import FountainDecoder
    from dashpi.optical.protocol import parse_frame
    from dashpi.optical.session import OpticalSession
    fixture = json.loads((Path(__file__).parent / 'fixtures' / 'optical-report-v1.json').read_text())
    payload = fixture['payload'].encode('utf8')
    assert len(payload) == fixture['payload_length'] <= MAX_TRANSFER_BYTES
    session = OpticalSession.from_bytes(fixture['name'], payload, fixture['media_type'], fixture['block_size'], fixture['session_id'])
    assert session.encoder.block_count == fixture['block_count']
    assert session.total_length == fixture['container_length']
    decoder = FountainDecoder(fixture['block_count'], fixture['block_size'], fixture['container_length'])
    assert min(fixture['sequences']) >= fixture['block_count'] * 2
    assert len(fixture['sequences']) > len(set(fixture['sequences']))
    for sequence, wire_hex in zip(fixture['sequences'], fixture['frames_hex'], strict=True):
        wire = bytes.fromhex(wire_hex)
        assert session.frame(sequence) == wire
        frame = parse_frame(wire)
        decoder.add(frame.indices, frame.symbol)
    received = unpack_container(decoder.result())
    assert received.payload == payload
    assert received.sha256 == fixture['payload_sha256']
    report = json.loads(payload)
    assert report['format'] == 'dashpi.report'
    for frame in report['keyframes']:
        content = base64.b64decode(frame['jpeg_base64'], validate=True)
        assert hashlib.sha256(content).hexdigest() == frame['sha256']
        assert cv2.imdecode(np.frombuffer(content, np.uint8), cv2.IMREAD_COLOR) is not None


@pytest.mark.parametrize('date', ['2026-10-04 12:00:00Z', '2026-02-30T12:00:00Z', '2026-10-04T12:00:00+01:60', '2026-10-04T12:00:00+24:00'])
def test_transfer_dates_match_native_iso_validation(date):
    source = transfer_source()
    source['generated_at'] = date
    with pytest.raises(ValueError):
        build_transfer_report(source, jpeg_images(), 30.0)


def test_conversion_does_not_resurrect_incident_deleted_while_encoding(tmp_path, monkeypatch):
    import dashpi.reports as reports
    store, item, _ = make_stored_legacy(tmp_path)
    directory = store.directory(item.incident_id)
    real_build = reports.build_transfer_report
    def delete_while_encoding(*args):
        store.delete(item.incident_id)
        return real_build(*args)
    monkeypatch.setattr(reports, 'build_transfer_report', delete_while_encoding)
    with store.open_incident(item.incident_id) as (current, descriptor, directory):
        with pytest.raises(FileNotFoundError):
            reports.create_transfer_artifact(store, current, descriptor, directory)
    assert not directory.exists()
    assert store.list() == []


def test_conversion_does_not_publish_into_replacement_directory(tmp_path, monkeypatch):
    import dashpi.reports as reports
    store, item, _ = make_stored_legacy(tmp_path / 'data')
    directory = store.directory(item.incident_id)
    moved = tmp_path / 'original-incident'
    real_build = reports.build_transfer_report
    def replace_while_encoding(*args):
        directory.rename(moved)
        directory.mkdir()
        (directory / 'sentinel').write_bytes(b'replacement directory')
        return real_build(*args)
    monkeypatch.setattr(reports, 'build_transfer_report', replace_while_encoding)
    with store.open_incident(item.incident_id) as (current, descriptor, directory):
        with pytest.raises(OSError, match='directory changed'):
            reports.create_transfer_artifact(store, current, descriptor, directory)
    assert sorted(path.name for path in directory.iterdir()) == ['sentinel']
    assert (directory / 'sentinel').read_bytes() == b'replacement directory'
    assert not (moved / 'report.transfer.json').exists()
    assert (moved / 'clip.mp4').read_bytes() == b'original evidence'


def test_conversion_ignores_old_partial_symlinks_without_overwriting_evidence(tmp_path):
    store, item, _ = make_stored_legacy(tmp_path)
    directory = store.directory(item.incident_id)
    original = item.clip.path.read_bytes()
    partials = [directory / 'report.transfer.json.partial', directory / 'metadata.json.partial']
    for partial in partials:
        partial.symlink_to(item.clip.path)
    with store.open_incident(item.incident_id) as (current, descriptor, directory):
        transfer = create_transfer_artifact(store, current, descriptor, directory)
    assert item.clip.path.read_bytes() == original
    assert all(partial.is_symlink() for partial in partials)
    assert not transfer.path.is_symlink()
    assert not (directory / 'metadata.json').is_symlink()
    assert store.load(item.incident_id).report_transfer == transfer


@pytest.mark.parametrize('target', ['report.transfer.json', 'metadata.json'])
def test_conversion_exclusive_temp_collision_cannot_overwrite_evidence(tmp_path, monkeypatch, target):
    import dashpi.storage as storage
    store, item, _ = make_stored_legacy(tmp_path)
    directory = store.directory(item.incident_id)
    original_metadata = (directory / 'metadata.json').read_bytes()
    monkeypatch.setattr(storage.secrets, 'token_hex', lambda _size: 'collision')
    partial = directory / f'.{target}.collision.partial'
    partial.symlink_to(item.clip.path)
    with store.open_incident(item.incident_id) as (current, descriptor, directory):
        with pytest.raises(FileExistsError):
            create_transfer_artifact(store, current, descriptor, directory)
        assert current.report_transfer is None
    assert item.clip.path.read_bytes() == b'original evidence'
    assert partial.is_symlink()
    assert (directory / 'metadata.json').read_bytes() == original_metadata
    assert store.load(item.incident_id).report_transfer is None


def test_deletion_before_metadata_rename_cannot_resurrect_incident(tmp_path, monkeypatch):
    import dashpi.storage as storage
    store, item, _ = make_stored_legacy(tmp_path)
    directory = store.directory(item.incident_id)
    real_replace = storage.os.replace
    def delete_before_metadata(source, target, **kwargs):
        if target == 'metadata.json':
            store.delete(item.incident_id)
        return real_replace(source, target, **kwargs)
    monkeypatch.setattr(storage.os, 'replace', delete_before_metadata)
    with store.open_incident(item.incident_id) as (current, descriptor, directory):
        with pytest.raises(FileNotFoundError):
            create_transfer_artifact(store, current, descriptor, directory)
        assert current.report_transfer is None
    assert not directory.exists()
    assert store.list() == []


def test_metadata_rename_failure_keeps_original_metadata_and_sources(tmp_path, monkeypatch):
    import dashpi.storage as storage
    store, item, _ = make_stored_legacy(tmp_path)
    directory = store.directory(item.incident_id)
    originals = {path: path.read_bytes() for path in directory.rglob('*') if path.is_file()}
    real_replace = storage.os.replace
    def fail_metadata(source, target, **kwargs):
        if target == 'metadata.json':
            raise OSError('metadata publication failed')
        return real_replace(source, target, **kwargs)
    monkeypatch.setattr(storage.os, 'replace', fail_metadata)
    with store.open_incident(item.incident_id) as (current, descriptor, directory):
        with pytest.raises(OSError, match='metadata publication failed'):
            create_transfer_artifact(store, current, descriptor, directory)
        assert current.report_transfer is None
    assert all(path.read_bytes() == content for path, content in originals.items())
    assert not list(directory.glob('.*.partial'))
    assert store.load(item.incident_id).report_transfer is None

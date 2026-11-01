"""Host inline byte-budget regressions; warnings must not become failures."""
from pathlib import Path
import importlib.util
import io
from zipfile import ZipFile
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('prompt_sizes_test', ROOT / 'tools/check_prompt_sizes.py')
sizes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sizes)


@pytest.mark.parametrize('path', sorted((ROOT / 'skills').glob('*/SKILL.md')), ids=lambda p: p.parent.name)
def test_skill_inline_limit(path):
    assert path.stat().st_size <= sizes.SKILL_LIMIT


@pytest.mark.parametrize('path', sorted((ROOT / 'agents').glob('*.md')), ids=lambda p: p.stem)
def test_agent_inline_limit(path):
    assert path.stat().st_size <= sizes.AGENT_LIMIT


@pytest.mark.parametrize('path', sorted((ROOT / 'individual-packages').glob('*/*.zip')), ids=lambda p: p.parent.name)
def test_standalone_skill_inline_limit(path):
    assert sizes.run(path)['pass']


@pytest.mark.parametrize('kind,count,status', [
    ('skill', 48128, 'PASS'), ('skill', 48129, 'FAIL'),
    ('agent', 49152, 'PASS'), ('agent', 49153, 'WARN'),
    ('agent', 51200, 'WARN'), ('agent', 51201, 'FAIL'),
])
def test_exact_byte_boundaries(kind, count, status):
    # Multibyte text proves that the limit counts bytes rather than characters.
    data = ('中' * (count // 3)).encode() + b'x' * (count % 3)
    assert sizes.measure('synthetic', data, kind)['status'] == status


def test_oversize_standalone_inside_release_is_rejected(tmp_path):
    inner = io.BytesIO()
    with ZipFile(inner, 'w') as z:
        z.writestr('stability-director/SKILL.md', b'x' * 48129)
    outer = tmp_path / 'release.zip'
    with ZipFile(outer, 'w') as z:
        z.writestr('crm-sre-team/skills/ok/SKILL.md', b'ok')
        z.writestr('crm-sre-team/individual-packages/stability-director/skill.zip', inner.getvalue())
    report = sizes.run(outer)
    assert not report['pass'] and len(report['errors']) == 1
    assert report['errors'][0]['kind'] == 'standalone_skill'


def test_empty_surface_is_not_a_pass(tmp_path):
    assert not sizes.run(tmp_path)['pass']

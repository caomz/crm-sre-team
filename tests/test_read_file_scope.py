"""Tool permission never grants permission to read a guard output file."""
from pathlib import Path
from zipfile import ZipFile
import importlib.util
import pytest

ROOT = Path(__file__).resolve().parents[1]
RULE = '除固定守卫命令外，不为 BOMC 另跑终端命令或脚本；仅当用户本轮文件范围明确包含守卫输出文件时，才用 Read 读取。Read 在工具名单内不等于文件获准；只准读 bomc.json 等其他文件时不读输出文件。未获准则按守卫预览分析，写明未读范围及限制。'
TAIL = '仅用户本轮文件范围明确包含守卫输出文件时才可 Read；否则按预览分析并说明未读范围及限制。'
PROMPTS = [
    'policy-source/prompts/roles/telecom-crm-sre-team-lead.md',
    'policy-source/skills/stability-director.md',
    'policy-source/skills/bomc-alarm-readonly.md',
    'agents/telecom-crm-sre-team-lead.md',
    'skills/stability-director/SKILL.md',
    'skills/bomc-alarm-readonly/SKILL.md',
]
CLAUSES = [
    '仅当用户本轮文件范围明确包含守卫输出文件时，才用 Read 读取',
    'Read 在工具名单内不等于文件获准',
    '只准读 bomc.json 等其他文件时不读输出文件',
    '未获准则按守卫预览分析，写明未读范围及限制',
]
spec = importlib.util.spec_from_file_location('read_scope_checker', ROOT / 'tools/check_workbuddy.py')
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


@pytest.mark.parametrize('name', PROMPTS)
def test_scope_first_rule_in_all_prompt_locations(name):
    text = (ROOT / name).read_text(encoding='utf-8')
    assert text.count(RULE) == 1
    assert RULE + '\nRead 只按本次实际返回的行表述' in text
    assert '需要查看完整脱敏结果时' not in text
    assert '如需读取完整脱敏文件仍须符合用户文件范围限制' not in text
    if 'bomc-alarm-readonly' in name:
        assert text.count(TAIL) == 1


def test_scope_first_rule_in_standalone_skill():
    with ZipFile(ROOT / 'individual-packages/stability-director/skill.zip') as z:
        text = z.read('stability-director/SKILL.md').decode()
    assert text.count(RULE) == 1


@pytest.mark.parametrize('name', PROMPTS)
@pytest.mark.parametrize('clause', CLAUSES)
def test_each_scope_clause_is_required_by_static_validator(name, clause):
    text = (ROOT / name).read_text(encoding='utf-8')
    assert checker.BOMC_TERMINAL_AND_READ_RULE == RULE
    changed = text.replace(clause, '', 1)
    errors = checker.check_prompt(changed, 'scope-regression', runtime=not name.startswith('policy-source/'))
    assert 'missing_bomc_lead_rule:' + RULE in errors

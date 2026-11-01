"""TD-03: Read visibility must survive every canonical/generated prompt location."""
from pathlib import Path
from zipfile import ZipFile
import pytest

ROOT = Path(__file__).resolve().parents[1]
RULE = 'Read 只按本次实际返回的行表述；某行带宿主截断或压缩标记（如“... [truncated]”），须写明该行在本次读取中被截断，不声称“完整内容”“全文”或逐字未截断。字段原值仅证明该字段在本次 Read 结果中可见；文件身份以 E 号登记的 output_file 路径和守卫回执 SHA256 为准，不拿字段值证明文件身份或完整性。数据自述为合成或演练时，称“合成字段”或“合成数据”，不称现场记录或现场证据。Read 成功不扩大展示或文件交付范围。'
ANCHOR = '除固定守卫命令外，不为 BOMC 另跑终端命令或脚本；仅当用户本轮文件范围明确包含守卫输出文件时，才用 Read 读取。Read 在工具名单内不等于文件获准；只准读 bomc.json 等其他文件时不读输出文件。未获准则按守卫预览分析，写明未读范围及限制。'

@pytest.mark.parametrize('name', [
    'policy-source/prompts/roles/telecom-crm-sre-team-lead.md',
    'policy-source/skills/stability-director.md',
    'policy-source/skills/bomc-alarm-readonly.md',
    'agents/telecom-crm-sre-team-lead.md',
    'skills/stability-director/SKILL.md',
    'skills/bomc-alarm-readonly/SKILL.md',
])
def test_read_visibility_rule_in_every_prompt(name):
    text = (ROOT / name).read_text(encoding='utf-8')
    assert text.count(RULE) == 1
    assert ANCHOR + '\n' + RULE in text

def test_read_visibility_rule_in_standalone_lead_zip():
    with ZipFile(ROOT / 'individual-packages/stability-director/skill.zip') as archive:
        text = archive.read('stability-director/SKILL.md').decode('utf-8')
    assert text.count(RULE) == 1
    assert ANCHOR + '\n' + RULE in text

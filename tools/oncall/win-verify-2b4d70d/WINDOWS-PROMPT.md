# crm-sre-team 2b4d70d · Windows 实机复验执行提示词（GitHub 同步版）

## 这一轮做什么

在值班机上，通过匿名只读 HTTPS 从公开仓库 `https://github.com/caomz/crm-sre-team.git` 拉取提交 `2b4d70d0e10f25603e85106159c8213279ef759e`（分支 `codex/deepseek-agent-team`）到新建工作目录，做一次实机复验。重点核实三项与 Windows 相关的修复：

1. 安装载荷校验改为按 POSIX 字符串排序。11-17 Windows 报告 §2 里 `test_25` 失败，原因是 WindowsPath 比较不区分大小写。
2. `test_30c` 改用原始字节保存和还原，不再因为 LF 变成 CRLF 而失败。
3. pre-commit 钩子改为按能力选择解释器：要求 Python 3.11+ 且能导入 PyYAML，并支持 `CRM_SRE_PYTHON` 显式指定。这一项要在 Git for Windows 的 sh 下，覆盖 `py -3` 和反斜杠路径。

另外顺带跑：全量离线 pytest、oncall 测试、三项静态校验；构建 DSH ZIP，先比对压缩数据以外的每个字节，再比对整个文件；用 ZIP 解出的载荷做安装校验；确认重建后零差异；再经钩子做两次真实 `git commit`（只在新克隆里提交），用 git 自己的跟踪记录确认钩子确实执行过。

## 这一轮不做什么

- **不做** DSH 桌面宿主的安装、VERIFY 和会话。`docs/17` 规定 Mac 总体未通过前不推进 Windows。
- **Node 版本只记录**。下一轮做宿主测试时要求 ≥ 24.9.0（11-17 用的 22.20.0 不合格）。
- 不装包、不升级；**除门禁阶段（G3/G4）通过匿名 HTTPS 从公开 GitHub 仓库只读拉取 `2b4d70d` 外，不做其他联网操作**，不读取登录凭据、不调用凭据管理器、不发送 Git 配置里的额外请求头和 cookie、不改全局 Git 配置、不推送（新克隆的 `origin` pushurl 已锁为 `no_push`）；也不手动删除或清理任何文件。测试只会删除它们自己在工作目录里建的临时文件。
- 不碰 `D:\python_code\github_my\crm-sre-team`、WorkBuddy 及其插件目录、凭据和环境变量。
- 所有写入都落在新建的工作目录 `D:\crm-sre-verify\w-<时间>` 里。唯一例外：脚本开始核对之后、建出工作目录之前就停下（且交付文件夹存在）时，会在交付文件夹里留一个 `BLOCKED-<时间>.json`（脚本自身出错时是 `ERROR-<时间>.json`）。更早的失败，例如粘贴块被改坏导致参数错误，只有控制台输出。

这台机器按记录是 Windows 11 家庭版 23H2（10.0.22631），报告里以实际系统信息为准。

## 准备

1. 把整个交付文件夹拷到值班机上，例如 `D:\crm-handoff\crm-dsh-win-verify-2b4d70d-github`。文件夹里应有：`win_verify.py`、`WINDOWS-PROMPT.md`、`SHA256SUMS`（无需 `.bundle` 文件）。
2. 打开**普通的 Windows PowerShell 5.1 窗口**（开始菜单里的 Windows PowerShell），**不要**在 WorkBuddy 或 AI 代理的工具通道里跑。代理通道的删除守卫会拦下测试和构建都要用到的 `shutil.rmtree`，而且会自动重试命令。
3. 工作根目录保持默认的 `D:\crm-sre-verify`，不要改到更深的位置。在这个位置下，测试里实测最深的路径约 234 个字符，已经接近 Windows 260 字符的上限。脚本拉取代码之前会按约 251 个字符（含余量）预估；系统没开长路径支持而预估超过 259 时，直接判 BLOCKED。
4. 预计耗时 15–40 分钟，大部分时间花在全量测试上。中途不需要任何输入（Git 拉取已关闭终端提示与凭据助手，并用最长前缀 `insteadOf` 绕开全局 SSH 改写；如果本机 Git 配置仍把仓库地址改写到别处，脚本会判 BLOCKED，不会改从别处拉取）。

## 粘贴块（只贴这一段；先把第 3 行改成交付文件夹的实际位置）

```powershell
. {
  $ErrorActionPreference = 'Stop'
  $Delivery = 'D:\crm-handoff\crm-dsh-win-verify-2b4d70d-github'   # 改成交付文件夹在本机的实际位置
  $Python   = 'C:\Users\AI\AppData\Local\Programs\Python\Python312\python.exe'
  $Expected = @{
    'win_verify.py' = 'D3C6B1C346581CB2A05152A7AED650746CE0E327011522A0E3CF3E4A9CFFDECD'
  }
  if (-not (Test-Path -LiteralPath $Delivery -PathType Container)) { throw "STOP: delivery folder not found: $Delivery" }
  foreach ($name in $Expected.Keys) {
    $file = Join-Path $Delivery $name
    if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { throw "STOP: missing file $file" }
    $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $file).Hash
    if ($actual -ne $Expected[$name]) { throw "STOP: SHA256 mismatch for $name : $actual" }
  }
  if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw "STOP: Python not found at $Python" }
  $driverArgs = @('-B', '-E', '-P', (Join-Path $Delivery 'win_verify.py'), '--delivery', $Delivery, '--ps-version', "$($PSVersionTable.PSVersion)")
  try { $os = Get-CimInstance Win32_OperatingSystem; $driverArgs += @('--os-caption', "$($os.Caption) $($os.Version)") } catch { }
  & $Python @driverArgs
  "win_verify exit code: $LASTEXITCODE  (0 PASS / 1 FAIL / 2 BLOCKED / 3 ERROR)"
}
```

如果 Python 不在第 4 行写的位置，就把那一行改成本机 Python 3.11+ 的 `python.exe` 路径。这个 Python 需要已经装好 pytest、PyYAML、jsonschema、referencing，脚本不会代为安装。

## 结束后看什么、回传什么

控制台最后会打印 `VERDICT PASS|FAIL|BLOCKED|ERROR`、`Report: …\REPORT.md`、`Evidence: …\evidence-<时间>.zip  sha256 …` 三行，粘贴块再补一行 `win_verify exit code: …`。

请把这三样传回 Mac：

- `REPORT.md` 全文
- `evidence-<时间>.zip`
- 同名的 `.sha256` 文件

`REPORT.md` 里有：环境信息（系统、PowerShell、脚本 SHA256、远端仓库、Git 配置展开后的仓库地址与分支头、Python 及各包版本、zlib、Git、sh、长路径设置、Node 及是否达到 24.9.0）、逐项结果表、6 个必过用例的状态、全量测试的跳过清单、对应的 Mac 参考值，以及失败项各自日志的最后 60 行。证据包里另有全部日志、两次提交的 git 跟踪记录，以及这台机器构建出的 DSH ZIP。

## 怎么读结果

- **退出码**：0 是 PASS；1 是 FAIL，表示至少一项失败；2 是 BLOCKED，表示前置条件不满足且没有任何一项失败；3 是 ERROR，表示复验脚本自身出错或被中断，且没有任何一项失败。连不上 GitHub HTTPS 或本机 Git 配置把仓库地址改写到别处（G3/G4）、找不到 Git for Windows 的 sh（H0）、工作目录过深（E2）都算 BLOCKED。如果远端分支未来继续前进，G3 记为 INFO，G4 仍按精确 40 位提交哈希拉取 `2b4d70d` 并校验。INFO 和 N/A 不影响结论。
- **ZIP 两项**：C5a 逐字节比对压缩数据以外的全部内容（只把压缩大小和偏移量归零），并核对每个文件解压后的 SHA256，必须 PASS。C5b 比对整个 ZIP 的字节。Windows 版 Python 自带的 zlib 如果和 Mac 的 1.2.12 不同，压出来的字节就可能不同。这时脚本会用本机 zlib 按 9 级把每个文件重新压缩，与 ZIP 里的压缩数据逐一核对：全部一致，就说明差异只来自 zlib，C5b 记为 INFO，不算失败；不一致则记 FAIL。REPORT 里会写明两边的 zlib 版本。
- **第一次在 Windows 上跑的部分**：H2（反斜杠绝对路径）、H5（仓库相对路径加 shim 脚本）、sh 的查找、E2 的长路径估算与注册表读取，以及粘贴块本身，在 Mac 上都无法实测。如果这些地方出现 FAIL 或 BLOCKED，而 C1b 的 6 个必过用例都 PASS，问题可能出在复验脚本本身，不一定是产品回归。照原样回传，等 Mac 复核后再下结论。

## 停止规则

- **哈希不符、文件缺失或路径不对**：粘贴块会以 `STOP:` 停下。不要改脚本，原样回报。
- **结果是 BLOCKED**（例如 Python 低于 3.11、缺 pytest、找不到 git 或 sh、GitHub HTTPS 连不上或超时、Git 配置把仓库地址改写到别处、工作目录过深）：不要修环境、不要装包、不要改本机 Git 或 hosts 配置，把控制台最后几行和 `REPORT.md`（或交付目录里的 `BLOCKED-<时间>.json`）回传。
- **结果是 FAIL 或 ERROR**：不重跑、不修复、不改仓库，直接回传报告和证据包，等 Mac 复核。
- **没有 `REPORT.md` 时**：按控制台最后几行提示的位置，回传工作目录里的 `results.json`，或交付文件夹里的 `BLOCKED-<时间>.json` / `ERROR-<时间>.json`；都没有的话，回传控制台最后 30 行。
- 全程不做任何“顺手”的修复或清理。工作目录先保留，等 Mac 复核完由你手动删除。

## 如果交给 Windows 上的 AI 代理

把下面这段作为提示词给它：

> 只做汇报，不执行测试。请确认用户已在普通 Windows PowerShell 5.1 窗口里运行过 `WINDOWS-PROMPT.md` 的粘贴块。不要在你的工具通道里运行 `win_verify.py`：通道里的删除守卫会拦截 `shutil.rmtree`，而且会自动重试。运行结束后，读取控制台最后几行和 `REPORT.md`，原样回报以下内容：VERDICT 和退出码、逐项结果表、必过用例、Environment 一节（含 script_sha256、effective_url、remote_branch_head、zlib 和 node_status），以及失败节选。G3 或 C5b 是 INFO 时照实转述，不要改判。不要修复、不要重跑、不要删除或移动任何文件、不要安装任何东西，也不要写工作记忆。

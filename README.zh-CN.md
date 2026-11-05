# Petra

[English](README.md) | **简体中文**

> 本文与英文版 README 同步维护；如有出入，以英文版为准。

Petra 是面向 AMD GPU 的开源大模型推理框架 agent，首先支持 sglang。它把一个任务——把上游特性移植到 AMD、处理 AMD 用户的 issue、修复变红的 AMD CI job、弥补系统级的性能差距——变成一个维护者可以审阅的 pull request：**先保证正确**（独立的单元门禁，对照同模式基线的精度 / 长上下文 / 压力门禁，有对照实验的排查循环），**再追求性能**（同等预算下的 A/B），并遵守 [`knowledge/guardrails.md`](knowledge/guardrails.md) 中的社区规则。Petra 只提出改动；审阅、push 和合入由人来做。

Petra 为什么存在、与既定设计如何对应，见 [`docs/design.md`](docs/design.md)（英文）。

## 模式

| 模式 | 任务 | 阶段 | 产出 |
|---|---|---|---|
| `feature` | 把上游 PR 或设计移植到 AMD | Setup → Spec → Recon → Design → Implement → (Kernel) → Verify → Performance → Review → PR → Report | 分支 + PR 描述 + 验证报告 |
| `issue` | 一个 AMD 用户 issue | Setup → Triage → Reproduce → Diagnose（已有修复 PR 时跳过）→ Implement → (Kernel) → Verify → (Performance) → Review → PR → Report | 修复 PR，或一个结论（已分诊、未复现、main 上已修复、已定位）；总会附一份回复草稿 |
| `ci` | 一个变红的 AMD CI job 或 Failure Tracker 簇 | Setup → Classify → Bisect → Implement → (Kernel) → Verify → Review → PR → Report | 修复 PR，或把偶发 / 基础设施失败移交出去 |
| `perf` | 针对某个模型和固定负载的系统级性能目标 | Setup → Profile → Plan → Implement → (Kernel) → Verify → Performance → Review → PR → Report | 带实测收益的 PR，或放弃改动；kernel 级的工作交给 kernel 后端 |
| `scan` | 无——从上游提交、AMD issue、CI 失败和平台门控代码中收集任务（按需附带 host 同步线索） | Collect → Dispatch → Report | 排好序的任务队列，每项附可以直接启动它的任务定义 |

括号中的阶段只在适用时运行：有 kernel hand-off 且 `kernel_backend` 不是 `none` 时才跑 Kernel；issue 模式下只有被分诊为 `performance` 的 issue 才跑 Performance。

任务从一份**任务定义**开始（[`templates/task_definition.md`](templates/task_definition.md)）：也就是 `petra.js` 接受的那些字段，每个角色读的都是同样的字段名。可以直接给出这些字段，也可以用一句话描述需求：这时先运行 Intake 阶段，把需求整理成任务定义，并在不改动任何东西的前提下核实能核实的内容（checkout、本机上的模型、GPU、issue）。如果任务定义仍缺少该模式需要的内容——issue、checkout、`feature` 和 `perf` 需要的模型、`perf` 需要的固定负载——就什么都不启动，而是返回问题，每个字段一个，并尽量附上选项或默认值。完整的任务定义会跳过 Intake。

实现阶段一次只处理一个工作包；独立的测试工程师会重新运行它的单元测试，检查这个测试在没有该改动时会失败，并做关闭特性时的检查；一直通不过的工作包会被回滚。验证失败交给排查者：它先做对照实验，再考虑加插桩，最后给出修复、证明该失败在基线上本就存在，或者给出无法定论的结论并停止任务。在 PR 之前，审阅者像维护者一样阅读 diff 和证据，并以一份已知 reward hack 目录为起点——也就是让数字变好、却违背了它本来含义的改动（[`knowledge/reward_hacks.md`](knowledge/reward_hacks.md)）；要求的修改，以及为每个确认的 hack 写的测试，都会变成工作包，重新经过 Implement 和 Verify。性能数据只有在 Setup 时固定的负载上、在任务所针对的服务路径上测得才算数，而且收益还必须在与负载一起固定下来的 held-out 工作点上同样成立（[`knowledge/perf_evaluation.md`](knowledge/perf_evaluation.md) §3）。

kernel 级的工作——调优 Petra 为某个特性写的 kernel，或者 kernel 级的性能机会——会在 Implement 和 Verify 之间的 Kernel 阶段交给 **kernel 工作流后端**（[`knowledge/kernel_backends.md`](knowledge/kernel_backends.md)）：

| `kernel_backend` | hand-off 的处理方式 |
|---|---|
| `none`（默认） | 连同其材料一起记录在报告里，不运行任何东西 |
| `geak` | 由 GEAK 的 `kernel_workflow/kernel_lane.js` 从 `kernel_backend_dir` 指定的 GEAK checkout 运行（嵌套一层，与 GEAK 的 e2e_workflow 做法相同） |
| `command` | 由 `kernel_backend_command` 指定的任意其他命令行工具运行 |

收益会以工作包的形式回来：由 implementer 集成，再由 Petra 自己的门禁评判。后端失败或者没有找到收益，都不会阻塞任务。

## 角色

每个阶段调用一个角色：一个读取 `roles/<role>.md`、完成自己那部分工作并返回结构化 JSON 的 agent；`petra.js` 持有这些 schema，并且只根据其中的必填字段做分支。所有角色都遵守四条规则：

- 只有 **implementer** 修改框架源码，而且只在任务的 worktree 里改；
- 负责测量的角色（test engineer、verify engineer、performance engineer）、intake 和 reviewer 从不修改框架源码；负责测量的角色从不复用别人的数据，而是全部重新跑一遍；
- **curator** 只修改 Petra 自己的 `knowledge/`，并且不提交，留给人审阅；
- 没有任何角色会 push 或发帖：PR engineer 只返回确切的 `git push` 命令，issue 回复都是草稿。

| 角色 | 阶段 | 职责 |
|---|---|---|
| `intake` | Intake | 把一句话的需求或不完整的定义整理成任务定义：判断模式，用只读检查补全字段，把采用的默认值记为假设；缺任务依据、模型或负载，或者某项信息要付出代价才能拿到时，提问而不是猜；拒绝 Petra 不做的事 |
| `director` | Setup、Spec、Report | 创建运行目录、任务分支和 worktree，固定 commit、镜像和 GPU 并跑基线；写出验收标准可测量的特性说明（feature spec）；为每种结局写最终报告，并写明人接下来该做什么 |
| `scout` | Collect | 用下文的脚本收集候选任务 |
| `dispatcher` | Dispatch | 确定每个候选任务的差距类型、难度级别、CUDA 依赖及其在 AMD 上的起点、工作量和优先级，并排序成队列 |
| `analyst` | Recon | 把特性涉及的每个子系统映射到目标框架中的文件、函数和挂载点，并列表说明源设计的哪些假设在 AMD 上成立；只读不写 |
| `architect` | Design、Plan | 把 recon 或 profile 的结果拆成可以单独测试的工作包，附上不变量、显存预算、同步方式、启动时的拒绝条件和测试计划；标出必须由人审阅的设计；把每个性能机会分配给 Petra、kernel 后端或 Hyperloom |
| `issue_triager` | Triage、Reproduce | 根据 issue、评论和关联 PR 确定优先级和处理方式；起草回复；写出作为该 issue 门禁的复现步骤 |
| `ci_guardian` | Classify、Bisect | 给变红的 job 分类（代码回归、依赖升级、测试缺陷、偶发、基础设施），后两类移交出去；找到并确认引入问题的 commit，规划修复 |
| `implementer` | Implement | 一次一个工作包，diff 尽量小，关闭特性时行为不变，只影响 HIP 或放在开关后面；编写带单元测试的功能性 kernel（调优走 hand-off）；应用现成的 PR 和验证过的 kernel 收益；回滚失败的工作包 |
| `test_engineer` | Implement | 在每个工作包的 commit 上重新运行它的单元测试，检查这个测试在没有该改动时会失败（在父 commit 或故意改坏的副本上），并检查关闭特性时行为不变 |
| `verify_engineer` | Verify | 在全新启动的服务上对照同模式基线运行正确性门禁（G0、G2–G4、组合性、模式专属门禁），对每个失败分类计数 |
| `investigator` | Investigate、Diagnose | 先跑对照实验，再一次只验证一个机制，并维护假设台账；返回修复工作包、基线同样存在的已知问题、无法定论的结论，或者（对 issue 而言）不在 AMD 这一侧的根因；探测代码只放在开关后面 |
| `perf_engineer` | Profile、Performance | 先确认运行走了预期的路径，再把稳态 trace 整理成固定的表格（kernel、重叠、融合模式、层）、指标和带上限的优化机会；在固定负载上以同等预算评估改动，对照噪声、守护负载和 held-out 工作点，并逐项检查已知的测量类 hack |
| `reviewer` | Review | 像维护者一样阅读 diff 和证据，以已知 reward hack 目录为起点：shape、dtype、并行布局、graph、回退路径、不造成损害、框架的惯例、公平的基准测试；要求的修改，以及为每个确认的 hack 写的测试，以工作包形式返回；可以换用另一个模型（`review_model`） |
| `kernel_liaison` | Kernel | 把 kernel hand-off 转成后端的任务，运行 `command` 类后端，依据后端自身的验证评判结果，并把收益作为工作包返回 |
| `pr_engineer` | PR | 代码整洁、lint、CI 注册、每个工作包一个 commit、试合并 main、在最终 commit 上检查关闭特性时的行为，写 PR 描述和 push 命令 |
| `curator` | Report | 把这次运行证实的内容写进 `knowledge/`（已知问题、特性 skill、CUDA → AMD 对照条目、新发现的 reward hack、方法经验），每个数字都能追溯到这次运行 |

## 安装

Petra 像 GEAK 一样，以 root 身份运行在 ROCm 容器里：Claude Code、Petra、git 以及框架的服务和测试都在容器里运行，紧挨着 GPU 和框架的 Python 环境。容器是一次性的（`scripts/run_docker.sh` 每次都新建一个），所以需要长期保留的东西都放在宿主机的 `/home` 下，并以相同路径挂载进容器：只装一次的 Claude Code、它的状态、各个 checkout 和你的 key。一次运行以 root 身份写进 checkout 的文件会还给原来的属主（[`scripts/restore_owner.sh`](scripts/restore_owner.sh)、[`knowledge/env_hygiene.md`](knowledge/env_hygiene.md)），所以宿主机上的 git 和你的 `git push` 照常可用。

除了容器（run_docker.sh 按设计会替换它），每一步都可以重复执行：先检查，保留已有的，只补缺的。不会删除、覆盖或重新克隆任何东西。

### 宿主机需要什么

- 装有 AMD Instinct GPU（MI300 或 MI350 系列）且已加载 ROCm 驱动的 Linux（存在 `/dev/kfd`）。
- 你能使用的 Docker（用户在 `docker` 组里，或者有 sudo），以及 git、curl、python3 和 tmux。
- 能访问 claude.ai、github.com 和 Docker Hub；每个 sglang 镜像约需 45 GB 磁盘。
- 一个 Anthropic API key 或网关；两者都没有时，用 Claude 订阅账号登录。
- 模型权重放在会挂载进容器的目录里（`/data`、`/mnt`、`/home` 等）：Petra 从不下载权重。

### 1. 安装 Claude Code 并保存 key（宿主机）

```bash
command -v claude >/dev/null || [ -x ~/.local/bin/claude ] || curl -fsSL https://claude.ai/install.sh | bash
~/.local/bin/claude --version    # 需要 2.1.177 或更高版本：从这个版本起才有 petra.js 运行所需的 Workflow 工具
[ -e ~/.petra_env ] || (umask 077 && echo 'export ANTHROPIC_API_KEY=sk-ant-...' > ~/.petra_env)
```

原生安装器把 Claude Code 装在 `~/.local/bin`，它在你的 home 里，而容器会挂载这个目录，容器就是这样调用它的。宿主机负责更新它，容器从不更新它。

`~/.petra_env` 把 key 保存在宿主机上，只有你能读取，每个容器都会加载它。网关配置也写在这个文件里（`ANTHROPIC_BASE_URL` 加上 `ANTHROPIC_AUTH_TOKEN` 或 `ANTHROPIC_CUSTOM_HEADERS`），`GITHUB_TOKEN` 也是；没有它，scan 和 issue 运行每分钟只能做 10 次 GitHub 搜索。如果用 Claude 订阅而不是 key，就不写 key，在首次启动时登录（第 4 步）。

### 2. 启动容器（宿主机）

```bash
[ -d ~/Petra/.git ] || git clone https://github.com/At1a8/Petra ~/Petra
tmux new -s petra                # 一次运行要几个小时；连接断开后 tmux 能让它继续跑
~/Petra/scripts/run_docker.sh    # NAME 默认是你的用户名
```

[`scripts/run_docker.sh`](scripts/run_docker.sh) 就是常见的 ROCm `run_docker.sh`：一个带 GPU 的特权容器，以相同路径挂载 `/home` 和存在的数据目录（`/data`、`/mnt` 等），并打开一个 root shell。

- **镜像。** 任务要在最新的 sglang 上测试，所以默认使用 ROCm 10、MI35x 下最新的每日 `rocm/sgl-dev` 镜像（[`scripts/latest_image.py`](scripts/latest_image.py)，例如 `v0.5.23-rocm10-mi35x-20261103`；同一页面上的 `miles` 镜像用于强化学习，会被跳过）。每天的新镜像在第一次使用时拉取，约 43 GB。MI30x 设置 `IMAGE_VARIANT=rocm10-mi30x`；要固定镜像，设置 `IMAGE=rocm/sgl-dev:<tag>`。
- **测的是哪份代码。** 镜像提供 PyTorch、aiter、sgl-kernel 以及它自带的一份 sglang。Petra 测试的是任务 worktree 里的代码（从当前上游 main 创建），方法是把它放在 `PYTHONPATH` 最前面；运行记录会写下镜像、镜像里 sglang 的版本和 worktree 的基础 commit。
- **每次都是新容器。** 它会先删除同名的旧容器，连同其中仍在运行的东西。要回到正在运行的容器，重新连上 tmux（`tmux attach -t petra`）或在容器里开一个 shell（`docker exec -it <name> bash`），不要再次运行 run_docker.sh。你自己的 run_docker.sh 也可以用，只要它以相同路径挂载 `/home`。

此时还不能调用 `claude`：宿主机上的程序通过 `/home` 挂载出现在容器里，但不在 root 的 `PATH` 上（`claude: command not found`）。第 3 步会创建链接；容器里不安装任何东西。

### 3. 安装 Petra（容器内，每个新容器都要做）

```bash
cd /home/<you>/Petra && python3 -B -m petra.bootstrap --framework-dir /home/<you>/sglang
source ~/.bashrc
claude --version    # 宿主机上的 Claude Code
```

| 步骤 | 在新容器里做什么 |
|---|---|
| `claude` | 创建链接 `/usr/local/bin/claude`，指向宿主机的 `/home/<you>/.local/bin/claude`；只有宿主机上没有 Claude Code 时才在容器里安装 |
| Claude Code 状态 | 保存在宿主机的 `/home/<you>/.petra/claude`（`CLAUDE_CONFIG_DIR`，与你自己的 `~/.claude` 分开）：首次启动时的回答和 `/login` 登录不会随容器消失 |
| git | 信任挂载进来的 checkout，它们属于你而不是 root（`safe.directory '*'`） |
| shell | 在 root 的 `~/.bashrc` 里设置 `PYTHONDONTWRITEBYTECODE=1`（你的 checkout 里不会出现 root 所有的 `__pycache__`）、`DISABLE_AUTOUPDATER=1`（由宿主机更新 Claude Code），并加载 `/home/<you>/.petra_env` |
| 框架（`--framework-dir`） | 已有的 checkout 原样使用（浅克隆只会提示，不会加深）；缺失时带完整历史克隆（`--filter=blob:none`），并把属主交给你 |
| 检查 | GPU、sglang、API 访问、`GITHUB_TOKEN`（只检测） |

`python3 -B` 让这第一次运行不会往 checkout 里写 root 所有的 `__pycache__`。这条命令从不写入 key。

### 4. 启动 Claude Code 并交给它任务（容器内）

```bash
cd /home/<you>/Petra && IS_SANDBOX=1 claude --dangerously-skip-permissions
```

`IS_SANDBOX=1` 让 Claude Code 以 root 身份自动批准权限，Petra 的 agent 需要这一点。第一次启动会问几个问题；回答保存在 `/home/<you>/.petra/claude`，之后的新容器不会再问。其中有三个问题，按默认选项会卡住：

| 问题 | 回答 |
|---|---|
| Do you want to use this API key?（来自 `~/.petra_env` 的 key） | **Yes**；默认的 No 会转去让你登录 |
| Is this a project you trust? | **Yes, I trust this folder**；默认选项会退出 |
| Bypass Permissions mode | **Yes, I accept**；默认选项会退出 |

没有 key 时，改为选择一种登录方式并登录一次。然后输入：

```
use /home/<you>/Petra/petra.js with mode=scan, petra_dir=/home/<you>/Petra,
framework_dir=/home/<you>/sglang
```

scan 不改任何代码。它收集上次扫描以来（没有上次扫描时为最近 7 天）开放的 AMD issue、变红的 AMD CI、CUDA 优先的上游改动和硬件差距，排好序，写出 `exp/scan_<time>/task_queue.md`，每项附可以启动它的任务定义。要接手一个任务，并在复现之后停下来确认环境，就给出它的字段：

```
use /home/<you>/Petra/petra.js with mode=issue, task=https://github.com/sgl-project/sglang/issues/41299,
petra_dir=/home/<you>/Petra, framework_dir=/home/<you>/sglang, model_path=<weights>,
gpu_ids=0, stop_after=Reproduce
```

或者直接用一句话描述，让 Intake 阶段写出任务定义：

```
use /home/<you>/Petra/petra.js with petra_dir=/home/<you>/Petra, request="DeepSeek-V4.1 在 MI355X 上
decode 太慢，帮我优化；我的 sglang 在 /home/<you>/sglang"
```

如果缺了什么（这里缺的是每次测量都用的固定负载），这次运行什么都不启动，返回 `status: needs_input`，每个字段一个问题。在对话里回答后，Claude Code 会用同样的参数加上 `answers={"workload": ...}` 再次运行 `petra.js`。[运行](#运行)一节列出了全部参数。

### 5. 运行结束后（宿主机）

每次运行都把报告留在 `/home/<you>/Petra/exp/` 下它自己的运行目录里（PR 准备好时是 `validation_report.md`，其他结局是 `report.md`；运行结果中的 `report_path` 给出路径），旁边就是任务的 worktree 和分支，root 写在那里的文件已经还给你。Petra 从不 push：报告里列出了 PR 描述和确切的 `git -C <worktree> push ...` 命令。请在宿主机上执行它，你的 git 凭据在那里。

### 重复执行与选项

`petra.bootstrap` 的每一步都会报告 `kept`、`installed`、`updated`、`added`、`created`、`skipped` 或 `failed`；最后有一份汇总，"下一步"只列出仍然缺少的内容，任何一步失败时退出码为 1。在新容器里，它几秒钟就能重建链接以及 git、shell 和 Claude Code 状态的设置，什么都不用安装。`--claude-only` 只运行 Claude Code 相关的步骤，`--check` 只运行检查。在容器里，`cd /home/<you> && pip install -v git+https://github.com/At1a8/Petra` 会按 GEAK 的方式执行第 3 步（加 `-v` 时 pip 才显示输出；用了缓存的 wheel 时会跳过）。

| 变量 | 使用者 | 默认值 |
|---|---|---|
| `IMAGE` | `scripts/run_docker.sh` | `IMAGE_VARIANT` 下最新的每日 `rocm/sgl-dev` 镜像（访问不了 Docker Hub 时用本地最新的） |
| `IMAGE_VARIANT`、`NAME`、`EXTRA_MOUNTS` | `scripts/run_docker.sh` | `rocm10-mi35x`；你的用户名；额外要挂载的目录，用空格分隔 |
| `PETRA_HOME` | bootstrap | `./Petra`，或你所在的 checkout |
| `PETRA_REPO_URL`、`PETRA_REF` | bootstrap | `https://github.com/At1a8/Petra.git`，它的默认分支 |
| `CLAUDE_VERSION`、`CLAUDE_BIN_DIR` | bootstrap | `latest`，`~/.local/bin` |
| `CLAUDE_CONFIG_DIR` | bootstrap、Claude Code | 容器里的 root 用 `/home/<you>/.petra/claude`；已经设置时原样使用 |
| `PETRA_FRAMEWORK_DIR`、`PETRA_FRAMEWORK_REPO` | bootstrap：`--framework-dir`、`--framework-repo` | 无（跳过该步）；sglang |
| `PETRA_SKIP_BOOTSTRAP` | bootstrap | 不设置；设置后安装这个包时没有任何副作用（CI、构建镜像） |

## 运行

Petra 是一个 GEAK 风格的工作流：`petra.js` 负责控制流，`roles/` 是 agent 的指令，`knowledge/` 是方法，`templates/` 是产物模板。在 Claude Code 里，用一句话说出 `petra.js` 和它的参数即可，就像 [第 4 步](#4-启动-claude-code-并交给它任务容器内)那样。只有两种情况需要 GEAK：使用 `geak` kernel 后端（`kernel_backend_dir`），以及在 Claude Code 之外运行 `petra.js`，这时要用 GEAK 的工作流运行时（Node 20+；dry run 用的也是它）：

```bash
node /path/to/GEAK/interface/runtime/engine/run_workflow.mjs petra.js --agent codex \
  --args '{"mode":"scan","petra_dir":"'"$PWD"'","framework_dir":"/path/to/sglang"}'
```

| 参数 | 含义 |
|---|---|
| `petra_dir` | 这个 checkout 的绝对路径（必填） |
| `request` | 用一句话描述的任务，任何语言都可以；Intake 阶段会把它整理成下面这些字段（`roles/intake.md`），同时给出的字段优先 |
| `answers` | 对 `needs_input` 结果的回答，格式为 `{"<field>": <value>}`，与之前相同的参数一起传入 |
| `mode` | `feature` \| `issue` \| `ci` \| `perf` \| `scan`（必填；没给时从 `request` 推断） |
| `task` | 上游 PR / 设计、issue URL、CI job / 簇，或性能目标（`scan` 以外必填） |
| `goal` | 什么算完成；可以测量的模式要写成可测量的；spec 和性能计划都要回应它 |
| `framework_dir` | 框架的 checkout；Petra 在它的 worktree 里工作（`scan` 以外必填） |
| `model_path` | 基线和各项门禁运行的模型（`feature` 和 `perf` 必填） |
| `framework`、`platform`、`gpu_ids` | 目标与环境（`sglang`；`gpu_ids` 为空时由 Setup 挑选空闲的 GPU） |
| `workload` | 每次测量都使用的基准负载，例如 `{"isl":8192,"osl":1024,"conc":64}`；`perf` 必填，在 Setup 时固定 |
| `container` | 只在 Petra 运行在宿主机上时使用：框架所在的容器，通过 `docker exec` 访问 |
| `exp_root` | 运行目录放在哪里（默认 `<petra_dir>/exp`） |
| `kernel_backend` | `none`（默认）\| `geak` \| `command`：kernel hand-off 交给谁 |
| `kernel_backend_dir` | `geak` 后端：提供 `kernel_workflow/kernel_lane.js` 的 GEAK checkout |
| `kernel_backend_command` | `command` 后端：带 `{task_dir}`、`{out_dir}`、`{gpu_ids}` 占位符的 shell 命令 |
| `kernel_budget` | kernel 后端的优化轮数（默认 6） |
| `apply_prs` | `perf`：要应用并做 A/B 的候选 PR |
| `sources`、`since` | `scan`：`upstream`、`issues`、`ci`、`hardware`、`perf` 中的任意几个；时间窗口的起点 |
| `stop_after` | 在指定阶段之后停下（例如 `Design`） |
| `resume_from`、`run_dir` | `feature`：人审阅通过 `design.md` 后，用 `implement` 继续一个停在 Design 的运行 |
| `review_model` | reviewer 使用的模型，随它的 agent 调用一起传入（GEAK 运行时支持按调用指定模型；其他运行时视其能力而定） |
| `max_fix_rounds`、`max_investigate_rounds`、`max_review_rounds`、`max_work_packages`、`agent_retries`、`agent_timeout_ms` | 预算 |

除 `petra_dir`、`request`、`answers`、`exp_root`、`review_model` 和各项预算外，其余参数都属于任务定义；每次已启动的运行，其结果都会记录所用的任务定义（`task_def`）、每个字段的来源（`provenance`）以及 intake 的假设（`assumptions`）。

人工检查点：Intake 的提问（`needs_input`）；任何 `stop_after`；L3 任务和 architect 标记的设计会停在 Design（`awaiting_design_review`）；被 reviewer 标为 `blocked` 的审阅会在 PR 之前停下；PR engineer 只返回确切的 `git push` 而不执行；issue 回复是运行目录里的草稿。无论结局如何，每次运行都以一份报告结束。

框架自带的 skill（sglang 的 `.agents/skills/`）以引用方式使用，从不复制：每个角色从任务 worktree 中读取 [`knowledge/frameworks/sglang/skills.md`](knowledge/frameworks/sglang/skills.md) 为它列出的 skill，因此与它正在修改的代码版本一致；ROCm 上的差异见 [`knowledge/platforms/rocm_skills.md`](knowledge/platforms/rocm_skills.md)。

## 脚本

全部是只用标准库的 Python；访问 GitHub 的脚本读取 `GITHUB_TOKEN` 或 `GH_TOKEN`（没有 token 时搜索 API 每分钟只允许 10 次请求）。

| 脚本 | 任务来源 |
|---|---|
| `scripts/scan_issues.py` | 开放的 AMD issue，附关联 PR、回复情况和预计的 60 天自动关闭日期 |
| `scripts/scan_ci.py` | Failure Tracker 状态 → 带状态和起始日期的失败簇 |
| `scripts/scan_upstream.py` | 已合入的上游提交：新增的 CUDA 门控、CUDA 优先的特性、新模型 |
| `scripts/audit_platform_gates.py` | 换到新架构时需要重新检查的平台门控（在 gfx1250 上为真的能力判断、wave32 假设） |
| `scripts/audit_host_syncs.py` | 热路径上的 host-device 同步和拷贝候选点（供 profile 参考的线索） |

`scripts/restore_owner.sh`（POSIX sh）把 root 在容器里写下的文件还给所在 checkout 的属主；每个 agent 在 git 写操作之后都会运行它（[`knowledge/env_hygiene.md`](knowledge/env_hygiene.md)）。`scripts/check_framework_skills.py --framework-dir <dir>` 拿 skill 索引和框架 checkout 对照：索引里提到但已经不存在的 skill，以及索引还没收录的新 skill（scout 每次 scan 都会运行它）。`scripts/latest_image.py [--variant rocm10-mi30x]` 输出最新的每日 sglang 镜像（`run_docker.sh` 从它启动；director 拿运行所用的镜像和它比较）。

## 测试

```bash
GEAK_HOME=/path/to/GEAK node tests/dry_run.mjs   # 在 GEAK 运行时上走遍 petra.js 的每条控制路径，不需要 GPU
python3 -m unittest discover -s tests             # 脚本的解析与规则、bootstrap、两份 README 的一致性；离线运行
```

## 目录结构

```
Petra/
├── petra.js                 # 编排：五种模式、门禁、预算、回滚、kernel 后端
├── roles/                   # intake, director, scout, dispatcher, analyst, architect, implementer,
│                            # test_engineer, verify_engineer, investigator, perf_engineer, issue_triager,
│                            # ci_guardian, kernel_liaison, reviewer, pr_engineer, curator
├── knowledge/
│   ├── dev_methodology.md   # 阶段、产物、门禁（契约）
│   ├── validation_doctrine.md, debugging_playbook.md, perf_evaluation.md, env_hygiene.md, pr_playbook.md
│   ├── guardrails.md        # 安全约束与社区行为准则
│   ├── reward_hacks.md      # 让数字变好却违背其本意的改动：怎么识别、用什么堵住
│   ├── dispatch.md, issue_triage.md, ci_triage.md, system_perf.md, composability.md, kernel_backends.md
│   ├── frameworks/sglang/feature_dev_map.md, platforms/rocm.md, known_issues.md
│   ├── frameworks/sglang/skills.md, platforms/rocm_skills.md   # sglang 自带 skill 的索引 + ROCm 说明
│   └── feature_skills/      # 按特性整理的已验证方案（首个是 hisparse-v2）
├── templates/               # task_definition, feature_spec, design, experiment_ledger, validation_report,
│                            # pr_body, issue_triage, ci_triage, perf_analysis, task_queue
├── scripts/                 # 任务收集、审计、run_docker.sh、latest_image.py、restore_owner.sh
├── petra/bootstrap.py       # 安装第 3 步，在容器内运行；可以重复执行
├── setup.py, pyproject.toml # 打包；pip 构建 wheel 时 setup.py 会运行 bootstrap
├── tests/                   # petra.js 的 dry run，脚本、bootstrap 和 README 的单元测试
├── README.md, README.zh-CN.md
└── docs/design.md
```

## 与 GEAK 和 Hyperloom 的关系

- kernel 的速度是 kernel 工作流的事，无论选的是哪个后端（GEAK 的 kernel lane 是其中之一）：Petra 写出带单元测试的功能性 kernel，把算子规格连同作为判定标准的参考实现一起移交，再集成验证过的收益。
- 针对某个负载搜索 flag 和 backend 属于 Hyperloom 和 GEAK `e2e_workflow` 的工作；它们发现的上游候选是 Petra 的输入，Petra 落地的特性又成为它们的可选项。

## 来源

方法论、验证准则、已知问题登记表、模板和 HiSparse V2 特性 skill 来自 GEAK 的 `framework_workflow`（分支 `fangyuan/framework_agent_init`，commit `fc857c9`），当时它处在以知识库为主的阶段。Petra 在此基础上补上了当时计划中的编排、各个角色、设计中的 issue / CI / 性能 / scan 入口，以及任务收集脚本。

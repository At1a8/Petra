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
| `scan` | 无——框架当天的状态：main 上的 AMD CI、开放的 AMD 用户 issue、AMD 需要跟进的上游改动（平台门控和 host 同步线索按需附带） | Collect → Dispatch → Report | 日报，发成 Petra 仓库里当天的 issue，附排好序的任务和启动每个任务的定义 |

括号中的阶段只在适用时运行：有 kernel hand-off 且 `kernel_backend` 不是 `none` 时才跑 Kernel；issue 模式下只有被分诊为 `performance` 的 issue 才跑 Performance。

任务从一份**任务定义**开始（[`templates/task_definition.md`](templates/task_definition.md)）：也就是 `petra.js` 接受的那些字段，每个角色读的都是同样的字段名。可以直接给出这些字段，也可以用一句话描述需求：这时先运行 Intake 阶段，把需求整理成任务定义，并在不改动任何东西的前提下核实能核实的内容（checkout、本机上的模型、GPU、issue）。如果任务定义仍缺少该模式需要的内容——issue、checkout、`feature` 和 `perf` 需要的模型、`perf` 需要的固定负载——就什么都不启动，而是返回问题，每个字段一个，并尽量附上选项或默认值。完整的任务定义会跳过 Intake。

实现阶段一次只处理一个工作包；独立的测试工程师会重新运行它的单元测试，检查这个测试在没有该改动时会失败，并做关闭特性时的检查；一直通不过的工作包会被回滚。验证失败交给排查者：它先做对照实验，再考虑加插桩，最后给出修复、证明该失败在基线上本就存在，或者给出无法定论的结论并停止任务。在 PR 之前，审阅者像维护者一样阅读 diff 和证据，并以一份已知 reward hack 目录为起点——也就是让数字变好、却违背了它本来含义的改动（[`knowledge/reward_hacks.md`](knowledge/reward_hacks.md)）；要求的修改，以及为每个确认的 hack 写的测试，都会变成工作包，重新经过 Implement 和 Verify。性能数据只有在 Setup 时固定的负载上、在任务所针对的服务路径上测得才算数，而且收益还必须在与负载一起固定下来的 held-out 工作点上同样成立（[`knowledge/perf_evaluation.md`](knowledge/perf_evaluation.md) §3）。

kernel 级的工作——调优 Petra 为某个特性写的 kernel，或者 kernel 级的性能机会——会在 Implement 和 Verify 之间的 Kernel 阶段交给 **kernel 工作流后端**（[`knowledge/kernel_backends.md`](knowledge/kernel_backends.md)）：

| `kernel_backend` | hand-off 的处理方式 |
|---|---|
| `none`（默认） | 连同其材料一起记录在报告里，不运行任何东西 |
| `geak` | 由 GEAK 的 `kernel_workflow/kernel_lane.js` 从 `kernel_backend_dir` 指定的 GEAK checkout 运行（嵌套一层，与 GEAK 的 e2e_workflow 做法相同） |
| `command` | 由 `kernel_backend_command` 指定的任意其他命令行工具运行 |

收益会以工作包的形式回来：由 implementer 集成，再由 Petra 自己的门禁评判。后端失败或者没有找到收益，都不会阻塞任务。集成后的 kernel 如果在 Verify 失败，会先退回功能版 kernel，再带着这个失败用例作为新增测试交给后端重跑一次；只有通过了，才会再次集成。

## 角色

每个阶段调用一个角色：一个读取 `roles/<role>.md`、完成自己那部分工作并返回结构化 JSON 的 agent；`petra.js` 持有这些 schema，并且只根据其中的必填字段做分支。所有角色都遵守四条规则：

- 只有 **implementer** 修改框架源码，而且只在任务自己的分支上改；
- 负责测量的角色（test engineer、verify engineer、performance engineer）、intake 和 reviewer 从不修改框架源码；负责测量的角色从不复用别人的数据，而是全部重新跑一遍；
- **curator** 只修改 Petra 自己的 `knowledge/`，并且不提交，留给人审阅；
- 没有任何角色会 push，或往上游发帖：PR engineer 只返回确切的 `git push` 命令，issue 回复都是草稿；会发出去的只有 Petra 自己仓库里的两样东西：scan 的日报（一个 issue），以及 curator 的知识更新（一个由人合并的 PR）。

| 角色 | 阶段 | 职责 |
|---|---|---|
| `intake` | Intake | 把一句话的需求或不完整的定义整理成任务定义：判断模式，用只读检查补全字段，把采用的默认值记为假设；缺任务依据、模型或负载，或者某项信息要付出代价才能拿到时，提问而不是猜；拒绝 Petra 不做的事 |
| `director` | Setup、Spec、Report | 创建运行目录和任务自己的分支，固定 commit、镜像和 GPU 并跑基线；写出验收标准可测量的特性说明（feature spec）；为每种结局写最终报告，并写明人接下来该做什么 |
| `scout` | Collect | 用下文的脚本收集候选任务 |
| `dispatcher` | Dispatch | 确定每个候选任务的差距类型、难度级别、CUDA 依赖及其在 AMD 上的起点、工作量和优先级，并排序成队列 |
| `analyst` | Recon | 把特性涉及的每个子系统映射到目标框架中的文件、函数和挂载点，并列表说明源设计的哪些假设在 AMD 上成立；只读不写 |
| `architect` | Design、Plan | 把 recon 或 profile 的结果拆成可以单独测试的工作包，附上不变量、显存预算、同步方式、启动时的拒绝条件和测试计划；标出必须由人审阅的设计；把每个性能机会分配给 Petra、kernel 后端或 Hyperloom |
| `issue_triager` | Triage、Reproduce | 根据 issue、评论和关联 PR 确定优先级和处理方式；起草回复；写出作为该 issue 门禁的复现步骤 |
| `ci_guardian` | Classify、Bisect | 给变红的 job 分类（代码回归、依赖升级、测试缺陷、偶发、基础设施），后两类移交出去；找到并确认引入问题的 commit，规划修复 |
| `implementer` | Implement | 一次一个工作包，diff 尽量小，关闭特性时行为不变，只影响 HIP 或放在开关后面，提交时已通过 lint、测试已注册；编写带单元测试的功能性 kernel（调优走 hand-off）；应用现成的 PR 和验证过的 kernel 收益；回滚失败的工作包 |
| `test_engineer` | Implement | 在每个工作包的 commit 上重新运行它的单元测试，检查这个测试确实可能失败（改变行为的改动在父 commit 上验证，不改变行为的改动在故意改坏的副本上验证），并检查关闭特性时行为不变 |
| `verify_engineer` | Verify | 在全新启动的服务上对照同模式基线运行正确性门禁（G0、G2–G4、组合性、模式专属门禁），对每个失败分类计数 |
| `investigator` | Investigate、Diagnose | 先跑对照实验，再一次只验证一个机制，并维护假设台账；返回修复工作包、基线同样存在的已知问题、无法定论的结论，或者（对 issue 而言）不在 AMD 这一侧的根因；探测代码只放在开关后面 |
| `perf_engineer` | Profile、Performance | 先确认运行走了预期的路径，再把稳态 trace 整理成固定的表格（kernel、重叠、融合模式、层）、指标和带上限的优化机会；在固定负载上以同等预算评估改动，对照噪声、守护负载和 held-out 工作点，并逐项检查已知的测量类 hack |
| `reviewer` | Review | 像维护者一样阅读 diff 和证据，以已知 reward hack 目录为起点：shape、dtype、并行布局、graph、回退路径、不造成损害、框架的惯例、公平的基准测试；要求的修改，以及为每个确认的 hack 写的测试，以工作包形式返回；可以换用另一个模型（`review_model`） |
| `kernel_liaison` | Kernel | 把 kernel hand-off 转成后端的任务，运行 `command` 类后端，依据后端自身的验证评判结果，并把收益作为工作包返回 |
| `pr_engineer` | PR | 不改任何代码：检查代码整洁、lint 和 CI 注册（缺什么就作为工作包退回），在不改变代码内容的前提下整理成每个工作包一个 commit，试合并 main 只用来报告冲突，在最终 commit 上检查关闭特性时的行为，写 PR 描述和 push 命令 |
| `curator` | Report | 把这次运行证实的内容写进 `knowledge/`（已知问题、特性 skill、CUDA → AMD 对照条目、新发现的 reward hack、方法经验），每个数字都能追溯到这次运行，并作为 PR 提到 Petra 仓库 |

## 安装

Petra 像 GEAK 一样，以 root 身份运行在 ROCm 容器里：Claude Code、Petra、git 以及框架的服务和测试都在容器里运行，紧挨着 GPU 和框架的 Python 环境。每个任务用一个自己的容器，任务用到的一切都在这个容器里：`/workspace` 里的 Petra checkout 和它的运行目录，以及镜像自带的 sglang `/sgl-workspace/sglang`，任务在它上面开自己的分支修改。容器之间不共享这些，所以互不干扰；它们随所在的容器保留，容器删除时一起删除。所有容器都要用的东西留在宿主机上你的 home 里，并以相同路径挂载进容器：只装一次的 Claude Code、它的状态和你的 key。

每一步都可以重复执行：先检查，保留已有的，只补缺的；再次运行 run_docker.sh 会回到原来的容器。命令里的 `检查 || 动作` 表示只有检查不通过时才执行动作：在新机器上每个动作都会执行，再运行一次则全部跳过。除了第 3 步丢弃镜像构建对 `/sgl-workspace/sglang` 打包文件的改动，不会删除、覆盖或重新克隆任何东西。

### 宿主机需要什么

- 装有 AMD Instinct GPU（MI300 或 MI350 系列）且已加载 ROCm 驱动的 Linux（存在 `/dev/kfd`）。
- 你能使用的 Docker（用户在 `docker` 组里，或者有 sudo），以及 git、curl 和 python3。
- 能访问 claude.ai、github.com 和 Docker Hub；每个 sglang 镜像约需 45 GB 磁盘。
- 一个 AMD LLM 网关 key（`LLM_GATEWAY_KEY`）、Anthropic API key 或其他网关；都没有时，用 Claude 订阅账号登录。
- 一个只读的 GitHub token（`GITHUB_TOKEN`），强烈建议准备：scan 和 issue 运行要通过 GitHub API 读取数据。
- 模型权重放在会挂载进容器的目录里（`/data`、`/mnt`、`/home` 等）：Petra 从不下载权重。

### 1. 安装 Claude Code 并保存 key（宿主机）

```bash
command -v claude >/dev/null || [ -x ~/.local/bin/claude ] || curl -fsSL https://claude.ai/install.sh | bash
~/.local/bin/claude --version    # 需要 2.1.177 或更高版本：从这个版本起才有 petra.js 运行所需的 Workflow 工具
[ -e ~/.petra_env ] || (umask 077 && echo 'export LLM_GATEWAY_KEY=<your AMD LLM gateway key>' > ~/.petra_env)
(umask 077 && grep -qs GITHUB_TOKEN ~/.petra_env || echo 'export GITHUB_TOKEN=<your GitHub token>' >> ~/.petra_env)
```

原生安装器把 Claude Code 装在 `~/.local/bin`，它在你的 home 里，而容器会挂载这个目录，容器就是这样调用它的。宿主机负责更新它，容器从不更新它。

运行最后两行之前，先把 `<your AMD LLM gateway key>` 和 `<your GitHub token>` 换成你自己的值：每一行都只在 `~/.petra_env` 里还没有这个 key 时才写入，所以以后要换 key，直接编辑这个文件。`~/.petra_env` 把 key 保存在宿主机上，只有你能读取，每个容器都会加载它。

- **LLM key（必填）。** 写的是 AMD LLM 网关 key 时，第 3 步会让 Claude Code 走这个网关（`https://llm-api.amd.com/Unified`，key 放在 `Ocp-Apim-Subscription-Key` 请求头里），网关按 Claude 模型的常用名字提供服务。不在 AMD 内部时，改写成 `export ANTHROPIC_API_KEY=sk-ant-...`，或者其他网关（`ANTHROPIC_BASE_URL` 加上 `ANTHROPIC_AUTH_TOKEN` 或 `ANTHROPIC_CUSTOM_HEADERS`）。用 Claude 订阅时不写 key，在首次启动时登录（第 4 步）。
- **GitHub token（强烈建议）。** scan 和 issue 运行要通过 GitHub API 读取 issue、PR 和 CI 跟踪记录。没有 token 时，GitHub 对每个 IP 地址每小时只允许 60 次请求、每分钟 10 次搜索，同一出口 IP 下的所有人共用这个额度，扫描会非常慢，还可能中途停下；有 token 时每小时 5000 次。只读权限就够了，Petra 从不 push，也从不往上游发帖：在 github.com 上进入 Settings → Developer settings → Personal access tokens → Fine-grained tokens，权限选 *Public repositories (read-only)*（不勾选任何权限的 classic token 也可以）。
- **Petra 仓库 token（可选）。** Petra 会把结果发到它自己的仓库，开发者在 GitHub 网页上就能看到：scan 的日报发成当天的 issue（当天再扫一次会更新它，第二天的会把它关掉），curator 的知识更新则从 `petra/knowledge/<run>` 分支向 main 提一个 PR，由你审阅合并。这需要一个只对这个仓库有效的 token，这样它没法往别处发：fine-grained token，*Only select repositories* 选 `At1a8/Petra`，*Repository permissions* 里 *Issues*、*Contents* 和 *Pull requests* 都选 *Read and write*，然后以 `export PETRA_REPO_TOKEN=<token>` 写进 `~/.petra_env`。Petra 只 push `petra/` 开头的分支；在 GitHub 上给 main 开分支保护（要求通过 PR 合并），这个 token 就也改不了 main。没有这个 token 时，队列只留在运行目录里，知识更新只留在容器的 checkout 里，报告会给出发布它们的命令。

### 2. 启动容器（宿主机）

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/At1a8/Petra/main/scripts/run_docker.sh)    # NAME 默认是你的用户名
```

这一行下载 [`scripts/run_docker.sh`](scripts/run_docker.sh) 并运行它，所以宿主机上不需要 Petra 的代码；在 Petra 的 checkout 里直接运行 `scripts/run_docker.sh` 效果相同。它就是常见的 ROCm `run_docker.sh`：一个带 GPU 的特权容器，以相同路径挂载 `/home` 和存在的数据目录（`/data`、`/mnt` 等），并在容器的 `/workspace` 里打开一个 root shell。和很多同类脚本不同，它默认不挂载宿主机的 Docker socket（`DOCKER_SOCKET=1` 才挂）：Petra 的 agent 以 root 身份、自动批准权限运行，挂上 socket 就能操作宿主机上的所有容器。

- **镜像。** 任务要在最新的 sglang 上测试，所以默认使用 ROCm 10、MI35x 下最新的每日 `rocm/sgl-dev` 镜像（[`scripts/latest_image.py`](scripts/latest_image.py)，例如 `v0.5.23-rocm10-mi35x-20261103`；同一页面上的 `miles` 镜像用于强化学习，会被跳过）。每天的新镜像在第一次使用时拉取，约 43 GB。MI30x 设置 `IMAGE_VARIANT=rocm10-mi30x`；要固定镜像，设置 `IMAGE=rocm/sgl-dev:<tag>`。
- **测的是哪份代码。** 镜像提供 PyTorch、aiter、sgl-kernel，以及它自带的 sglang checkout `/sgl-workspace/sglang`（带完整历史），sglang 就是以 editable 方式从这里安装的：这里检出的是什么，运行的就是什么，所以不需要另外克隆或指定 sglang。第 3 步把它切到当前的 main；之后每个任务都在它上面、从最新的 main 开自己的分支，Setup 会先 fetch。在基础 commit 上跑的 baseline 和 scan 读的当前 main，用的是同一个仓库在运行目录下的 worktree（每个约 0.2 GB）。运行记录会写下镜像、镜像里 sglang 的版本和任务的基础 commit。
- **一个任务一个容器。** 用同一个 `NAME` 再次运行时，run_docker.sh 会回到那个容器（已停止的会先启动），`/workspace` 保持你离开时的样子：它从不删除容器。下一个任务换个名字开新容器（`NAME=<name>`），用的是最新的镜像；不再需要的容器用 `docker rm -f <name>` 删除，它的 `/workspace` 也随之删除。不管有多少个容器，一台机器同时只跑一个 Petra 任务（[运行](#运行)）。你自己的 run_docker.sh 也可以用，只要它以相同路径挂载你的 home，并把它作为 `PETRA_HOST_HOME` 传进容器（`-e PETRA_HOST_HOME=$HOME`）。

此时还不能调用 `claude`：宿主机上的程序通过 `/home` 挂载出现在容器里，但不在 root 的 `PATH` 上（`claude: command not found`）。第 3 步会创建链接；容器里不安装任何东西。

### 3. 在容器里配置 Petra（每个容器做一次）

这一步把 Petra 放进容器的 `/workspace`，并让容器能运行它，具体做什么见下表：

```bash
[ -d /workspace/Petra/.git ] || git clone https://github.com/At1a8/Petra /workspace/Petra
cd /workspace/Petra && python3 -B -m petra.bootstrap
source ~/.bashrc
claude --version    # 宿主机上的 Claude Code
```

| 步骤 | 在新容器里做什么 |
|---|---|
| 你宿主机上的 home | 通过 `PETRA_HOST_HOME` 找到（run_docker.sh 会传进来）：你的 Claude Code、它的状态和 `~/.petra_env` 都在那里。没有它就启动的容器什么都不会配置，因为那样的容器里 Claude Code 没有 key，会要求你登录；bootstrap 会报错，并说明怎样启动一个有它的容器 |
| `claude` | 创建链接 `/usr/local/bin/claude`，指向你在宿主机上的 `~/.local/bin/claude`；只有宿主机上没有 Claude Code 时才在容器里安装 |
| Claude Code 状态 | 保存在你宿主机上的 `~/.petra/claude`（`CLAUDE_CONFIG_DIR`，与你自己的 `~/.claude` 分开），你的各个容器共用：首次启动时的回答和 `/login` 登录只需做一次 |
| git | 信任宿主机挂载目录里的 checkout，它们属于你而不是 root（`safe.directory '*'`） |
| shell | 在 root 的 `~/.bashrc` 里设置 `PYTHONDONTWRITEBYTECODE=1`（你宿主机上的 checkout 里不会出现 root 所有的 `__pycache__`）、`DISABLE_AUTOUPDATER=1`（由宿主机更新 Claude Code），并加载你宿主机上的 `~/.petra_env`；设置了 `LLM_GATEWAY_KEY` 且没有 `ANTHROPIC_BASE_URL` 时，让 Claude Code 走 AMD LLM 网关 |
| 框架 | 镜像里的 `/sgl-workspace/sglang` 如果还是镜像留下的样子（detached 在构建时的 commit 上，打包文件被改成了 ROCm 版），就把它切到 main：丢弃这些打包改动，然后 `git checkout main`、`git pull`。之后不要在这里 `pip install -e`：这时它的 `pyproject.toml` 是上游默认的版本，会装进 CUDA 的包。已经在某个分支上、或者有其他改动的 checkout 原样保留；用 `--framework-dir` 可以改用宿主机上的 checkout（已有的原样使用，缺失时带完整历史克隆） |
| 检查 | GPU、sglang、API 访问、`GITHUB_TOKEN`，`~/.petra_env` 里设置的也算（只检测） |

只有 `/workspace/Petra` 还不存在时才会克隆；bootstrap 从不写入 key。

### 4. 启动 Claude Code 并交给它任务（容器内）

```bash
cd /workspace/Petra && IS_SANDBOX=1 claude --dangerously-skip-permissions
```

`IS_SANDBOX=1` 让 Claude Code 以 root 身份自动批准权限，Petra 的 agent 需要这一点。第一次启动会问几个问题；回答保存在你宿主机上的 `~/.petra/claude`，之后的新容器不会再问。其中有三个问题，按默认选项会卡住：

| 问题 | 回答 |
|---|---|
| Do you want to use this API key?（只在用 `ANTHROPIC_API_KEY` 时才问，网关 key 不会问） | **Yes**；默认的 No 会转去让你登录 |
| Is this a project you trust? | **Yes, I trust this folder**；默认选项会退出 |
| Bypass Permissions mode | **Yes, I accept**；默认选项会退出 |

有 key 时，首次启动不会要求登录。如果它让你选择登录方式（select a login method），或者显示 `Paste code here if prompted >`，说明这个 shell 里的 Claude Code 没有拿到 key：什么都不要输入，连按三次 Ctrl-C 退出，然后看第 3 步输出的最后几行，那里写明了缺什么。用 Claude 订阅、没有 key 时，这个登录才是入口：选择 *Claude account with subscription*，在任意浏览器里打开它打印出的 URL，登录后把页面上显示的授权码粘贴到这个提示后面。

启动完成后，最下面一行会一直显示 `bypass permissions on`：这是 `--dangerously-skip-permissions` 打开的模式，不是在问你问题。保持这个模式不变（Shift+Tab 会切换到执行命令前要等你确认的模式，Petra 的 agent 就会停住），在它上方的输入框里输入任务：

```
use /workspace/Petra/petra.js with mode=scan, petra_dir=/workspace/Petra
```

scan 不改任何代码。它写出框架当天的日报，覆盖上一份日报以来（没有时为最近 7 天）的情况：main 上的 AMD CI（每个失败的 job、从何时开始失败、日志里说了什么）、按 P0、P1、P2 分好的开放 AMD 用户 issue，以及 AMD 需要跟进的上游改动。它把其中的任务排好序写进 `exp/scan_<time>/task_queue.md`，每项附可以启动它的任务定义，并把日报去掉本机信息后，发成 Petra 仓库里当天的 issue。一天一份日报就够了：已有不到 24 小时的日报时，scan 会先问你要不要重扫（回答 `rescan`）；`upstream_repos` 可以加上要跟进的其他仓库，比如 vLLM。要接手一个任务，并在复现之后停下来确认环境，就给出它的字段：

```
use /workspace/Petra/petra.js with mode=issue, task=https://github.com/sgl-project/sglang/issues/41299,
petra_dir=/workspace/Petra, model_path=<weights>, gpu_ids=0, stop_after=Reproduce
```

或者直接用一句话描述，让 Intake 阶段写出任务定义：

```
use /workspace/Petra/petra.js with petra_dir=/workspace/Petra, request="DeepSeek-V4.1 在 MI355X 上
decode 太慢，帮我优化"
```

如果缺了什么（这里缺的是每次测量都用的固定负载），这次运行什么都不启动，返回 `status: needs_input`，每个字段一个问题。在对话里回答后，Claude Code 会用同样的参数加上 `answers={"workload": ...}` 再次运行 `petra.js`。[运行](#运行)一节列出了全部参数。

### 5. 运行结束后（容器内）

每次过了 Setup 的运行，都在 `/workspace/Petra/exp`（git 会忽略它）里有自己的目录，名字是 `<mode>_<slug>_<time>`：模式、任务的简短名字和 UTC 开始时间，例如 `issue_41299-glm-dcp_20261106-071502Z` 或 `scan_20261106-064327Z`。`exp/index.md` 列出这个容器里的每次运行和它的结局。一个运行目录里有：

| 文件 | 内容 |
|---|---|
| `run.json` | 任务定义、intake 的假设，以及所在的容器（任务的分支在那个容器里） |
| `validation_report.md`、`run_report.md` | 报告：PR 准备好时是前者，其他结局是后者（运行结果中的 `report_path` 给出路径） |
| `experiment_ledger.md` | 环境、基线和每一次测量 |
| `logs/` | 每次启动服务或 benchmark 一个日志，`<tag>_<time>.log` |
| `pr_body.md`、`patches/` | PR 描述，以及导成 patch 的分支 commit |
| `knowledge_pr.md` | curator 向 Petra 仓库提的 PR 的描述 |
| `task_queue.md`、`daily_report.md` | scan 排好序的任务，每项附可以启动它的任务定义；旁边是各个来源找到的内容（`<source>.json`）。后者是发布出去的日报，不含本机信息 |

Petra 从不 push。任务的分支 `petra/<slug>` 在 `/sgl-workspace/sglang` 里，报告给出确切的 `git -C /sgl-workspace/sglang push ...`：可以在容器里用有 push 权限的凭据执行它。运行目录随容器保留和删除；要保留某次运行，或者要在宿主机上 push（你的 git 凭据在那里），就把它复制到你宿主机上的 home（`<run>` 是运行目录的名字）：

```bash
cp -r /workspace/Petra/exp/<run> "$PETRA_HOST_HOME"/ && /workspace/Petra/scripts/restore_owner.sh "$PETRA_HOST_HOME"/<run>
```

复制出来的文件属于你而不是 root。在宿主机上你的 sglang checkout 里，先用报告给出的基础 commit 执行 `git checkout -b petra/<slug> <base>`，再执行 `git am ~/<run>/patches/*.patch`，然后 push。

### 重复执行与选项

`petra.bootstrap` 的每一步都会报告 `kept`、`installed`、`updated`、`added`、`created`、`skipped` 或 `failed`；最后有一份汇总，"下一步"只列出仍然缺少的内容，任何一步失败时退出码为 1。在新容器里，它几秒钟就能重建链接以及 git、shell 和 Claude Code 状态的设置，什么都不用安装。`--claude-only` 只运行 Claude Code 相关的步骤，`--check` 只运行检查。在容器里，`cd /workspace && pip install -v git+https://github.com/At1a8/Petra` 会按 GEAK 的方式执行第 3 步，把 Petra 克隆到 `/workspace/Petra`（加 `-v` 时 pip 才显示输出；用了缓存的 wheel 时会跳过）。

| 变量 | 使用者 | 默认值 |
|---|---|---|
| `IMAGE` | `scripts/run_docker.sh` | `IMAGE_VARIANT` 下最新的每日 `rocm/sgl-dev` 镜像（访问不了 Docker Hub 时用本地最新的） |
| `IMAGE_VARIANT`、`NAME`、`EXTRA_MOUNTS` | `scripts/run_docker.sh` | `rocm10-mi35x`；你的用户名；额外要挂载的目录，用空格分隔 |
| `DOCKER_SOCKET` | `scripts/run_docker.sh` | 不设置；设为 `1` 时额外挂载宿主机的 Docker socket 和 `docker` |
| `PETRA_LOCK_FILE` | `scripts/run_lock.py` | `/dev/shm/petra-run.lock`，这台机器"一个任务"的锁 |
| `PETRA_HOME` | bootstrap | `./Petra`，或你所在的 checkout |
| `PETRA_HOST_HOME` | `scripts/run_docker.sh`、bootstrap | 你在宿主机上的 home（`$HOME`），容器从这里找到你的 Claude Code、它的状态和 `~/.petra_env` |
| `PETRA_REPO_URL`、`PETRA_REF` | bootstrap | `https://github.com/At1a8/Petra.git`，它的默认分支 |
| `CLAUDE_VERSION`、`CLAUDE_BIN_DIR` | bootstrap | `latest`，`~/.local/bin` |
| `CLAUDE_CONFIG_DIR` | bootstrap、Claude Code | 容器里的 root 用你宿主机上的 `~/.petra/claude`；已经设置时原样使用 |
| `PETRA_REPO_TOKEN` | `~/.petra_env`、`scripts/post_queue.py`、`scripts/propose_knowledge.py` | 不设置；只对 Petra 自己仓库有 Issues、Contents、Pull requests 读写权限的 fine-grained token，scan 用它发布当天的日报，curator 用它提 PR |
| `LLM_GATEWAY_KEY` | `~/.petra_env`、容器的 shell 配置 | 不设置；设置后 Claude Code 走 AMD LLM 网关，除非 `ANTHROPIC_BASE_URL` 指定了别的地址 |
| `PETRA_FRAMEWORK_DIR`、`PETRA_FRAMEWORK_REPO` | bootstrap：`--framework-dir`、`--framework-repo` | 镜像里的 `/sgl-workspace/sglang`；sglang |
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
| `framework_dir` | 每个任务在其中工作的框架 checkout，任务从当前的 main 开自己的分支（sglang 默认用镜像里的 `/sgl-workspace/sglang`，镜像就是从这里安装 sglang 的） |
| `model_path` | 基线和各项门禁运行的模型（`feature` 和 `perf` 必填） |
| `framework`、`platform`、`gpu_ids` | 目标与环境（`sglang`；`gpu_ids` 为空时由 Setup 挑选空闲的 GPU，之后每个角色都通过 `HIP_VISIBLE_DEVICES` 使用这组 GPU） |
| `workload` | 每次测量都使用的基准负载，例如 `{"isl":8192,"osl":1024,"conc":64}`；`perf` 必填，在 Setup 时固定 |
| `container` | 只在 Petra 运行在宿主机上时使用：框架所在的容器，通过 `docker exec` 访问 |
| `exp_root` | 运行目录放在哪里（默认 `<petra_dir>/exp`，git 会忽略它） |
| `kernel_backend` | `none`（默认）\| `geak` \| `command`：kernel hand-off 交给谁 |
| `kernel_backend_dir` | `geak` 后端：提供 `kernel_workflow/kernel_lane.js` 的 GEAK checkout |
| `kernel_backend_command` | `command` 后端：带 `{task_dir}`、`{out_dir}`、`{gpu_ids}` 占位符的 shell 命令 |
| `kernel_budget` | kernel 后端的优化轮数（默认 6） |
| `apply_prs` | `perf`：要应用并做 A/B 的候选 PR |
| `sources`、`since` | `scan`：`ci`、`issues`、`upstream`（默认）以及 `hardware`、`perf` 中的任意几个；时间窗口的起点（默认为上一份日报） |
| `rescan`、`upstream_repos` | `scan`：为 `true` 时，即使已有 24 小时内的日报也重新扫描；要跟进的其他上游仓库，写成 `[{"name": "vllm", "url": "https://github.com/vllm-project/vllm"}]` |
| `stop_after` | 在该模式的指定阶段之后停下（例如 `Design`、`Reproduce`）；填了该模式没有的阶段，会作为问题返回 |
| `resume_from`、`run_dir` | `feature`：人审阅通过 `design.md` 后，用 `implement` 继续一个停在 Design 的运行 |
| `review_model` | reviewer 使用的模型，随它的 agent 调用一起传入（GEAK 运行时支持按调用指定模型；其他运行时视其能力而定） |
| `max_fix_rounds`、`max_investigate_rounds`、`max_review_rounds`、`max_work_packages` | 预算 |
| `agent_retries`、`agent_timeout_ms` | agent 调用出错时会重试（重试前先检查失败的那次留下了什么），超时则不重试：超时的 agent 可能还在运行，会被记入报告里的待人工处理清单。默认超时 3 小时，verify engineer、performance engineer 和 investigator 为 6 小时 |

除 `petra_dir`、`request`、`answers`、`exp_root`、`review_model` 和各项预算外，其余参数都属于任务定义；每次已启动的运行，其结果都会记录所用的任务定义（`task_def`）、每个字段的来源（`provenance`）以及 intake 的假设（`assumptions`）。

人工检查点：Intake 的提问（`needs_input`）；任何 `stop_after`；L3 任务和 architect 标记的设计会停在 Design（`awaiting_design_review`）；被 reviewer 标为 `blocked` 的审阅会在 PR 之前停下；PR engineer 只返回确切的 `git push` 而不执行；issue 回复是运行目录里的草稿。只要建好了运行目录，无论结局如何，运行都会以一份报告结束；停在 Intake（提问或拒绝），或在 Setup 建目录之前就结束的运行（`busy`），只返回运行结果。

**一台机器一个任务。** 运行在创建任何东西之前先占住这台机器：锁放在 `/dev/shm`，所有用 `--ipc=host` 启动的容器都和宿主机共用它，其他机器看不到；运行在写完报告后释放。另一个任务占着机器时，新的运行会立即以 `busy` 结束，并说明是谁占着。如果持有锁的运行已经结束，或者在两倍于最长 agent 调用的时间里（默认 12 小时）没往运行目录写过任何东西，下一个运行会直接接管。另一个容器里的运行不会因为没动静而被接管，因为这里看不到它的运行目录；确认那次运行已经不在之后，用第二条命令释放机器，和释放意外中断的运行留下的锁一样：

```bash
python3 scripts/run_lock.py status            # 谁占着这台机器
python3 scripts/run_lock.py release --force   # 那个运行已经中断时，强制释放
```

框架自带的 skill（sglang 的 `.agents/skills/`）以引用方式使用，从不复制：每个角色从任务 worktree 中读取 [`knowledge/frameworks/sglang/skills.md`](knowledge/frameworks/sglang/skills.md) 为它列出的 skill，因此与它正在修改的代码版本一致；ROCm 上的差异见 [`knowledge/platforms/rocm_skills.md`](knowledge/platforms/rocm_skills.md)。

## 脚本

全部是只用标准库的 Python；访问 GitHub 的脚本读取 `GITHUB_TOKEN` 或 `GH_TOKEN`（见第 1 步；没有 token 时，GitHub 对每个 IP 每小时只允许 60 次请求、每分钟 10 次搜索）。

| 脚本 | 任务来源 |
|---|---|
| `scripts/scan_issues.py` | 开放的 AMD issue，附关联 PR、回复情况和预计的 60 天自动关闭日期 |
| `scripts/scan_ci.py` | 从 main 上 AMD CI 自己的运行和日志读出现状（每个失败 job：从何时开始失败、上次通过的时间、失败的测试、第一条错误），以及 Failure Tracker 的失败簇 |
| `scripts/scan_upstream.py` | 已合入的上游提交：新增的 CUDA 门控、CUDA 优先的特性、新模型 |
| `scripts/audit_platform_gates.py` | 换到新架构时需要重新检查的平台门控（在 gfx1250 上为真的能力判断、wave32 假设） |
| `scripts/audit_host_syncs.py` | 热路径上的 host-device 同步和拷贝候选点（供 profile 参考的线索） |

`scripts/restore_owner.sh`（POSIX sh）把 root 在容器里写到宿主机挂载目录中的文件还给属主（`/workspace` 里的不用还）；每个 agent 在 git 写操作之后都会运行它（[`knowledge/env_hygiene.md`](knowledge/env_hygiene.md)）。`scripts/check_framework_skills.py --framework-dir <dir>` 拿 skill 索引和框架 checkout 对照：索引里提到但已经不存在的 skill，以及索引还没收录的新 skill（scout 每次 scan 都会运行它）。`scripts/latest_image.py [--variant rocm10-mi30x]` 输出最新的每日 sglang 镜像（`run_docker.sh` 从它启动；director 拿运行所用的镜像和它比较）。`scripts/run_lock.py` 保证一台机器同时只跑一个 Petra 任务（`acquire`、`release`、`status`）。`scripts/post_queue.py` 把 scan 的日报发成 Petra 自己仓库里当天的 issue，正文里提到本机或本地路径时拒绝发布；`--latest` 输出最新的一个，下一次 scan 从它接着扫。`scripts/propose_knowledge.py` 把 curator 在 `knowledge/` 下的改动，放在一个临时 worktree 里基于当前的 main 做成从 `petra/knowledge/<run>` 到 main 的 PR，然后把 checkout 里的 `knowledge/` 恢复原样，这样之后的运行只会读到合并过的知识。

## 测试

```bash
GEAK_HOME=/path/to/GEAK node tests/dry_run.mjs   # 在 GEAK 运行时上走遍 petra.js 的每条控制路径，不需要 GPU
python3 -m unittest discover -s tests             # 脚本的解析与规则、bootstrap、Claude Code 对 workflow 的规则、两份 README 的一致性；离线运行
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
├── scripts/                 # 任务收集、审计、run_docker.sh、latest_image.py、run_lock.py、
│                            # restore_owner.sh
├── petra/bootstrap.py       # 第 3 步的配置脚本，在容器内运行；可以重复执行
├── setup.py, pyproject.toml # 打包；pip 构建 wheel 时 setup.py 会运行 bootstrap
├── tests/                   # petra.js 的 dry run，脚本、bootstrap、Claude Code workflow 规则和 README 的单元测试
├── README.md, README.zh-CN.md
└── docs/design.md
```

## 与 GEAK 和 Hyperloom 的关系

- kernel 的速度是 kernel 工作流的事，无论选的是哪个后端（GEAK 的 kernel lane 是其中之一）：Petra 写出带单元测试的功能性 kernel，把算子规格连同作为判定标准的参考实现一起移交，再集成验证过的收益。
- 针对某个负载搜索 flag 和 backend 属于 Hyperloom 和 GEAK `e2e_workflow` 的工作；它们发现的上游候选是 Petra 的输入，Petra 落地的特性又成为它们的可选项。

## 来源

方法论、验证准则、已知问题登记表、模板和 HiSparse V2 特性 skill 来自 GEAK 的 `framework_workflow`（分支 `fangyuan/framework_agent_init`，commit `fc857c9`），当时它处在以知识库为主的阶段。Petra 在此基础上补上了当时计划中的编排、各个角色、设计中的 issue / CI / 性能 / scan 入口，以及任务收集脚本。

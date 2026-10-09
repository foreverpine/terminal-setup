# CLAUDE.md

给「在新机器上做终端配置」的 Claude Code 看。人类向说明见 `README_CN.md`。

## 这是什么

个人终端 dotfiles 仓库。本仓库是 [lewislulu/terminal-setup](https://github.com/lewislulu/terminal-setup) 的 fork / 个人定制版——原始项目是多平台开源终端配置，本仓库针对个人环境（Ubuntu 24.04 + zsh）定制，并改造成下面的「**版本化模板 + 本地覆盖**」架构。

- `configs/.zshrc`（入仓库）= 通用、跨平台的 zsh 模板
- `~/.zshrc.env`（**不入仓库**）= 代理、PATH、工具初始化所需环境变量，工具初始化前加载
- `~/.zshrc.local`（**不入仓库**，可能含账号等敏感信息）= 函数、别名、widget 等机器/个人覆盖
- `sync.sh` 统一部署 `.zshrc` 和 Starship；模板自行判断平台，不再由安装脚本 sed 修改。`~/.zshrc.local` 在 `zsh-syntax-highlighting` **之前**加载。

## 新机器配置流程

用户要复现当前服务器的基础使用环境时，优先从 `foreverpine/terminal-setup` clone 后运行 `./install.sh`。
`configs/server/` 保存实际使用的不含密钥的配置，`vendor/ccm/` 保存 ccm 本体和语言文件，
`scripts/bin/` 提供不依赖用户名的启动器。新机器不需要私有迁移包也能配齐工具和 ccm/ccc。
应用配置仅首次部署；已有账号、API 配置保留。共享 Shell 函数部署到 `.config/terminal-setup/ccm.zsh`。
API 密钥、私有网关和网关模型覆盖、登录态和项目授权不发布。
`./migrate.sh export ./snapshots/<name>` 仅作为可选的私有设置迁移入口。
工具版本清单在 `configs/server-baseline.json`，导出时更新为可读的本机版本。
`snapshots/` 含私有配置且被 Git 忽略，不提交、不打印其内容。登录态、私钥、项目数据不导出。
`migrate.sh apply` 校验所有文件后备份并替换配置，支持 `--dry-run` 和 `--config-only --target <临时目录>`。
安装快照使用内部 `setup.sh --server --keep-config`，防止模板覆盖迁移后的路径与 Git 设置。

GitHub 安装流程：

1. `git clone git@github.com:foreverpine/terminal-setup.git && cd terminal-setup`
2. Ubuntu/Debian/WSL：`./install.sh`（需 sudo；自动安装完整服务器基线及共享配置，跳过桌面和字体）。macOS：`./setup.sh --zsh`。
3. `sync.sh` 自动创建注释版 `~/.zshrc.env` / `~/.zshrc.local`，已有文件不覆盖。可用 `--local-dir <目录>` 导入预先准备的目标服务器配置（至少包含其中一个文件）；已有内容不同时停止，需手动合并。支持与 `--install`、`--pull`、`--dry-run` 组合。基本终端无需填写即可使用。
4. `exec zsh`

后续：修改 `configs/` 内模板；Git 提交推送后，新服务器 `./sync.sh --pull`，或复制仓库后 `./sync.sh`。
配置同步不需要 sudo。`--pull` 只允许干净工作树和 fast-forward；会重新执行更新后的脚本。
`--dry-run` 预览，`--restore <备份目录>` 恢复，`--target <目录>` 隔离验证。
备份位于 `~/.local/state/terminal-setup/backups/`。恢复不回退软件安装、Git 配置、登录 shell，且不删除首次安装的新文件。

## 硬约束（配置时不要违反）

Docker 是独立入口 `./docker-setup.sh --gpu`，规范和来源记录见 `DOCKER_SETUP.md`。
模板位于 `configs/docker.json`；主逻辑为 `scripts/docker_setup.py`，测试使用同一 unittest 入口。
只合并加速设置、按需加入 NVIDIA runtime，保留目标机器其他 daemon 配置。
不复制容器/镜像/凭据/驱动；发现运行中容器时默认停止，显式 `--restart` 才允许继续。
本机验证用 `--dry-run` 或 `--configure-only --root <临时目录>`，不要为测试重启当前服务器的 Docker。

1. **`zsh-syntax-highlighting` 必须最后加载**（PR #12 的 invariant）。它位于 `source ~/.zshrc.local` 之后，会包含本机覆盖中定义的 ZLE widget，无需重复加载。
2. **敏感及机器特定内容只进 `~/.zshrc.env` / `~/.zshrc.local`**，绝不进 `configs/.zshrc`。代理、私有域名、账号相关 PATH 放 `.env`；私有覆盖放 `.local`。可共享的 ccm/ccc 函数在 `configs/server/ccm.zsh` 版本化，路径使用 `$HOME`。
3. **要持久改 `~/.zshrc`，改模板 `configs/.zshrc` 再跑 `./sync.sh`**。直接改部署文件会在下次同步时被备份、覆盖。
4. **永不自动覆盖已存在的 `~/.zshrc.env` / `~/.zshrc.local`，包括软链接**；不存在时以权限 600 导入指定文件或 seed 注释示例。`--restore` 不改动这两个文件。
5. 用户级 PATH 必须在 Starship/zoxide 初始化前加载；保持 fzf 的旧版 Debian/Ubuntu 集成脚本回退。

## 机器配置入口（真实值不进仓库）

参考 `configs/.zshrc.env.example` / `configs/.zshrc.local.example`。旧 `.local` 保持兼容，需要提前生效的导出应移到 `.env`，避免两处值冲突。通常含：
- **代理（`.env`）**：`http_proxy`/`https_proxy`/`no_proxy`。端口与方案随机器，`127.0.0.1` 指目标服务器自身，不能默认复用旧机器的本地代理。
- **ccm/ccc 函数**：依赖 `~/.local/share/ccm/ccm.sh`；Git 仓库已携带脚本及语言文件，`./install.sh` 自动部署。API 密钥在本机填写或通过环境变量提供。
- **额外 PATH（`.env`）**：如 `~/.npm-global/bin`、`~/.opencode/bin`。

这些是可选功能，基础同步不依赖它们。迁移已知的本机覆盖时先核对代理及硬编码路径，不把真实值写进通用模板。

## 机器特定项（换机器要核对）

- **用户名**：仓库内的启动器使用 `$HOME`；私有快照里的旧绝对路径在迁移时改为目标 HOME。
- **代理**：端口/方案随机器和网络环境变。
- **WSL**：WSL2 + mirrored 网络 + Windows 代理（Clash 等）有额外坑——`sudo` 无 TTY、apt 因 fake-ip 需配 `/etc/apt/apt.conf.d/95proxy`、setup.sh 历史 bug 等，详见 [`WSL_DEPLOY_NOTES.md`](WSL_DEPLOY_NOTES.md)。

## `setup.sh` 速查

- `--server` 是 `sync.sh --install` 的实现入口，仅支持 Debian/Ubuntu/WSL 的 Zsh，无可选软件交互（sudo 可能要求密码）。
- `--zsh` / `--fish` 保留原桌面安装入口。服务器路径的 `--dry-run` 已验证无文件写入及下载；旧 Fish 路径未做此保证。
- **服务器自动装**：原终端工具和插件、Git/curl/wget/rsync/zip/unzip/构建工具/tmux、Python/pip/venv、fnm/Node/pnpm、uv/uvx、Miniconda、Zellij、Claude Code/Codex/OpenCode/dsh/agently-cli。用户工具已有则保留，缺失则按版本清单安装；最终缺工具必须失败。
- **服务器不装**：Ghostty、字体、项目环境和数据。ccm/ccc 使用仓库随附的本机版本，不从猜测的来源下载。原桌面流程保留。
- `scripts/server_runtime.py --check` 检查基线命令是否齐全；快照清单会额外要求 ccm/ccc。安装时若已有 Node 主版本过旧，仍需通过 fnm 补齐基线版本。工具版本不等于项目环境锁定，Conda 初始化不自动激活 base。
- 验证：`bash -n setup.sh sync.sh`、`zsh -n configs/.zshrc`、`python3 -m unittest discover -s tests -v`。

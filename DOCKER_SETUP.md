# Docker / NVIDIA GPU 服务器配置

目标：另一台 Ubuntu/Debian 服务器取得此仓库后，用一条命令安装 Docker、Compose、Buildx 和 NVIDIA Container Toolkit，并复用软件源及镜像加速设置。镜像、容器和数据卷不参与迁移。

## 新服务器

先安装适合新机器的 NVIDIA 驱动，确保 `nvidia-smi` 正常显示 GPU。驱动与显卡、内核有关，不从旧机器复制，也不由此脚本安装。

```bash
git clone git@github.com:liyongso22/terminal-setup.git ~/terminal-setup
cd ~/terminal-setup
nvidia-smi
./docker-setup.sh --gpu --dry-run
./docker-setup.sh --gpu
```

若已有仓库，先 `git pull --ff-only`。需要 Python 3、sudo 和 systemd；WSL 需要先启用 systemd。正常安装可能询问 sudo 密码。普通 CPU 服务器去掉 `--gpu`。

脚本会：

1. 检查现有配置、正在运行的容器及 GPU 驱动；发现发行版自带 `docker.io` 等冲突包时停止并列出包名，不自动卸载。
2. 根据目标机的发行版代号和 CPU 架构配置带签名验证的 Docker apt 仓库；GPU 模式另外配置 NVIDIA 官方 stable 仓库。
3. 安装缺失的 Docker CE、CLI、containerd.io、Compose、Buildx，以及 GPU 模式需要的四个 Toolkit 软件包。已安装的包不主动升级；新机器安装所配置源提供的稳定版本，不保证与旧机器版本号相同。
4. 合并 `registry-mirrors`，保留既有数据目录、代理、网络和其他运行时设置；GPU 模式使用 `nvidia-ctk` 加入 NVIDIA runtime。
5. 使用 `dockerd --validate` 检查候选配置，备份后写入；启动 Docker，配置有变化时重启，并验证运行时和两个 CLI 插件。

正常 `sync.sh` 只同步终端配置，不会触发 Docker 安装或重启。

## 配置放在哪里

公共模板：`configs/docker.json`。

```json
{
  "docker-apt-base": "https://mirrors.tuna.tsinghua.edu.cn/docker-ce/linux",
  "registry-mirrors": ["https://docker.1panel.live"]
}
```

两种“源”的用途不同：

| 配置 | 用途 |
|---|---|
| Docker apt 软件源 | 下载 Docker 程序、Compose、Buildx 等安装包 |
| `registry-mirrors` | Docker Hub 镜像拉取加速，不是 apt 源，也不自动加速所有其他镜像仓库 |
| NVIDIA apt 软件源 | 下载 NVIDIA Container Toolkit，不是 GPU 驱动或 CUDA 镜像 |

机器专属覆盖可以另存为已忽略的 `configs/docker.local.json`，通过 `--config` 显式选择。该文件是完整的两字段配置，不是补丁：

```bash
cp configs/docker.json configs/docker.local.json
# 编辑配置后：
./docker-setup.sh --gpu --config configs/docker.local.json
```

若目标网络能直连 Docker 官方源，可将 `docker-apt-base` 改为 `https://download.docker.com/linux`。不需要镜像加速时将 `registry-mirrors` 设为 `[]`。模板仅接受无账号、密码和查询参数的 HTTPS 地址。Docker 登录凭据 `~/.docker/config.json` 不进入仓库。

## 后续仅更新加速配置

```bash
cd ~/terminal-setup
git pull --ff-only
./docker-setup.sh --gpu --configure-only
```

此模式不修改 apt 源、不安装包，要求 Docker 和 NVIDIA Toolkit 已安装。无变化时不重写 `daemon.json`，也不重启已运行的 Docker。

如果 Docker 正在运行容器，默认先停止操作；安排好停机窗口后才使用：

```bash
./docker-setup.sh --gpu --configure-only --restart
```

`--restart` 表示允许这次操作影响正在运行的容器；新服务器通常不需要。安装包也可能重启服务，因此安装路径同样执行此检查。

## 备份与恢复

变更前保存的文件放在 `/var/backups/terminal-setup/docker/<时间及随机后缀>/`，目录权限为 700，脚本输出具体路径。包括被替换的 `daemon.json` 和 apt 源文件。没有修改的文件不产生备份。

Docker 因新配置启动失败时，脚本恢复本次运行前的 `daemon.json` 并尝试再次启动；软件安装和 apt 源不会因此回退。需要手动恢复配置时，在合适的停机窗口执行：

```bash
sudo cp -p /var/backups/terminal-setup/docker/<备份目录>/daemon.json /etc/docker/daemon.json
sudo dockerd --validate --config-file=/etc/docker/daemon.json
sudo systemctl restart docker
```

安装器不会删除现有数据、改 Docker 数据目录、安装 GPU 驱动、复制 registry 登录凭据或自动把用户加入 `docker` 组。使用 `sudo docker ...` 即可操作。

## 验证（默认不拉取镜像）

```bash
nvidia-smi
sudo docker info
sudo docker compose version
sudo docker buildx version
```

`docker info` 的 Runtimes 中应包含 `nvidia`。这确认了运行时注册；实际 GPU 容器计算还需要运行工作负载验证。若已有包含 `nvidia-smi` 的 CUDA 镜像，可以使用它测试，`--pull=never` 防止下载：

```bash
sudo docker run --rm --pull=never --gpus all <已有CUDA镜像名> nvidia-smi
```

## ubuntu22 配置记录与源检查

2026-09-29 从本机文件读取：Docker CE 29.2.1，Ubuntu 24.04 noble，amd64；原 Docker apt 源为 `https://download.docker.com/linux/ubuntu`，NVIDIA 源为 `https://nvidia.github.io/libnvidia-container/stable/deb/amd64`，daemon 配置包含 NVIDIA runtime。

原镜像加速列表及当时在 ubuntu22 上的无代理检查结果：

| 原地址 | 检查结果 |
|---|---|
| `https://mirror.ccs.tencentyun.com` | 未能解析；腾讯官方说明该服务仅限腾讯云内网 |
| `https://docker.pullery.cn` | 未能解析 |
| `https://dockerpull.com` | HTTPS 连接超时 |
| `https://docker.1panel.live` | `/v2/` 返回 200、JSON `{}` 和 `Docker-Distribution-Api-Version: registry/2.0` |

同一网络下 Docker 官方 apt 域名发生连接重置；清华 Docker 仓库的公钥端点、NVIDIA 官方公钥端点可访问。因此模板选择清华 apt 镜像和已响应的 1Panel 加速地址。保留以上记录便于调整，不将旧地址全部默认启用。

这些结果只是当时该服务器的连通性快照；没有拉取镜像验证，不能保证目标网络可用、所有镜像有缓存或第三方服务持续可用。镜像加速由相应第三方运营；软件包通过 apt 的签名机制验证。

## 开发验证与官方依据

```bash
python3 -m unittest discover -s tests -v
bash -n docker-setup.sh
./docker-setup.sh --gpu --dry-run
```

`--configure-only --root /tmp/docker-preview` 可在独立目录验证文件合并，不运行 apt、sudo 或 systemctl；加 `--gpu` 时需要本机已安装 `nvidia-ctk`，只修改临时目录内的候选配置。

- [Docker Ubuntu 安装文档](https://docs.docker.com/engine/install/ubuntu/)
- [清华 Docker CE 软件源说明](https://mirrors.tuna.tsinghua.edu.cn/help/docker-ce/)
- [NVIDIA Container Toolkit 安装及 Docker 配置](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)
- [Docker Hub mirror 配置](https://docs.docker.com/docker-hub/image-library/mirror/)
- [腾讯镜像服务的内网限制](https://cloud.tencent.com/document/product/213/8623)

# Transdub

[English](README.md) · **简体中文**

> 一条龙把外语视频翻译并配音成中文——本地优先。

看到一个很棒的视频，想分享给不懂外语的朋友？Transdub 只用一条命令，就能把外语
（YouTube）视频变成可以直接分享的中文版本——既有精准的中英双语字幕，也有自然的
中文配音。它把整个流程串成一条链，省去你在各种工具之间来回折腾：

**下载 → 转写 → 翻译 → 合成 → 配音 → 发布**，一端可选接入频道监控，另一端记录
播放量/点赞等数据。完整规格见 `instruction.md`。

它**本地优先**，所以大部分环节都能在自己的机器上免费完成：翻译和发布文案优先用
本地 Ollama 模型，只有在需要时才回退到 Claude；缺失的字幕用本地 Whisper 转写；
中文配音可选 edge-tts、本地 Kokoro，或 GPT-SoVITS 声音克隆。每个后端都藏在一个
小协议之后，所以本地与云端引擎可以即插即换。

> [!IMPORTANT]
> **使用须知与你的责任。** Transdub 是面向**你有权使用的内容**的本地化工具——你
> 自己的视频，或是**经创作者授权**的他人视频。从 YouTube 下载可能违反其服务条款，
> 未经授权转载他人作品即使标注来源也构成侵权。项目内置了授权征询的工作流正是为此：
> **请先征得同意。** 你需要自行确保对所处理和发布的一切内容拥有合法权利，并遵守你
> 所使用的每个平台与模型的条款。本软件按“原样”提供，作者不对其使用方式承担任何责任
> （见 `LICENSE`）。

## 前置依赖

- **[uv](https://docs.astral.sh/uv/)** —— Python 3.13+ 的环境与运行器
- **ffmpeg** —— 音视频处理（所有媒体环节都用到）
- **[deno](https://deno.com/)** —— 下载时求解 YouTube 的 JS 挑战
- *可选：* **[Ollama](https://ollama.com)**（本地翻译/文案）、本地 **GPT-SoVITS**
  服务（声音克隆）、以及 **Anthropic API Key**（云端回退）。每一项都是可选的，缺失
  时会优雅降级。

## 安装

```bash
uv sync                          # 核心依赖
uv sync --extra asr              # + Whisper（faster-whisper）字幕回退
uv sync --extra dub              # + edge-tts 中文配音
uv sync --extra dub-kokoro       # + 本地离线 Kokoro 语音（可选）
cp .env.example .env             # 填入所需配置（见下）
```

除核心安装外一切皆可选，并且会优雅降级——缺少某个 extra 只会跳过对应环节并给出警告。

### 本地模型（可选，但推荐）

翻译与发布文案在本地 [Ollama](https://ollama.com) 服务可用时优先使用本地模型，
否则改用 Claude。

```bash
ollama serve                     # 启动本地服务
ollama pull qwen3.5:9b           # 一个中文能力好的模型（推荐 qwen）
export OLLAMA_MODEL=qwen3.5:9b   # 否则自动挑选 qwen/yi/glm/… 中的模型
```

也可用：`llama3.1:8b`，或通过
`ollama pull hf.co/mradermacher/Hunyuan-MT-7B-GGUF:Q4_K_M` 拉取 Hunyuan-MT。
发布文案通常以 qwen 效果最佳。

### 环境变量（`.env`）

| 变量 | 用途 |
|-----|------|
| `ANTHROPIC_API_KEY` | Claude（翻译/发布回退，或 Ollama 关闭时的主力） |
| `YOUTUBE_API_KEY`、`SMTP_*` | 频道监控 + 邮件摘要 |
| `OLLAMA_MODEL`、`OLLAMA_HOST` | 本地翻译/发布模型 + 服务地址 |
| `WHISPER_MODEL` | Whisper 转写模型（默认 `small`） |
| `DUB_ENGINE`、`DUB_VOICE`、`DUB_WORKERS` | 配音引擎 / 音色 / 并发 |
| `KOKORO_MODEL`、`KOKORO_VOICES`、`KOKORO_VOICE` | 本地 Kokoro 模型文件/音色 |

## 完整流程（一条链，带重试）

```bash
uv run transdub-run "https://www.youtube.com/watch?v=VIDEO_ID"
```

端到端跑完每个环节——**下载 →（无字幕则转写）→ 翻译 → 合成 → 配音 → 发布 →
记录指标**——每步在遇到瞬时失败时都会重试。最后会打印成品元数据，以及一份按环节
区分的**本地 vs 云端引擎汇总**：

```
engines (local vs cloud):
    download:   yt-dlp
    subtitle:   local · whisper:small        (或 "YouTube captions")
    translate:  local · ollama:qwen3.5:9b (3/3 chunks)
    dub:        online · edge-tts:zh-CN-XiaoxiaoNeural
    publish:    local · ollama:qwen3.5:9b
```

常用参数：

- `--no-dub` 跳过中文配音（默认开启）
- `--voice zh-CN-YunxiNeural` 指定配音音色
- `--backend auto|ollama|claude` 翻译引擎（默认 `auto` = 本地优先 + Claude 回退；
  发布文案同理）
- `--stop-after translate` 停在人工校对字幕的关口（校对后再跑
  `transdub-compose` / `transdub-dub` / `transdub-publish`）
- `--stop-after compose` 在发布前停止
- `--no-publish` / `--no-data` 跳过对应环节
- `--attempts N` / `--retry-delay S` 调整重试策略
- `--schedule SECONDS`（+ 可选 `--max-runs N`）按间隔重复执行
- `-v` 详细（debug）日志

### 恢复中断的任务

没有单独的恢复命令——**直接用同一个 URL 再跑一次即可**。流程本身不保存检查点，但
每个环节都会把产物作为*同名兄弟文件*写在视频旁边并复用，所以重跑会跳过已完成的
工作，从中断处继续：

| 环节 | 重跑时复用的产物 |
|------|------------------|
| download | 已有的 `<video>.mp4`（yt-dlp 跳过重新下载，仅取 info JSON） |
| subtitle | 已有的 `<video>.en.srt`（Whisper 不会重新转写） |
| translate | 覆盖已有的 `<video>.bilingual.ass`（开销很小） |
| compose | `<video>.final.mp4` |
| dub | `<video>.final.dubbed.mp4` |

```bash
uv run transdub-run "https://www.youtube.com/watch?v=VIDEO_ID"   # 从中断处继续
```

任务最常停在**配音**环节。若默认的 GPT-SoVITS 引擎内存不足，可换用更轻的路径继续：

```bash
uv run transdub-run "…VIDEO…" --dub-engine edge     # 云端 edge-tts，不占本地内存
uv run transdub-run "…VIDEO…" --stop-after compose  # 先出带字幕的视频，配音稍后再做
```

一旦字幕已存在（下载得到或 Whisper 生成），你也可以用下面的单环节命令手动续跑——
但没有独立的转写命令，所以无字幕的视频需要先完整跑一次来生成 `<video>.en.srt`。

## 频道监控 + 通知

维护一份按分类分组的关注清单（`channels.json`，参见 `channels.example.json`），
扫描新视频和热门视频并发送邮件摘要。需要 `.env` 中的 `YOUTUBE_API_KEY` 与 `SMTP_*`。

```bash
uv run transdub-monitor --config channels.json            # 扫描 + 发邮件
uv run transdub-monitor --config channels.json --dry-run  # 扫描 + 仅打印
uv run transdub-run --monitor --schedule 3600             # 每小时扫描 + 发邮件
```

## 单独环节

每个环节也都是独立命令（跑一步、检查、再跑下一步）：

```bash
# 下载视频 + 字幕（+ info.json + 封面图）
uv run transdub-download "https://www.youtube.com/watch?v=VIDEO_ID"

# 翻译字幕 → 双语 ASS（英文 + 中文）。--backend auto|ollama|claude
uv run transdub-translate samples/demo.srt -o out/demo.bilingual.ass

# 合成：把双语字幕烧录进视频（--mode soft = MKV 字幕轨；
# --preview N = 全量编码前先快速检查 N 秒）
uv run transdub-compose video.mp4 video.bilingual.ass -o out/final.mp4

# 配音：以双语字幕为脚本，用中文音色替换音轨，
# 在带字幕版本旁另写一个 <video>.dubbed.mp4
uv run transdub-dub out/final.mp4 video.bilingual.ass
uv run transdub-dub --list-voices          # 列出中文音色 + 试听入口
uv run transdub-dub --samples ./samples-out # 每个音色合成一段用于试听

# 发布：中文标题/简介/标签 + 一张封面，输出到 output/<日期>/<频道>/
uv run transdub-publish out/final.mp4 -s video.bilingual.ass

# 数据：记录并对比“原片 vs 二次发布”的指标
uv run transdub-data record-source downloads
uv run transdub-data record-upload --source-id VIDEO_ID --platform bilibili --views 8200 --likes 430
uv run transdub-data show VIDEO_ID
```

## 字幕、翻译、配音的工作原理

- **字幕**：YouTube 越来越多地在没有 PO token 时不提供自动字幕。当没有字幕可下载
  时，音频会用本地 **Whisper**（`--extra asr`）转写成英文 SRT 再喂给翻译——所以
  没有字幕的视频依然能处理。能下载到的自动字幕是“滚动”格式（每条都重复上一行再加
  一行新内容），翻译前会先去滚动（`transdub-translate --no-clean` 可关闭）。
- **翻译**采用编号行文本协议（而非 JSON——对标点更稳健）。`auto` 模式按块调用本地
  Ollama 模型，对任何它搞砸的块回退到 Claude。
- **配音**先把**字幕碎片合并成完整句子**（双语字幕被切成约 2 秒、常常断在句子中间
  的阅读窗口，直接配音效果很差），再逐句合成，并按其时间窗口对齐（加速上限 2.0×）。
  对齐是以“距该字幕结束还剩多少时间”为准来测量的，所以某句超时后会被压缩以**吸收
  漂移**而非让其累积——即使是语速很快的讲者，语音也能牢牢贴住画面。随后替换音轨。
  默认（`auto`）在 GPT-SoVITS 服务可用时使用**频道音色克隆**（见下），否则用
  **edge-tts**（`zh-CN-Xiaoxiao`，并发合成以掩盖网络延迟）；本地 **Kokoro** 是离线
  选项（`DUB_ENGINE=kokoro`，需要 `--extra dub-kokoro` + Kokoro 模型文件）。可用
  `--dub-engine` / `$DUB_ENGINE` 显式指定。

### 声音克隆——用频道本人的声音配音（GPT-SoVITS）

GPT-SoVITS 会克隆**原创作者的声音**来做中文配音，并在其服务可用时作为**默认引擎**
（否则 `auto` 回退到 edge-tts）。系统会自动从源音频里剪出一段简短的参考片段（用
视频中段的一段字幕作为其文本），并按频道缓存到 `models/refs/<频道>.wav`，这样同一
频道的每个视频都用同一个克隆音色。

要使用**自定义音色**，把任意音/视频片段注册一次即可——它会抽取一段简短参考、用
Whisper 自动转写、并存到 `models/refs/`（需要 `--extra asr`）：

```bash
uv run transdub-dub --register "clip.mp4" [--name MyVoice]
uv run transdub-run "…VIDEO…" --voice MyVoice     # 按名字复用
```

或用 `--voice /path/clip.wav` 内联指定一段参考（同名的 `clip.txt` 提供其文本，
`clip.lang` 提供其语言）。

在 `transdub-run` 内部使用 GPT-SoVITS 时，会先卸载本地 Ollama 模型以释放内存，
再进行（更吃资源的）配音。

GPT-SoVITS 是较重的 PyTorch 程序，因此作为独立的本地服务运行（支持 Apple Silicon），
transdub 通过 HTTP 与之通信：

```bash
# 一次性：安装 GPT-SoVITS 并下载其预训练模型，然后：
python api_v2.py                      # 监听 127.0.0.1:9880（见 GPT-SoVITS 文档）

# 让 transdub 指向它并配音：
export DUB_ENGINE=gpt-sovits          # 或：--dub-engine gpt-sovits
export GPT_SOVITS_URL=http://127.0.0.1:9880   # 默认值
uv run transdub-run "https://www.youtube.com/watch?v=VIDEO_ID"
```

若服务未运行，配音环节会对该视频失败（非致命），并给出清晰的“服务不可达”提示。

下载真实的 YouTube 字幕需要浏览器 cookie（机器人校验）和一个 JS 运行时（如 `deno`，
用于求解挑战）；流程通过 `--cookies-from-browser` 和 `--remote-components ejs:npm`
自动处理这些。

**如果下载时报 `The page needs to be reloaded.`**（或类似的 `[youtube]` 抽取错误），
说明 yt-dlp 版本过旧——YouTube 会定期更改其播放器，只有较新的 yt-dlp 才能求解新的
挑战。更新后重试：

```bash
uv lock --upgrade-package yt-dlp && uv sync
```

（已下载的视频会从磁盘复用，所以重跑中断的任务不会再碰到这个问题——见上文
“恢复中断的任务”。）

## 测试

```bash
uv run pytest                    # 全部测试（无需网络/API/模型）
```

## 架构

按功能命名的包位于 `src/` 下（代码与 `downloads/`、`output/`、`models/` 等运行时
目录分离）；`tests/` 在仓库根目录。每个环节都是输入输出清晰的准纯函数，后端藏在
协议之后可随意替换，便于日后迁移到工作流框架。

- `download/` —— yt-dlp 封装 → 视频 + 字幕（+ info.json、封面图）
- `transcribe/` —— Whisper ASR 回退 → 缺字幕时生成英文 SRT
- `translate/` —— 字幕 → 双语 ASS；`TranslationBackend` 协议，含 Claude + Ollama
  实现与本地优先的 `FallbackBackend`
- `compose/` —— ffmpeg 把双语字幕烧录/软挂载进成品视频
- `dub/` —— 中文 TTS 音轨（`VoiceBackend`：edge-tts / Kokoro），对齐字幕时间轴后
  替换音频
- `publish/` —— 中文标题/简介/标签（`MetadataBackend`：Claude + Ollama，本地优先）
  + 封面帧
- `data/` —— 以 SQLite 保存“原片 vs 二次发布”的指标快照
- `monitor/` —— YouTube Data API 频道监控 + 新片/热门检测 + 邮件
- `obs/` —— 终端日志 + 单行进度
- `orchestrate/` —— 把各环节编排成一条流程（`flow.run_full`），带重试策略、定时
  调度与引擎汇总；也是日后接入工作流框架的接缝

## 参与贡献

欢迎提 issue 和 PR——见 `CONTRIBUTING.md`。测试无需网络、API Key 或模型：
`uv run pytest`。

## 许可证

[MIT](LICENSE)。请留意上文的**使用须知与你的责任**——许可证覆盖的是软件本身，而非
你所处理的任何视频的权利。

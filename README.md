# Autonomous Android Controller

[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python: 3.10+](https://img.shields.io/badge/Python-3.10%2B-brightgreen.svg)](https://www.python.org/)
[![Platform: Android 11+](https://img.shields.io/badge/Platform-Android_11%2B_%2F_OneUI-green.svg)](https://www.android.com/)
[![Architecture: Shizuku UID 2000](https://img.shields.io/badge/Privilege-Shizuku_UID_2000-orange.svg)](https://shizuku.rikka.app/)
[![Hardware: Samsung Galaxy M56](https://img.shields.io/badge/Target-Samsung_Galaxy_M56_(SM--M566B)-purple.svg)](https://www.samsung.com/)
[![Failover: 19-Key Multi-Provider](https://img.shields.io/badge/Failover-19--Key_Multi--Provider-red.svg)](#resilient-19-key-multi-provider-failover-architecture)

An autonomous, rootless on-device AI agent and perception engine for Android. Engineered to execute natively inside **Termux** via **Shizuku (`rish`, UID 2000)** or remotely from a host PC over **Wireless ADB**.

Powered by a closed-loop **Perception-Action-Verification (ReAct)** diagnostic engine, a **19-key resilient multi-provider failover vault**, and visual semantic UI grounding tailored for Samsung OneUI hardware.

---

## Executive Overview & Genesis Architecture

Traditional mobile automation frameworks suffer from severe platform constraints:
1. **Accessibility Scraper Flakiness:** Conventional agents rely on Android's `AccessibilityService` (`AccessibilityNodeInfo`). In practice, accessibility trees drop events during rapid UI transitions, lag behind frame updates, fail completely on modern declarative canvas rendering (Flutter, Jetpack Compose, WebViews, and game engines), and trigger aggressive Android 13+ "Restricted Settings" security roadblocks alongside 15–25% hourly battery drain.
2. **Sandboxed APK Isolation:** Running inside standard application sandboxes (`UID 10xxx`) isolates processes from system commands, blocks cross-package hierarchy inspection, and forces disruptive `MediaProjection` screen-recording prompts on every session launch.
3. **The Rootless Alternative (UID 2000):** The **Autonomous Android Controller** bypasses accessibility services and sandboxed APKs entirely by anchoring execution in **Android UID 2000 (`shell`)** via Shizuku. This grants programmatic access to system utilities (`uiautomator`, `cmd`, `input`, `settings`, `dumpsys`) through native Binder IPC without requiring kernel rooting, bootloader unlocking, or tripping SafetyNet / Play Integrity attestation.

---

## Core Features & Key Innovations

* **Rootless Privilege Escalation (UID 2000):** Leverages Shizuku (`/system/bin/rish`) over local TLS loopback (Android 11+) to execute privileged system commands with sub-5ms latency while keeping device integrity, warranty bits (`0x0`), and banking applications completely intact.
* **Closed-Loop ReAct Self-Verification & Healing:** Operates on an autonomous *Observe $\rightarrow$ Plan $\rightarrow$ Act $\rightarrow$ Settle (1.2s) $\rightarrow$ Verify $\rightarrow$ Self-Diagnose $\rightarrow$ Corrective Actuation* cycle. Before/after UI hierarchies, foreground activities, and hardware states are evaluated by an LLM diagnostician; unexpected soft keyboards or modal popups are autonomously dismissed with corrective actions.
* **19-Key Multi-Provider Failover Vault:** Eliminates rate limits (HTTP 429), quota depletion (HTTP 402), and model retirements via automated round-robin rotation and cross-tier cascading across 19 independent developer keys in 3 distinct tiers.
* **Samsung OneUI Hardware Control:** Specifically tuned for the **Samsung Galaxy M56 (`SM-M566B`)**, solving discrete 15-step audio stream quantization (`cmd media_session volume --stream 3 --set <idx>`), media session dual-dispatch (Play/Pause/Next/Prev), and screen brightness adjustments without floating UI overlay obstruction.
* **Visual Semantic Grounding (No Brittle Regex Tables):** Replaces hardcoded intent guessing with live UI accessibility tree dumps (`uiautomator dump`), dynamic package discovery (`pm list packages`), and geometric center touch calculation `[(x1 + x2) // 2, (y1 + y2) // 2]`.
* **Multilingual Natural Language Understanding:** Parses and executes natural language commands in English, Bengali (বাংলা), and Hindi (हिंदी).
* **Terminal HUD & Background Execution Stability:** Overrides the Android Phantom Process Killer to prevent background process termination and emits real-time progress updates directly to the Android notification drawer (`cmd notification post`) and persistent transcripts (`ai log`).

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       Natural Language User Instruction                     │
│                (CLI, Termux Terminal, or PC Remote Dispatch)                │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                 Resilient 19-Key Multi-Provider Router                      │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │ Tier 1: Primary Low-Latency Flash API Endpoints (7 Keys, 800-1200ms)  │  │
│  └───────────────────────────────────┬───────────────────────────────────┘  │
│                                      │ Failover on HTTP 429/402/5xx         │
│                                      ▼                                      │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │ Tier 2: Groq High-Speed Open-Source Inference (5 Keys, 250-450ms)     │  │
│  └───────────────────────────────────┬───────────────────────────────────┘  │
│                                      │ Failover on HTTP 429/402/5xx         │
│                                      ▼                                      │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │ Tier 3: OpenRouter Multi-Model Fallback Pool (7 Keys, 1700-4800ms)    │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    Autonomous Task Decomposition Engine                     │
│          (Hardware Control, Media, App Launch, UI Perception, Chat)         │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│               Rootless Privilege Execution Domain (UID 2000)                │
│       On-Device: Shizuku Binder IPC (`rish`)  |  Remote: ADB TCP 5555       │
└───────────────────┬─────────────────────────────────────┬───────────────────┘
                    │                                     │
                    ▼                                     ▼
┌──────────────────────────────────────┐ ┌────────────────────────────────────┐
│      Android Hardware Subsystem      │ │    Dynamic Visual UI Grounding     │
│  - OneUI Audio: Discrete Stream 3    │ │  - uiautomator window dump XML     │
│  - MediaSession Dual-Dispatch        │ │  - Element bounding box centers    │
│  - Settings Provider (Brightness)    │ │  - Touch injection: `input tap`    │
└───────────────────┬──────────────────┘ └────────────────┬───────────────────┘
                    │                                     │
                    └──────────────────┬──────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                 Perception-Action-Verification Closed Loop                  │
│       Observe State -> Actuate -> Settle (1.2s) -> Re-Dump State            │
│         -> Multi-Modal Diagnosis -> Autonomous Self-Correction              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Target Device Hardware Specifications

The controller is tested and tuned for the **Samsung Galaxy M56 (`SM-M566B`)**:

| Hardware Subsystem | Specification Details | Impact on Controller Architecture |
| :--- | :--- | :--- |
| **Model** | Samsung Galaxy M56 (`SM-M566B` / Dual-SIM) | Primary testing and deployment platform. |
| **SoC** | Samsung Exynos 1480 (4nm FinFET) | High single-thread CPU performance for XML hierarchy parsing. |
| **CPU Configuration** | 4x Cortex-A78 @ 2.75 GHz + 4x Cortex-A55 @ 2.0 GHz | Requires background battery optimization exemption. |
| **GPU** | AMD RDNA2-based Xclipse 530 GPU | Hardware-accelerated UI rendering and compositing. |
| **Display Panel** | 6.7" FHD+ Super AMOLED+ (1080 x 2340 pixels, 120Hz) | Total canvas bounds: `[0, 0]` to `[1080, 2340]`. |
| **Display Cutout / Inset** | Top status bar cutout: `[0, 0][1080, 97]` (Height: 97px) | Touch bounds clamped to $Y \ge 97$ to avoid notification shade. |
| **Navigation Inset** | Bottom navigation bar: `[0, 2210][1080, 2340]` (Height: 130px)| Touch bounds clamped to $Y \le 2210$ to avoid gesture bar. |
| **Usable Viewport** | Interactive content viewport: `[0, 97]` to `[1080, 2210]` | Active interactive viewport height: **2113 pixels**. |
| **RAM & Storage** | 8GB LPDDR5 RAM + 128GB/256GB UFS 3.1 | Ample memory for concurrent Termux Python daemons. |
| **OS & Skin** | Samsung OneUI 6.x / 7.0 on Android 14 (API 34) | Discrete 15-step volume scale (`STREAM_MUSIC` = 3). |

---

## Resilient 19-Key Multi-Provider Failover Architecture

Agentic ReAct loops require repeated, high-frequency LLM calls. Relying on a single API provider results in unavoidable rate limits. The controller utilizes a **19-key key vault structured across 3 tiers**:

| Provider Tier | Key Count & Vault Variables | Target Models | Latency Window | Role in Architecture |
| :--- | :--- | :--- | :--- | :--- |
| **Tier 1: Primary Flash Endpoints** | **7 Keys** (`PRIMARY_FLASH_KEY_1..7`) | `flash-lite-latest`, `flash-latest`, `flash-preview`, `2.5-flash` | 800ms – 1200ms | Complex multi-step task planning, JSON schema adherence, visual hierarchy evaluation, and ReAct self-diagnosis. |
| **Tier 2: Groq High-Speed Inference** | **5 Keys** (`GROQ_API_KEY_1..5`) | `qwen/qwen3.8-27b`, `openai/gpt-oss-120b`, `llama-3.3-70b-versatile` | 250ms – 450ms | Sub-300ms reflex intent routing, emergency hardware actuation, and rapid single-turn classifications. |
| **Tier 3: OpenRouter Fallback Pool** | **7 Keys** (`OPENROUTER_API_KEY_1..7`) | `liquid/lfm-2.5-2.6b:free`, `inclusionai/ling-3.0-flash-fin:free`, `minimax/minimax-m3:free`, `nemotron-3-super-120b` | 1700ms – 4800ms | Global failover safety net providing high-diversity open-source models when upstream tiers hit rate boundaries. |

### Automated Rotation State Machine
- **Round-Robin Key Pointer:** Advances automatically upon any `HTTP 429` (Rate Limit), `HTTP 402` (Credits Exhausted), or `HTTP 404` (Deprecated Slug).
- **Exponential Backoff:** Applied per tier with non-blocking pauses: $\text{delay} = \min(\text{delay} \times 1.5, 4.0)$.
- **Cross-Tier Cascading:** Tier 1 $\rightarrow$ Tier 2 $\rightarrow$ Tier 3, providing up to **38 consecutive attempts** with zero downtime.

---

## Empirical Benchmark Table

An empirical benchmark evaluating **16 free open-access models** across 6 complex diverse tasks (Short Latency Ping, Classical Physics, Calculus Derivatives, JSON Schema Extraction, Deductive Logic, Algorithmic Code Generation) was conducted to construct the optimal fallback hierarchy:

| Model Identifier | Success Rate | Avg Latency | Prompt Tokens | Completion Tokens | Reliability Grade | Production Routing Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `liquid/lfm-2.5-2.6b:free` | **100.0%** | **1714.0 ms** | 333 | 1065 | **Grade A+** | **Tier 3 Primary** |
| `inclusionai/ling-3.0-flash-fin:free` | **100.0%** | **2550.9 ms** | 389 | 1065 | **Grade A** | **Tier 3 Secondary** |
| `nvidia/nemotron-3-super-120b-a12b:free`| **100.0%** | **2578.8 ms** | 371 | 1004 | **Grade A** | **Tier 3 Active** |
| `cohere/north-mini-code:free` | **100.0%** | **2706.1 ms** | 265 | 1061 | **Grade A** | **Tier 3 Active** |
| `poolside/laguna-xs-2.1:free` | **100.0%** | **2891.7 ms** | 526 | 1065 | **Grade A** | **Tier 3 Active** |
| `nvidia/nemotron-3-ultra-550b-a55b:free`| **100.0%** | **3144.7 ms** | 213 | 665 | **Grade B+** | **Tier 3 Active** |
| `dots-studio/dots-3-note-preview:free` | **100.0%** | **3162.7 ms** | 349 | 1065 | **Grade B+** | **Tier 3 Active** |
| `nvidia/nemotron-3-nano-omni-30b-a3b:free`| **100.0%** | **3957.9 ms** | 227 | 1147 | **Grade B** | **Tier 3 Active** |
| `minimax/minimax-m2.7:free` | **100.0%** | **4018.2 ms** | 514 | 1065 | **Grade B** | **Tier 3 Active** |
| `minimax/minimax-m3:free` | **100.0%** | **4819.3 ms** | 1246 | 626 | **Grade B** | **Tier 3 Active** |
| `poolside/laguna-s-2.1:free` | **100.0%** | **6122.5 ms** | 526 | 937 | **Grade C** | High Latency |
| `z-ai/glm-5.2:free` | **33.3%** | **1799.4 ms** | 129 | 450 | **Grade D** | Unstable Endpoint |
| `nvidia/nemotron-3.5-lightning:free` | **0.0%** | N/A | N/A | N/A | **Offline** | HTTP 404 / Retired Slug |
| `thinkingmachines/inkling:free` | **0.0%** | N/A | N/A | N/A | **Offline** | Quota Depleted |
| `thinkingmachines/inkling-small:free` | **0.0%** | N/A | N/A | N/A | **Offline** | Quota Depleted |
| `nvidia/llama-nemotron-rerank-vl:free`| **0.0%** | N/A | N/A | N/A | **Offline** | HTTP 404 / Retired Slug |

---

## Quickstart & Installation Guide

### Mode A: Standalone Mobile Setup (100% On-Device via Termux)

1. **Activate Shizuku:**
   - Enable **Developer Options** and **Wireless Debugging** in Android Settings.
   - Open **Shizuku**, pair via Wireless Debugging with the 6-digit code, and tap **Start**.
   - Export `rish` to Termux and verify: `rish -c "id"` (returns `uid=2000(shell)`).
2. **Install Termux Dependencies:**
   ```bash
   pkg update -y && pkg install -y python git clang libxml2 libxslt
   pip install requests pytest
   ```
3. **Clone & Configure:**
   ```bash
   git clone https://github.com/partofcosmos-site/autonomous-android-controller.git
   cd autonomous-android-controller
   cp .env.example .env
   nano .env  # Insert your API keys
   ```
4. **Install Global CLI Wrapper:**
   ```bash
   cp ai $PREFIX/bin/ai && chmod +x $PREFIX/bin/ai
   ```
5. **Disable Phantom Process Killer:**
   ```bash
   rish -c "device_config put activity_manager max_phantom_processes 2147483647"
   rish -c "settings put global settings_enable_monitor_phantom_procs false"
   ```

### Mode B: PC Remote Control Setup (Host Workstation)

1. **Connect over Wireless ADB:**
   ```bash
   adb connect <DEVICE_IP>:5555
   adb devices
   ```
2. **Install Python Dependencies:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: .\venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   cp .env.example .env      # Populate API keys
   ```
3. **Run from Workstation:**
   ```bash
   # Windows batch wrapper
   .\ai.cmd "set volume to 70% and open YouTube"

   # Direct Python execution
   python master_agent.py "set volume to 70% and open YouTube"
   ```

---

## CLI Usage Guide

### 1. Compound Autonomous Missions
```bash
# Hardware volume manipulation and video search
ai "set volume to 80% and play Kishore Kumar on YouTube"

# Messaging automation (self-addressed verification)
ai "open WhatsApp and message +15551234567 saying meeting started"

# Browser control & visual navigation
ai "open Firefox and switch to private browsing"

# Display brightness adjustment
ai "set screen brightness to 60%"
```

### 2. Multilingual Natural Language Execution
```bash
# Bengali (বাংলা)
ai "volume 70 percent koro ebong gaan chalao"

# Hindi (हिंदी)
ai "aawaz 80 percent badhao aur gaana lagao"
```

### 3. Conversational Queries & Telemetry
```bash
# Identity and capability inspection (no external web search loop)
ai "who are you"
ai "what capabilities do you have"

# View execution transcript of previous mission
ai log
```

### 4. Interactive Terminal Summoner
Launch the interactive terminal menu:
```bash
./summon_agent.sh
```

---

## Testing & Verification Instructions

The codebase includes an offline unit test suite validating controllers, intent parsing, ReAct diagnosis schemas, and strict privacy/sanitization rules:

```bash
# Run complete test suite via pytest
python -m pytest tests -v

# Run test suite via Python standard unittest
python -m unittest discover tests -v

# Run forensic privacy & sanitization audit
python -m pytest tests/test_sanitization.py -v
```

All tests execute completely offline using mock device bridges, ensuring deterministic CI/CD verification without requiring a physical connected device.

---

## Documentation Suite

For detailed technical deep-dives, consult the specialized documentation suite:

* [**Architecture & System Evolution**](docs/architecture-evolution.md) — Exhaustive technical chronology of Shizuku IPC, multi-provider failover state machines, Samsung OneUI hardware edge cases, and the ReAct perception loop.
* [**Setup & User Operation Guide**](docs/setup-guide.md) — Comprehensive step-by-step setup manual covering Shizuku pairing, Termux environment setup, PC remote control, and troubleshooting.
* [**Engineering Post-Mortem & Roadblocks**](docs/engineering-postmortem.md) — Detailed technical post-mortem of real-world bugs encountered, failed naive approaches, and architectural solutions.
* [**Hardware Platform Profile & Platform Quirks**](docs/hardware-quirks.md) — Deep-dive into Samsung Galaxy M56 (`SM-M566B`) hardware specifications, discrete 15-step audio quantization formulas, and display insets.

---

## Project Structure

```
autonomous-android-controller/
├── .env.example               # Template configuration for multi-provider API keys
├── .gitignore                 # Strict git ignore rules (excluding .env, logs)
├── LICENSE                    # Unmodified Apache License, Version 2.0
├── README.md                  # Primary project overview and documentation suite index
├── requirements.txt           # Core Python dependencies (requests, pytest)
├── master_agent.py            # Flagship autonomous controller & ReAct diagnostic engine
├── agent.py                   # Fast sub-300ms dual-mode intent dispatcher
├── autoglm_agent.py           # Visual UI perception agent with bounding-box center taps
├── rotate_keys.py             # 19-key automated multi-provider rotator
├── summon_agent.sh            # Interactive mobile dialog summoner for Termux
├── ai                         # Global POSIX CLI executable wrapper for mobile shell
├── ai.cmd                     # Windows shell wrapper for PC remote execution
├── docs/                      # Technical documentation suite
│   ├── architecture-evolution.md
│   ├── setup-guide.md
│   ├── engineering-postmortem.md
│   └── hardware-quirks.md
└── tests/                     # Automated offline test suite
    ├── test_controllers.py    # Unit tests for hardware and intent controllers
    ├── test_sanitization.py   # Forensic privacy, PII, and secret hygiene audit
    └── ...
```

---

## License

This project is licensed under the **Apache License, Version 2.0**. See the [LICENSE](LICENSE) file for the full license text.

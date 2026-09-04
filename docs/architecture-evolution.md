# Architecture Evolution: From Accessibility Scrapers to an Autonomous Rootless ReAct Agent

---

## 1. Executive Summary & Research Retrospective

Mobile automation has long lagged behind desktop and cloud environments in stability, privilege accessibility, and reasoning capability. While cloud web automation benefits from deterministic DOM trees, DevTools protocols (CDP), and headless browsers, Android automation has historically been constrained by mobile sandboxing, OEM UI customizations, and aggressive operating system battery and background process management.

This document chronicles the research, technical evolution, and production architecture of the **Autonomous Android Controller** (`partofcosmos-site/autonomous-android-controller`). Over multiple development phases, the project evolved through three distinct automation paradigms:

1. **Genesis Architecture & Early Exploration:** Evaluating traditional Android Accessibility Services (`AccessibilityNodeInfo`) and sandboxed agent APKs, revealing severe event lag, tree drops on custom canvas/Flutter rendering, and Android 13+ "Restricted Settings" friction.
2. **Rootless Privilege Escalation:** Harnessing the Shizuku framework to bridge standard userland terminals (Termux) directly into Android's native `UID 2000` (`shell`) execution domain over Binder IPC, achieving full system access without rooting or tripping SafetyNet/Play Integrity.
3. **Resilient 19-Key Multi-Provider Routing:** Designing a 3-tier, 19-key automated failover state machine across Primary Low-Latency Flash API endpoints, Groq LPU high-speed inference, and an OpenRouter fallback pool to achieve zero-downtime execution under heavy agentic workloads.
4. **Hardware & OEM Scaling on Samsung OneUI:** Solving hardware-level platform quirks on the Samsung Galaxy M56 (`SM-M566B`), including discrete 15-step audio stream quantization, media session dual-dispatch, and display cutout inset handling.
5. **Perception-Action-Verification Closed Loop:** Transitioning from fragile static intent classifiers to an autonomous ReAct (Observe $\rightarrow$ Plan $\rightarrow$ Act $\rightarrow$ Verify $\rightarrow$ Diagnose $\rightarrow$ Correct) loop with live multi-modal diagnostic reasoning.

---

## 2. Chapter 1: Genesis & Problem Statement

### 2.1 The Limitations of Traditional Accessibility Services

Early mobile automation agents relied almost exclusively on Android's native Accessibility Service API (`android.accessibilityservice.AccessibilityService`). While designed to assist users with disabilities by inspecting screen content and dispatching synthetic gestures, utilizing Accessibility Services for general-purpose autonomous control suffers from three fatal architectural flaws:

#### A. Virtual Tree Dropping & Modern UI Opacity
Android's Accessibility framework constructs a virtual hierarchical representation of the active window (`AccessibilityNodeInfo`). However, modern Android application development has shifted away from traditional Android View hierarchies (`android.widget.TextView`, `android.widget.Button`) toward declarative and immediate-mode graphics frameworks:
- **Flutter & Skia/Impeller:** Applications built with Flutter render into a raw Skia or Impeller OpenGL/Vulkan canvas. Accessibility semantics must be manually annotated by app developers; if unannotated, the entire interactive interface appears to an accessibility service as a single opaque canvas node with zero children.
- **Jetpack Compose:** While Compose exposes accessibility semantics, dynamic layout transitions frequently cause race conditions where the accessibility tree lags 300ms to 800ms behind actual on-screen rendering.
- **WebViews & Games:** Hybrid web containers and Unity/Unreal game engines render external DOMs or 3D viewports that do not expose interactive elements to the system accessibility bridge.

#### B. Android 13+ "Restricted Settings" Security Guardrails
Starting in Android 13 (API 33), Google introduced "Restricted Settings" for any sideloaded application (e.g. apps installed via APK, browser, or third-party stores). When a user attempts to activate an accessibility service for a sideloaded controller:
1. The system displays a modal dialog: *"Restricted setting: For your security, this setting is currently unavailable."*
2. The user must manually navigate to App Info, tap an overflow menu, select "Allow restricted settings", authenticate via biometric or lock-screen PIN, and only then return to Accessibility settings to grant permission.
3. On corporate, managed, or enterprise work profiles, restricted settings are permanently locked by Device Policy Controllers (DPC), rendering accessibility-based agents completely inoperable.

#### C. System Event Throttling & Severe Battery Drain
Android's `AccessibilityManagerService` runs in the system server and broadcasts accessibility events to registered services. Monitoring full-window accessibility events creates substantial CPU overhead. During continuous automation or background monitoring:
- Active battery drain spikes between **15% and 25% per hour**.
- High-frequency UI changes trigger internal system rate limiters, causing the OS to drop accessibility change events (`TYPE_WINDOW_CONTENT_CHANGED`), leading to missed states and brittle automation.

#### D. Synthetic Input Limitations
Accessibility services inject touch events via `dispatchGesture()`. This API relies on high-level synthetic path generation:
- It cannot simulate low-level multi-touch kernel protocols cleanly.
- It is blocked from interacting with secure system dialogs or `FLAG_SECURE` password fields.
- It cannot inject text or key events into out-of-focus background applications.

### 2.2 The Bottlenecks of Sandboxed APKs

A secondary approach evaluated during early architecture was deploying the controller as a dedicated, standalone Android APK. However, standard Android sandboxing imposes strict Linux UID isolation:
- Every installed app runs under its own unique Linux UID (e.g. `UID 10245`).
- Sandboxed apps cannot access window hierarchies or memory spaces of other applications without system signatures.
- Screen capture requires the `MediaProjection` API, which prompts the user with an unavoidable, modal warning dialog (*"Start recording or casting with [App]?"*) every single time the session starts.
- Sandboxed apps cannot execute privileged system utilities (`cmd`, `dumpsys`, `pm`, `settings`, `uiautomator`).

### 2.3 The Rootless Alternative: Establishing the UID 2000 Privilege Boundary

To achieve complete system-level automation without rooting the physical hardware (which voids warranties, breaks Samsung Knox, and trips SafetyNet / Play Integrity attestation), the project established its execution boundary at **Android UID 2000 (`shell`)**.

| Architectural Dimension | Accessibility Service | Sandboxed APK | Rooted Su Daemon | Rootless Shizuku (`UID 2000`) |
| :--- | :--- | :--- | :--- | :--- |
| **Linux UID** | App Sandbox (`UID 10xxx`) | App Sandbox (`UID 10xxx`) | Superuser (`UID 0`) | Shell (`UID 2000`) |
| **SafetyNet / Play Integrity** | Intact | Intact | **Permanently Tripped** | **100% Clean & Intact** |
| **Samsung Knox Warranty Bit** | Unaffected (`0x0`) | Unaffected (`0x0`) | **Tripped (`0x1`)** | **Untouched (`0x0`)** |
| **UI Hierarchy Access** | AccessibilityNodeInfo (Laggy) | Blocked | Complete | **Native `uiautomator dump`** |
| **System CLI Utilities** | Blocked | Blocked | Complete | **Native `cmd`, `pm`, `settings`** |
| **Direct Audio Gain Access** | Blocked | Blocked | Complete | **Native `cmd media_session`** |
| **Background Daemon Stability** | Throttled / Killed | Throttled / Killed | Unrestricted | **Configurable via `device_config`** |
| **Invocation Latency** | 150ms – 400ms | N/A | < 5ms | **< 5ms via Binder IPC (`rish`)** |

---

## 3. Chapter 2: Rootless Privilege Escalation via Shizuku & ADB

### 3.1 Wireless Debugging & Local TLS Loopback Pairing (Android 11+)

Prior to Android 11, ADB shell access required tethering the device to an external computer via USB cable or running an ADB daemon over an unencrypted local network port. Android 11 introduced **Wireless Debugging**, an on-device mechanism built on Wi-Fi Direct and TLS 1.3:
- The system pairs client connections using a 6-digit PIN and an ephemeral TLS pairing port advertised via mDNS (`_adb-tls-pairing._tcp`).
- Once paired, communication moves to a persistent, authenticated loopback port (`127.0.0.1:<port>`).

However, standard shell scripts executing in Termux cannot easily maintain this connection:
1. Reconnecting over raw TLS sockets inside Termux requires complex OpenSSL wrapping and certificate persistence.
2. If the user disconnects from Wi-Fi or switches access points, the Android OS alters the ephemeral debugging port, breaking naive TCP connections.

### 3.2 The Shizuku IPC Architecture & The `rish` Bridge

Shizuku solves this limitation elegantly by decoupling the TLS pairing lifecycle from local application processes:
1. **Elevated Server Process:** Shizuku authenticates once via Wireless Debugging loopback and spawns an elevated server process running natively under `UID 2000` (`shell`).
2. **Android Binder IPC Protocol:** Rather than routing commands through high-overhead network sockets, Shizuku exposes an Android Binder interface registered with the local system service registry.
3. **The `rish` Executable & Runtime DEX Injection:** Shizuku provides a standalone command-line client (`rish`) and an accompanying compiled Dalvik Executable (`rish.dex`):
   - When the agent invokes `rish -c "<command>"`, `rish` loads `rish.dex` into a lightweight `app_process` instance.
   - `rish.dex` communicates directly with the Shizuku server across the kernel Binder driver (`/dev/binder`).
   - The Shizuku server executes the command in the context of `UID 2000` and streams stdout, stderr, and the return code back to Termux via Binder shared memory.

```
┌─────────────────────────────────────────────────────────────┐
│                 Termux Userland Environment                 │
│        (Python 3.10+ Controller / master_agent.py)          │
└──────────────────────────────┬──────────────────────────────┘
                               │
                       executes `/system/bin/rish` (< 5ms)
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                   `rish` Client Bridge                      │
│             Loads `/data/local/tmp/rish.dex`                │
└──────────────────────────────┬──────────────────────────────┘
                               │
                   Kernel Binder IPC (`/dev/binder`)
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                   Shizuku Server Daemon                     │
│               Running as `UID 2000` (shell)                 │
└──────────────┬───────────────────────────────┬──────────────┘
               │                               │
               ▼                               ▼
┌──────────────────────────────┐ ┌────────────────────────────┐
│      Android OS Framework    │ │      System Binaries       │
│  - WindowManagerService      │ │  - `uiautomator` (UI Dump) │
│  - AudioService (Stream 3)   │ │  - `cmd` (media_session)   │
│  - ActivityManager (`am`)    │ │  - `input` (tap/swipe/key) │
│  - PackageManager (`pm`)     │ │  - `settings` / `dumpsys`  │
└──────────────────────────────┘ └────────────────────────────┘
```

The overhead of this Binder IPC invocation is **under 5 milliseconds**, allowing the agent to perform high-frequency state inspection and input injection without perceptible delay.

### 3.3 Remote ADB TCP Port 5555 Fleet Dispatch

When controlling the device externally from a development workstation or automated testing server, the controller leverages standard ADB over TCP:
```bash
# Enable TCP listening on target device
adb tcpip 5555

# Connect over local network (using device IP address)
adb connect <DEVICE_IP>:5555

# Verify rootless shell execution
adb -s <DEVICE_IP>:5555 shell "id"
# Output: uid=2000(shell) gid=2000(shell) groups=2000(shell)...
```
Both execution paths (`rish` on-device and `adb shell` from host PC) expose identical command semantics, allowing `master_agent.py` to run unmodified in either environment by auto-detecting the active shell bridge.

### 3.4 Overriding the Android Phantom Process Killer

Beginning with Android 12, the Linux kernel and `ActivityManager` enforce the **Phantom Process Killer**. When an unprivileged background app (such as Termux) spawns sub-processes (such as Python workers, `cat`, `grep`, or `uiautomator`), the OS monitors child processes spawned outside the application's root cgroup:
- If the total count of phantom child processes across the system exceeds **32**, the OS aggressively sends `SIGKILL` (`kill -9`) to terminate them.
- This caused long-running Python agent scripts or multi-step ReAct loops to crash silently mid-mission.

Because Shizuku grants native `UID 2000` shell access, the controller executes a permanent system configuration override:
```bash
# Increase phantom process ceiling to maximum 32-bit integer limit
device_config put activity_manager max_phantom_processes 2147483647

# Disable system-wide monitoring of background phantom processes
settings put global settings_enable_monitor_phantom_procs false
```
This permanently eliminates unexpected process termination, allowing the agent to maintain persistent memory daemons, background loggers, and multi-step ReAct missions indefinitely.

---

## 4. Chapter 3: Resilient 19-Key Multi-Provider Failover Architecture

### 4.1 The 19-Key 3-Tier Hierarchy

High-frequency autonomous agents generate dense LLM traffic: mission planning, visual coordinate extraction, settling verifications, and error diagnoses. Relying on a single API endpoint or single API key invariably leads to rate limits (HTTP 429), quota exhaustion (HTTP 402), or transient provider downtime.

To guarantee continuous availability, the controller integrates a resilient **19-key key vault structured across three independent provider tiers**:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                       Incoming Mission Prompt                           │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│             Tier 1: Primary Low-Latency Flash Endpoints                 │
│      7 Independent API Keys (PRIMARY_FLASH_KEY_1 .. 7)                  │
│      Models: flash-lite-latest, flash-latest, flash-preview, 2.5-flash  │
│      Latency: ~800ms - 1200ms | Role: Deep ReAct Planning & Diagnoses   │
└──────────────────┬──────────────────────────────────▲───────────────────┘
                   │ Failover on HTTP 429/402/5xx     │ Round-Robin
                   ▼                                  │ Exhaustion
┌─────────────────────────────────────────────────────────────────────────┐
│             Tier 2: Groq High-Speed Open-Source Inference               │
│      5 Independent API Keys (GROQ_API_KEY_1 .. 5)                       │
│      Models: qwen/qwen3.8-27b, openai/gpt-oss-120b, llama-3.3-70b       │
│      Latency: ~250ms - 450ms | Role: Reflex Action Classification       │
└──────────────────┬──────────────────────────────────────────────────────┘
                   │ Failover on HTTP 429/402/5xx
                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│             Tier 3: OpenRouter Multi-Model Fallback Pool                │
│      7 Independent API Keys (OPENROUTER_API_KEY_1 .. 7)                 │
│      Models: liquid/lfm-2.5-2.6b, ling-3.0-flash, minimax-m3, nemotron  │
│      Latency: ~1700ms - 4800ms | Role: High-Diversity Global Fallback   │
└─────────────────────────────────────────────────────────────────────────┘
```

#### Detailed Provider Tier Specifications

| Tier | Provider & Engine | Key Count | Primary Model Targets | End-to-End Latency | Strategic Role |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Tier 1** | **Primary Flash Endpoints** | **7 Keys** (`PRIMARY_FLASH_KEY_1..7`) | `flash-lite-latest`, `flash-latest`, `flash-preview`, `2.5-flash` | 800ms – 1200ms | Complex multi-step task planning, JSON schema adherence, visual hierarchy evaluation, and ReAct self-diagnosis. |
| **Tier 2** | **Groq LPU Inference** | **5 Keys** (`GROQ_API_KEY_1..5`) | `qwen/qwen3.8-27b`, `openai/gpt-oss-120b`, `llama-3.3-70b-versatile` | 250ms – 450ms | Sub-300ms reflex intent routing, emergency hardware actuation, and rapid single-turn classifications. |
| **Tier 3** | **OpenRouter Fallback Pool** | **7 Keys** (`OPENROUTER_API_KEY_1..7`) | `liquid/lfm-2.5-2.6b:free`, `inclusionai/ling-3.0-flash-fin:free`, `minimax/minimax-m3:free`, `nvidia/nemotron-3-super-120b-a12b:free` | 1700ms – 4800ms | Global failover safety net providing high-diversity open-source models when upstream tiers hit rate boundaries. |

### 4.2 Automated Failover State Machine

The key rotation engine (`rotate_keys.py` and `query_llm_resilient` in `master_agent.py`) implements a resilient failover state machine:

1. **Round-Robin Key Pointer:** Each tier maintains an independent rotation index:
   $$\text{index}_{t} = (\text{index}_{t} + 1) \pmod{N_t}$$
2. **Intercepted HTTP Error Codes:**
   - `HTTP 429` (Rate Limit Exceeded / Quota Exhaustion)
   - `HTTP 402` (Payment or Account Credit Required)
   - `HTTP 404` (Model Slug Deprecated or Retired)
   - `HTTP 408 / 504` (Gateway Timeout > 25.0s)
   - `ConnectionError / SSLError` (Network Socket Reset)
3. **Exponential Backoff with Jitter:** When an error occurs, the rotator delays before advancing:
   $$\text{delay} = \min(\text{base\_delay} \times 1.5^{\text{attempts}}, 4.0)$$
4. **Cross-Tier Cascading:** If all 7 keys in Tier 1 encounter consecutive errors, execution automatically cascades down to Tier 2 (Groq). If Tier 2 is exhausted, execution cascades to Tier 3 (OpenRouter).
5. **Zero-Downtime Guarantee:** With 19 independent developer keys across 3 distinct cloud infrastructures, the system provides up to **38 consecutive retry attempts** before an unrecoverable failure is returned.

### 4.3 Empirical Robustness Benchmark (16 Free OpenRouter Models)

To construct an empirical fallback hierarchy for Tier 3, a benchmark evaluation was conducted across **16 free open-access models**. Each model was evaluated across 6 diverse task domains:
1. *Short Latency Ping:* Minimal response latency under cold and warm starts.
2. *Classical Mechanics (Physics):* Multi-step kinematic calculations.
3. *Calculus Derivatives:* Symbolic mathematics and chain rule operations.
4. *JSON Schema Extraction:* Strict adherence to structured agent tool-calling schemas.
5. *Competitive Logic:* Multi-hop deductive reasoning and constraint satisfaction.
6. *Algorithmic Code Generation:* Python algorithmic implementation.

#### Comprehensive Benchmark Results

| Model Identifier | Success Rate | Avg Latency | Prompt Tokens | Completion Tokens | Reliability Grade | Production Status |
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
| `z-ai/glm-5.2:free` | **33.3%** | **1799.4 ms** | 129 | 450 | **Grade D** | Unstable |
| `nvidia/nemotron-3.5-lightning:free` | **0.0%** | N/A | N/A | N/A | **Offline** | HTTP 404 / Slug Retired |
| `thinkingmachines/inkling:free` | **0.0%** | N/A | N/A | N/A | **Offline** | Rate Limit Depleted |
| `thinkingmachines/inkling-small:free` | **0.0%** | N/A | N/A | N/A | **Offline** | Rate Limit Depleted |
| `nvidia/llama-nemotron-rerank-vl:free`| **0.0%** | N/A | N/A | N/A | **Offline** | HTTP 404 / Slug Retired |

*Key Takeaway:* Models exhibiting 100% success rates and sub-3000ms latency (`liquid/lfm-2.5-2.6b:free` and `inclusionai/ling-3.0-flash-fin:free`) were selected as the primary routing targets for Tier 3, while retired or unstable slugs were pruned from the rotation schema.

---

## 5. Chapter 4: Android Hardware Control & Samsung OneUI Platform Quirks

### 5.1 Samsung Galaxy M56 (`SM-M566B`) Hardware Baseline

The controller was specifically deployed, profiled, and optimized against the **Samsung Galaxy M56 (`SM-M566B`)**, representing a modern Android 14 / OneUI 6.x hardware target:
- **SoC:** Samsung Exynos 1480 (4nm process; 4x Cortex-A78 @ 2.75GHz + 4x Cortex-A55 @ 2.0GHz).
- **GPU:** AMD RDNA2-based Xclipse 530 GPU.
- **Display:** 6.7-inch Super AMOLED+, 1080 x 2340 FHD+ resolution, 120Hz refresh rate, 393 ppi density.
- **Memory & Storage:** 8GB LPDDR5 RAM, 128GB/256GB UFS 3.1 storage.
- **Operating System:** Samsung OneUI 6.x / 7.0 running on Android 14 (API 34).

### 5.2 Discrete 15-Step Audio Stream Quantization

In standard Android Open Source Project (AOSP), the audio subsystem exposes continuous volume scales (0–100 or 0–25). However, Samsung OneUI strictly enforces a **discrete 15-step quantization index** for `STREAM_MUSIC` (Stream 3):
- Index `0`: Complete Mute.
- Index `15`: Maximum Hardware Gain.
- Intermediate values exist purely as integer steps $i \in \{0, 1, 2, \dots, 15\}$.

#### The Failure of Naive Volume Approaches
1. **Hardware Keyevents (`input keyevent 24` / `25`):** Sending volume up/down keyevents only adjusts volume by 1 index increment out of 15 (~6.6%). A user request such as *"set volume to 80%"* would require calculating relative offsets and firing multiple keyevent pulses in rapid succession.
2. **Floating Volume Overlay Obstruction:** Firing repeated keyevents causes Samsung OneUI to render a large floating volume slider overlay that covers the right side of the screen for 3.0 seconds, occluding underlying UI elements and corrupting `uiautomator dump` XML captures.
3. **Substring Matching Bug:** Naive volume string parsers evaluating `elif "0%" in prompt` prior to integer regex extraction match `"80%"` and `"90%"` because `"0%"` is a literal substring, causing volume to mistakenly mute!

#### The Quantization Formula & Direct AudioService Binder Dispatch
To resolve this, the controller extracts the explicit integer percentage via regex and applies mathematical quantization:
$$\text{target\_idx} = \text{clamp}\left(0, 15, \text{round}\left(\frac{\text{percentage} \times 15}{100}\right)\right)$$

| Requested Percentage | Math Calculation | Samsung OneUI Index | Effective Hardware Gain |
| :--- | :--- | :--- | :--- |
| **0% (Mute)** | $0 \times 15 / 100 = 0.0$ | **Index 0** | Muted (0.0 dB) |
| **20%** | $20 \times 15 / 100 = 3.0$ | **Index 3** | 20.0% Gain |
| **40%** | $40 \times 15 / 100 = 6.0$ | **Index 6** | 40.0% Gain |
| **50% (Half)** | $50 \times 15 / 100 = 7.5$ | **Index 8** | 53.3% Gain |
| **70%** | $70 \times 15 / 100 = 10.5$ | **Index 11** | 73.3% Gain |
| **80%** | $80 \times 15 / 100 = 12.0$ | **Index 12** | 80.0% Gain |
| **90%** | $90 \times 15 / 100 = 13.5$ | **Index 14** | 93.3% Gain |
| **100% (Max)** | $100 \times 15 / 100 = 15.0$ | **Index 15** | Maximum Hardware Gain |

The command is dispatched directly to the system AudioService via `cmd media_session`:
```bash
cmd media_session volume --stream 3 --set 12
```
*Key Advantage:* This binder command updates the hardware audio amplifier instantly **without rendering the floating UI volume slider**, leaving the screen completely clear for subsequent UI inspection.

### 5.3 Media Session Dual-Dispatch Protocol

Samsung OneUI aggressively manages background media players (Spotify, YouTube, Samsung Music, Podcasting apps). When an application moves to the background, OneUI frequently revokes window focus, causing standard Linux keyevents (`input keyevent 85` for play/pause) to be ignored because no focused window accepts the media event.

To ensure deterministic media control, the controller implements a **Dual-Dispatch Protocol**:
1. **Primary Session Dispatch:** Sends a direct session command via `cmd media_session dispatch <action>`. This reaches `MediaSessionService` directly, routing to the active `MediaSession.Token` regardless of window focus.
2. **Keyevent Fallback Dispatch:** Immediately follows with the corresponding hardware keyevent to trigger foreground media responders:

| Action | Primary Session Dispatch | Linux Keyevent Fallback |
| :--- | :--- | :--- |
| **Play** | `cmd media_session dispatch play` | `input keyevent 126` (`KEYCODE_MEDIA_PLAY`) |
| **Pause** | `cmd media_session dispatch pause` | `input keyevent 127` (`KEYCODE_MEDIA_PAUSE`) |
| **Next Track** | `cmd media_session dispatch next` | `input keyevent 87` (`KEYCODE_MEDIA_NEXT`) |
| **Previous Track**| `cmd media_session dispatch previous` | `input keyevent 88` (`KEYCODE_MEDIA_PREVIOUS`) |
| **Toggle Play/Pause**| `cmd media_session dispatch play-pause`| `input keyevent 85` (`KEYCODE_MEDIA_PLAY_PAUSE`) |

### 5.4 Screen Brightness Control

Device brightness is managed through the system settings provider table on a scale from 0 to 255:
- **Querying State:** `settings get system screen_brightness`
- **Setting Level:** `settings put system screen_brightness <value>`
- **Safety Clamping:** The controller clamps target values to `[1, 255]` to prevent accidental screen blackout, which would disable visual feedback for the user.

### 5.5 Display Geometry, Insets & Spatial Grounding

The physical display geometry of the Samsung Galaxy M56 dictates strict bounding constraints for automated touch injection:

```
[0, 0] ────────────────────────────────────────── [1080, 0]
│  STATUS BAR INSET (Camera Cutout) - Height: 97px          │
[0, 97] ───────────────────────────────────────── [1080, 97]
│                                                           │
│                                                           │
│                                                           │
│               INTERACTIVE VIEWPORT                        │
│               X: [0, 1080]                                │
│               Y: [97, 2210]                               │
│               Usable Height: 2113px                       │
│                                                           │
│                                                           │
│                                                           │
[0, 2210] ─────────────────────────────────────── [1080, 2210]
│  NAVIGATION BAR INSET (Gesture Pill) - Height: 130px      │
[0, 2340] ─────────────────────────────────────── [1080, 2340]
```

- **Full Display Bounds:** `[0, 0]` to `[1080, 2340]` (1080x2340 pixels).
- **Status Bar Inset:** `[0, 0]` to `[1080, 97]` (`android:id/statusBarBackground`, height 97px).
- **Navigation Bar Inset:** `[0, 2210]` to `[1080, 2340]` (`android:id/navigationBarBackground`, height 130px).
- **Interactive Viewport:** $X \in [0, 1080]$, $Y \in [97, 2210]$.
- **Collision Avoidance:** Any programmatic touch injected at $Y < 97$ risks triggering notification pull-down shades, while $Y > 2210$ risks triggering Android system back/home gestures. The element center calculator automatically bounds interactive targets within the safe viewport.

---

## 6. Chapter 5: Evolution of the Perception-Action-Verification Closed Loop

The agent controller evolved through three distinct evolutionary generations:

```
┌─────────────────────────────────────────────────────────────┐
│  STAGE 1: Static Case Handlers & Open-Loop Intent Dispatch  │
│  - agent.py: Natural language -> regex/rules -> am start    │
│  - Limitation: Zero perception, fails silently on crashes   │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│  STAGE 2: Iterative Visual Grounding & Element Coordinates  │
│  - autoglm_agent.py: uiautomator dump -> center tap loop     │
│  - Limitation: Greedy execution, no verification or repair  │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│  STAGE 3: Autonomous Closed-Loop ReAct Diagnosis Engine     │
│  - master_agent.py: Observe -> Plan -> Act -> Settle        │
│    -> Verify -> Self-Diagnose -> Corrective Actuation Loop   │
│  - Features: Multi-attribute telemetry, live JSON diagnosis │
└─────────────────────────────────────────────────────────────┘
```

### 6.1 Stage 1: Static Case Handlers & Open-Loop Intent Dispatch (`agent.py`)
In the earliest implementation, the agent functioned as an intent dispatcher. User instructions were categorized into predefined regex rules or single-turn LLM intent classifications, emitting hardcoded `am start` intents.
*Failure Mode:* Completely blind and open-loop. If an intent launched a disambiguation dialog ("Open with Chrome or Browser?"), or if the app crashed, the agent had zero awareness and reported success falsely.

### 6.2 Stage 2: Iterative Visual Grounding (`autoglm_agent.py`)
To overcome intent brittleness, Stage 2 introduced visual UI hierarchy extraction. The agent captured `uiautomator dump` XML snapshots, parsed clickable nodes, extracted bounding boxes, and computed center coordinates:
$$\text{center}_x = \frac{x_1 + x_2}{2}, \quad \text{center}_y = \frac{y_1 + y_2}{2}$$
The agent executed sequential taps in an 8-step iterative loop.
*Failure Mode:* Greedy execution. The agent executed taps sequentially without verifying whether a tap actually triggered the expected state change. If an unexpected permissions dialog or soft keyboard popped up, the agent continued tapping stale coordinates.

### 6.3 Stage 3: Autonomous Closed-Loop ReAct Diagnostic Engine (`master_agent.py`)
Stage 3 represents the production architecture: an autonomous ReAct loop with multi-privilege before/after state verification and automated diagnostic self-healing.

```
       ┌──────────────────────────────────────┐
       │   1. OBSERVE Screen & Hardware State │
       │   - Foreground package & activity    │
       │   - Audio stream & brightness level  │
       │   - Parsed XML interactive nodes     │
       └──────────────────┬───────────────────┘
                          │
                          ▼
       ┌──────────────────────────────────────┐
       │   2. PLAN Task Decomposition         │
       │   - Ordered typed milestones         │
       │   - Fast-path package targeting      │
       └──────────────────┬───────────────────┘
                          │
                          ▼
       ┌──────────────────────────────────────┐
       │   3. ACT (Hardware / Intent / Tap)   │
       │   - cmd media_session / input tap    │
       └──────────────────┬───────────────────┘
                          │
                          ▼
       ┌──────────────────────────────────────┐
       │   4. SETTLE UI Transitions (1.2s)    │
       │   - Await animation & page load      │
       └──────────────────┬───────────────────┘
                          │
                          ▼
       ┌──────────────────────────────────────┐
       │   5. VERIFY Fresh Multi-Modal State  │
       │   - Compare before vs after state    │
       │   - Check text presence & focus      │
       └──────────────────┬───────────────────┘
                          │
                 ┌────────┴────────┐
         Goal Satisfied?    Goal Blocked?
                 │                 │
                 ▼                 ▼
          [Advance Step]   ┌──────────────────────────────────┐
                           │   6. SELF-DIAGNOSE & REPAIR      │
                           │   - Identify blocking modal/popup│
                           │   - Synthesize corrective action │
                           │   - Re-actuate & Re-evaluate     │
                           └──────────────────────────────────┘
```

#### The Structured Verification Schema
During Step 5 and Step 6, the diagnostic engine passes the multi-modal state delta to the LLM and demands strict JSON output:
```json
{
  "diagnosis": "Detailed analysis of current screen state, blockers, or UI state changes.",
  "verified_success": true,
  "evidence": "Concrete proof (e.g. Volume index updated from 8 to 12; foreground window confirmed com.google.android.youtube).",
  "corrective_action": {
    "action": "none",
    "x": 0,
    "y": 0,
    "code": 0,
    "cmd": ""
  }
}
```
If `verified_success` is `false`, the controller immediately executes `corrective_action` (e.g. dismissing an unexpected soft keyboard via `code: 4` (Back), clicking an "Accept" dialog button at `[x, y]`, or re-issuing an intent) and re-evaluates the state up to 2 times before escalating.

---

## 7. Chapter 6: Production Engineering, Security Boundaries & Ethical Guardrails

### 7.1 Defense-in-Depth Security Boundaries

Operating under `UID 2000` provides immense system capability. To maintain user safety and data confidentiality, the controller enforces strict defensive boundaries:

1. **`FLAG_SECURE` SurfaceFlinger Enforcement:**
   - Applications handling sensitive data (banking applications, password managers, private messaging credentials) declare `WindowManager.LayoutParams.FLAG_SECURE`.
   - Android's SurfaceFlinger hardware compositor blanks screen memory for secured surfaces.
   - The controller respects this hardware boundary: when `FLAG_SECURE` is active, the agent halts visual coordinate extraction and safely delegates authentication to Android's native Autofill and biometric hardware prompts.
2. **Biometric Authentication Delegation:**
   - The agent never attempts to automate or record lock-screen PINs, pattern locks, or fingerprint prompts.
3. **Strict Self-Addressed Messaging Boundary:**
   - In messaging automation modules (SMS, WhatsApp), the controller strictly validates recipient numbers against the user's self-contact, preventing unintended third-party transmissions.

### 7.2 Zero-PII Discipline & Open-Source Scrubbing Protocols

All code, logs, benchmarks, and documentation committed to the repository adhere to the **Strict Privacy Mandate**:
- Zero personal email addresses: strictly RFC 2606 placeholders (`user@example.com`).
- Zero personal phone numbers: strictly dummy international placeholders (`+15551234567`).
- Zero private local area network IPs: documentation uses placeholder `<DEVICE_IP>` or RFC 5737 documentation test addresses (`198.51.100.1`).
- Zero committed secrets: `.env` is permanently excluded via `.gitignore`, and `.env.example` provides dummy templates.
- Zero forbidden brand or personal names: complete neutrality across all documentation and commit history.

---

## 8. Appendix: Android Linux Keyevent Reference

| Keycode | Android Constant Name | Controller Usage & Semantics |
| :--- | :--- | :--- |
| `3` | `KEYCODE_HOME` | Returns to default launcher home screen; resets clean state. |
| `4` | `KEYCODE_BACK` | Navigates back; dismisses soft keyboards and transient popups. |
| `24` | `KEYCODE_VOLUME_UP` | Increments hardware audio gain by 1 step. |
| `25` | `KEYCODE_VOLUME_DOWN` | Decrements hardware audio gain by 1 step. |
| `26` | `KEYCODE_POWER` | Toggles display power state. |
| `85` | `KEYCODE_MEDIA_PLAY_PAUSE`| Toggles playback on active media session. |
| `87` | `KEYCODE_MEDIA_NEXT` | Skips to next audio/video track. |
| `88` | `KEYCODE_MEDIA_PREVIOUS` | Skips to previous audio/video track. |
| `126` | `KEYCODE_MEDIA_PLAY` | Forces media playback resume. |
| `127` | `KEYCODE_MEDIA_PAUSE` | Forces media playback pause. |
| `187` | `KEYCODE_APP_SWITCH` | Opens Recent Apps multitasking carousel. |

---

*Authored by the Autonomous Android Controller Engineering Team.*
*Licensed under the Apache License, Version 2.0.*

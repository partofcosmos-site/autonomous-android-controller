# Hardware Platform Profile, Platform Quirks & Limitations

---

## 1. Device Hardware Baseline: Samsung Galaxy M56 (`SM-M566B`)

The **Autonomous Android Controller** is specifically tuned, validated, and optimized against the **Samsung Galaxy M56 (`SM-M566B`)**, representing a modern Android 14 / Samsung OneUI 6.x hardware platform.

### Hardware Specifications Summary

| Component / Subsystem | Technical Specification | Operational Impact for Automation |
| :--- | :--- | :--- |
| **Model Designation** | `SM-M566B` / `SM-M566B/DS` | Dual-SIM 5G Global Variant. |
| **System-on-Chip (SoC)** | Samsung Exynos 1480 (4nm process) | High single-core burst capability for local JSON parsing. |
| **CPU Topology** | 4x Cortex-A78 @ 2.75GHz + 4x Cortex-A55 @ 2.0GHz | Big.LITTLE architecture; background cgroups throttled if not exempted. |
| **GPU Architecture** | AMD RDNA2-based Xclipse 530 GPU | Hardware-accelerated Vulkan UI compositing. |
| **Display Panel** | 6.7" Super AMOLED+ (1080 x 2340 pixels) | High-contrast ratio; deep blacks with 120Hz refresh rate. |
| **Aspect Ratio / DPI** | 19.5:9 Aspect Ratio (~393 ppi density) | Requires dynamic center-coordinate calculation over static pixel bounds. |
| **Memory Configuration** | 8GB LPDDR5 RAM + 128GB/256GB UFS 3.1 | Ample memory for concurrent Termux Python daemons and target apps. |
| **Operating System** | Samsung OneUI 6.x / 7.0 (Android 14, API 34) | Aggressive OEM background process policies; discrete audio quantization. |
| **Privilege Model** | Rootless UID 2000 (`shell`) via Shizuku | Native binder IPC access without modifying system partitions. |

---

## 2. Display Geometry, Insets & Spatial Grounding

Samsung Galaxy M56 features an Infinity-O top center camera cutout and customizable navigation insets. The controller uses precise geometry grounding derived directly from real-device `uiautomator dump` XML hierarchies (`local_dump.xml`):

```
(0, 0) ────────────────────────────────────────── (1080, 0)
│   TOP STATUS BAR INSET (Height: 97px)                     │
│   bounds="[0,0][1080,97]" (android:id/statusBarBackground)│
(0, 97) ───────────────────────────────────────── (1080, 97)
│                                                           │
│                                                           │
│               INTERACTIVE CONTENT VIEWPORT                │
│               Horizontal Range: X ∈ [0, 1080]             │
│               Vertical Range:   Y ∈ [97, 2210]            │
│               Usable Height:    2113 pixels               │
│                                                           │
│                                                           │
(0, 2210) ─────────────────────────────────────── (1080, 2210)
│   BOTTOM NAVIGATION BAR INSET (Height: 130px)             │
│   bounds="[0,2210][1080,2340]"                            │
│   (android:id/navigationBarBackground)                    │
(0, 2340) ─────────────────────────────────────── (1080, 2340)
```

### Inset Metrics & Collision Avoidance Rules
- **Full Display Canvas:** `[0, 0]` to `[1080, 2340]` ($1080 \times 2340$ pixels).
- **Status Bar Cutout Inset:** `[0, 0]` to `[1080, 97]` (Height: **97px**).
- **Navigation Bar Inset:** `[0, 2210]` to `[1080, 2340]` (Height: **130px**).
- **Interactive Safe Viewport:** $X \in [0, 1080]$, $Y \in [97, 2210]$ (Total interactive height: **2113px**).

#### Critical Grounding Rules
1. **Status Bar Pull-Down Collision:** Injecting synthetic taps at $Y < 97$ risks triggering the system notification shade or quick settings panel rather than in-app top navigation buttons.
2. **System Navigation Gesture Collision:** Injecting taps at $Y > 2210$ risks triggering Android's bottom gesture pill (triggering Home or Recent Apps).
3. **Bounding Box Center Calculation:** All touch coordinates are calculated dynamically using the geometric center formula:
   $$\text{Center}_X = \frac{X_1 + X_2}{2}, \quad \text{Center}_Y = \frac{Y_1 + Y_2}{2}$$
   clamped strictly within the $[97, 2210]$ vertical bounds.

---

## 3. Audio Stream Architecture & Discrete 15-Step Quantization

Unlike generic AOSP distributions that expose 0–100 or 0–25 continuous volume streams, Samsung OneUI strictly binds media volume (`STREAM_MUSIC`) to **16 discrete integer steps (indices 0 through 15)**.

### OneUI Stream Routing Identifiers
- **Stream 3:** `STREAM_MUSIC` (Music, video playback, streaming media, games, podcasts)
- **Stream 2:** `STREAM_RING` (Incoming telephony ringtones)
- **Stream 4:** `STREAM_ALARM` (Device clock alarms)
- **Stream 5:** `STREAM_NOTIFICATION` (System notifications and message alerts)
- **Stream 1:** `STREAM_SYSTEM` (Keypad clicks, haptic feedback tones)

### Discrete Quantization Formula
When natural language prompts request volume levels as percentages (e.g. *"set volume to 80%"*), the controller applies the quantization formula:
$$\text{target\_idx} = \text{clamp}\left(0, 15, \text{round}\left(\frac{\text{percentage} \times 15}{100}\right)\right)$$

### Complete Quantization Mapping Table

| Requested Percentage | Mathematical Ratio | Discrete Index (0..15) | Effective Hardware Gain |
| :--- | :--- | :--- | :--- |
| **0% (Mute)** | $0 \times 15 / 100 = 0.0$ | **Index 0** | Muted (0.0 dB) |
| **10%** | $10 \times 15 / 100 = 1.5$ | **Index 2** | 13.3% Gain |
| **20%** | $20 \times 15 / 100 = 3.0$ | **Index 3** | 20.0% Gain |
| **30%** | $30 \times 15 / 100 = 4.5$ | **Index 5** | 33.3% Gain |
| **40%** | $40 \times 15 / 100 = 6.0$ | **Index 6** | 40.0% Gain |
| **50% (Half)** | $50 \times 15 / 100 = 7.5$ | **Index 8** | 53.3% Gain |
| **60%** | $60 \times 15 / 100 = 9.0$ | **Index 9** | 60.0% Gain |
| **70%** | $70 \times 15 / 100 = 10.5$ | **Index 11** | 73.3% Gain |
| **80%** | $80 \times 15 / 100 = 12.0$ | **Index 12** | 80.0% Gain |
| **90%** | $90 \times 15 / 100 = 13.5$ | **Index 14** | 93.3% Gain |
| **100% (Max)** | $100 \times 15 / 100 = 15.0$ | **Index 15** | Maximum Hardware Gain |

### Direct Programmatic AudioService Dispatch
To prevent the large Samsung OneUI floating volume slider from obstructing the display, commands are sent directly to the AudioService binder interface:
```bash
# Query current music volume index
cmd media_session volume --stream 3 --get

# Set discrete volume index directly (e.g., 80% -> index 12)
cmd media_session volume --stream 3 --set 12

# Relative notch adjustments
cmd media_session volume --stream 3 --adj raise
cmd media_session volume --stream 3 --adj lower
```

---

## 4. MediaSession Token Binding & Dual-Dispatch Protocol

Samsung OneUI aggressively optimizes memory by suspending background audio player activities. When an app moves to the background:
- Standard Linux keyevents (`input keyevent 85`) fail if the application has relinquished active window focus.
- The `MediaSessionService` preserves the app's `MediaSession.Token` in kernel memory even after window focus is lost.

To guarantee deterministic media playback control across background and foreground applications, the controller executes a **Dual-Dispatch Protocol**:

```
                               ┌────────────────────────────────┐
                               │   Natural Language Media Goal  │
                               │  ("pause playback", "play music")
                               └───────────────┬────────────────┘
                                               │
                                               ▼
                               ┌────────────────────────────────┐
                               │     Dual-Dispatch Protocol     │
                               └───────┬────────────────┬───────┘
                                       │                │
            Primary Session Dispatch   │                │   Keyevent Fallback
            (MediaSessionService)      │                │   (Linux Input Layer)
                                       ▼                ▼
                     ┌──────────────────┐      ┌─────────────────┐
                     │ cmd media_session│      │ input keyevent  │
                     │ dispatch <action>│      │ <keycode>       │
                     └─────────┬────────┘      └────────┬────────┘
                               │                        │
                               └───────────┬────────────┘
                                           │
                                           ▼
                     ┌───────────────────────────────────────────┐
                     │ Deterministic Media Playback State Update │
                     └───────────────────────────────────────────┘
```

### Media Action Dispatch Mapping

| Action | Primary Binder Dispatch | Linux Keyevent Fallback | Target Responders |
| :--- | :--- | :--- | :--- |
| **Play** | `cmd media_session dispatch play` | `input keyevent 126` (`KEYCODE_MEDIA_PLAY`) | Background players with active session tokens. |
| **Pause** | `cmd media_session dispatch pause` | `input keyevent 127` (`KEYCODE_MEDIA_PAUSE`) | Foreground & background audio sessions. |
| **Next Track** | `cmd media_session dispatch next` | `input keyevent 87` (`KEYCODE_MEDIA_NEXT`) | Spotify, YouTube Music, Samsung Music. |
| **Previous Track**| `cmd media_session dispatch previous`| `input keyevent 88` (`KEYCODE_MEDIA_PREVIOUS`) | Spotify, YouTube Music, Samsung Music. |
| **Toggle Play/Pause**| `cmd media_session dispatch play-pause`| `input keyevent 85` (`KEYCODE_MEDIA_PLAY_PAUSE`)| System-wide media focus holder. |

---

## 5. Screen Brightness Hardware Controls

Device screen brightness is controlled via the system settings database on an integer scale from 0 to 255:
```bash
# Query active brightness
settings get system screen_brightness

# Set brightness level (e.g., 50% = ~128)
settings put system screen_brightness 128
```
**Safety Clamping:** The controller enforces strict bounds:
$$\text{brightness} = \text{clamp}(1, 255, \text{target})$$
Clamping the minimum value to `1` rather than `0` prevents accidental screen blackout, ensuring that the physical display remains visible to the user at all times.

---

## 6. OEM Battery Optimizations & Background Execution Policies

Samsung OneUI includes aggressive memory management features through **Device Care** and `ActivityManager` background process killing:

### Required Device Settings Configuration
To ensure uninterrupted background agent execution:
1. **Termux Battery Optimization Exemption:**
   - Navigate to **Settings** $\rightarrow$ **Apps** $\rightarrow$ **Termux** $\rightarrow$ **Battery**.
   - Select **Unrestricted** (prevents Android from placing Termux in deep sleep).
2. **Shizuku Battery Optimization Exemption:**
   - Navigate to **Settings** $\rightarrow$ **Apps** $\rightarrow$ **Shizuku** $\rightarrow$ **Battery**.
   - Select **Unrestricted**.
3. **Recent Apps Locking:**
   - In the Recent Apps multitasking screen, tap the app icon above the Termux card and select **Lock this app**. This prevents OneUI's memory manager from terminating Termux when launching heavy external applications.
4. **Phantom Process Killer Override:**
   - As documented in Chapter 2, execute the privileged override via `rish`:
     ```bash
     rish -c "device_config put activity_manager max_phantom_processes 2147483647"
     rish -c "settings put global settings_enable_monitor_phantom_procs false"
     ```

---

## 7. Known Issues & Platform Limitations

1. **`FLAG_SECURE` SurfaceFlinger Blanking:**
   - Applications handling sensitive information (such as banking apps, password fields, or DRM-protected video) set `WindowManager.LayoutParams.FLAG_SECURE`.
   - Android's SurfaceFlinger blanks the display framebuffer for these surfaces, returning empty black screens in `screencap` and sanitized XML dumps.
   - *Mitigation:* The controller recognizes `FLAG_SECURE` boundaries and gracefully hands over authentication tasks to Android's native Autofill service and biometric hardware.
2. **Wireless Debugging Wi-Fi Dependency:**
   - If the device completely disconnects from all Wi-Fi networks or reboots in an offline environment, Wireless Debugging requires a Wi-Fi connection to initialize Shizuku. Once Shizuku is started, Termux maintains its Binder IPC bridge even if Wi-Fi is subsequently disabled.
3. **Display Scaling Customizations:**
   - If the user modifies "Screen zoom" or "Font size" in Samsung Settings, the physical pixel dimensions of system bars may shift by $\pm 10\%$. Dynamic bounding box center calculation handles in-app content adaptively regardless of user scaling settings.

---

*Authored by the Autonomous Android Controller Engineering Team.*
*Licensed under the Apache License, Version 2.0.*

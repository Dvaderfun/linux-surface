# First-generation Surface Laptop: camera enablement and evidence

Both built-in cameras and the exposure-synchronized IR illuminator produced frames on a physical Microsoft Surface Laptop. The tests below separate kernel support, image processing, and desktop delivery. This is a reproducible engineering reference for reviewing the individual changes; the branch is not a kernel release or an installation overlay.

| Component | Review target | Observed on the SL1 |
| --- | --- | --- |
| Color sensor and bridge | [Existing kernel PR #186](https://github.com/linux-surface/kernel/pull/186); [actual tested series in #2401](https://github.com/linux-surface/linux-surface/issues/2401); [sources and review differences](kernel/color/README.md) | Both ACPI endpoints enumerated; the OV9734 bound, captured and runtime-suspended. The original PR head differs in probe and power handling. |
| Color processing | [Libcamera OV9734 series](https://patchwork.libcamera.org/cover/28869/), [tuning series](https://patchwork.libcamera.org/cover/29021/), [rebasing and testing](libcamera/README.md) | A clean upstream build with the pending changes delivered 1280×704. With the additional single-stream HD change it delivered real 1280×720 NV12 at about 30 fps when requested. |
| Infrared sensor and light | [Linux-media strobe v3 8/9](https://lore.kernel.org/linux-media/20261113024059.1087031-9-antoine.pichot@gmail.com/); [exact SL1 backport and differences](kernel/infrared/README.md) | OV7251 captured 640×480 at 30 sensor frames/s. Every other exposure received light. Two optical runs at fixed exposure/gain detected the same alternation across the scene. |
| Desktop IR | [Optional PipeWire source](https://github.com/Dvaderfun/linux-surface/tree/contrib/sl1-infrared-camera/contrib/surface-laptop1-ir) | 30 fps in ambient light, or 15 distinct illuminated frames/s. Cooperates with the existing color stack's media lock. No face authentication or simultaneous RGB/IR streaming is claimed. |

**Hardware and software.** DMI product `Surface Laptop`, SKU `Surface_Laptop`, firmware 138.3732.768; Fedora 45, kernel `7.3.4-2.surface.fc45.x86_64`, Secure Boot enabled. Color: OV9734 / OVTI9734 / MSHW0073, one lane on CSI-2 port 1, 19.2 MHz input clock. IR: OV7251 / INT347E / MSHW0074, on a different CSI port of the same Intel CIO2. The tested Fedora config already enabled the sensor module. [Packaging PR #2404](https://github.com/linux-surface/linux-surface/pull/2404) adds it to the common 7.3 fragment. Enabling it in the common config fragment is useful for builds where the baseline disabled it; it does not implement missing driver or userspace behavior.

**What to build.** For kernel integration, use the [development-branch instructions](kernel/color/README.md) and the [IR backport base](kernel/infrared/README.md). The alternative color series and PR #186 are not cumulative. For userspace use the [pinned libcamera recipe](libcamera/README.md). The IR companion can be built and staged separately, defaults to ambient capture, and does not install a kernel module or enable login services on its own. Its README describes opting into the light, checking dependencies, and removing the utility. The Fedora private libraries and locally signed kernel binaries used for early testing are not required deliverables.

**Reproduce the checks.** Close camera clients first. On an equipped SL1 these tests consume frames without displaying or saving images. The optical check requires Python 3, a C compiler, Linux media UAPI headers and `media-ctl`. The PipeWire checks additionally need Python GObject introspection for GStreamer, the PipeWire GStreamer plugin and `pw-dump`.

```sh
python3 checks/check.py --self-test      # synthetic controls; no device access
python3 checks/check.py --also-color    # optical off/on/off, then desktop color
python3 checks/capture.py --infrared    # separately check the published IR source
python3 checks/check-sharing.py         # with the illuminated desktop source selected/configured
```

The optical probe compares matched unsaturated regions in contiguous 10-bit sensor frames at constant shutter (400 lines) and gain (8×). It checks that only one parity brightens, that the unlit parity stays near ambient and that the baseline returns after disabling strobe. It takes the same media-device lock as libcamera, and restores formats, route and controls on exit. Sensor node numbering may change on reboot; the tools discover the graph.

| Recorded checks on the installed test stack | Observation |
| --- | --- |
| [Optical run 1](evidence/sl1-optical-run1.json) and [repeat](evidence/sl1-optical-final.json) | 19.4 → 192.2 → 19.3 and 20.6 → 251.9 → 20.5 (off → lit → off, 0–1023 scale); 13/13 and 17/17 usable central regions responded in phase. |
| [Exact proposed IR package](evidence/staged-pipewire.json) and [direct checks](evidence/staged-direct.json) | An explicitly linked GStreamer client on a private PipeWire graph received 12 timestamped 640×480 YUY2 frames in each mode, 30.0 fps passive and 15.0 fps illuminated; strobe read zero after both. |
| [GNOME Camera](evidence/sl1-gnome-preview.json) | The actual preview negotiated color at 1280×720 and IR at 640×480, 15 fps. Strobe was off during color and after closing IR. |
| [Sensor-process death](evidence/sl1-release.json) and [desktop-client death](evidence/sl1-desktop-client-exit.json) | Both cleared the strobe. The test harness restored gain separately after killing the low-level process; a subsequent desktop capture succeeded. |
| [Shared controller](evidence/sl1-sharing.json) | RGB maintained 30.3 fps during an IR request; IR maintained 15.0 fps during an RGB request. The second camera worked after the first released the controller. |

The tested CIO2 driver routes one queue to DMA channel 0. Its two sensor nodes do not imply concurrent capture. The [CIO2 code](https://github.com/gregkh/linux/blob/v7.3.4/drivers/media/pci/intel/ipu3/ipu3-cio2.c#L992) and the bridge's POSIX lock explain the behavior. A raw V4L2 client that ignores that lock is outside the desktop sharing guarantee. Results are for one Laptop 1, not for every Surface with an OV7251. Active-stream system suspend/resume on the final SL1 kernel series, other models, formal optical-safety certification, and release packaging are not established by these tests.

**Wiki proposal.** The [three-page patch](wiki/sl1-camera-status.patch) updates the camera table, the Laptop 1 device page and its feature-matrix cell. It marks support experimental and leaves the Laptop 2 row alone. It applies to wiki commit `89ead87adc7e26ee50ae23a0e5696c899ff1c017`; from a clean clone of `https://github.com/linux-surface/linux-surface.wiki.git`, use `git apply --check /path/to/sl1-camera-status.patch` to review. The wiki is a separate Git repository and a normal project pull request does not update it.

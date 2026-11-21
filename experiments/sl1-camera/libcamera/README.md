# Surface Laptop 1: libcamera color follow-up

**Recommendation:** keep the kernel PR independent. Add the [current userspace submission](https://patchwork.libcamera.org/cover/28869/) to its prerequisites and contribute the new Laptop 1 measurements to that thread. Submit the [native 720p follow-up](rfc/ov9734-native-720.diff) separately to libcamera as an RFC dependent on those changes. The tested helper adaptation and eight unmodified patches already registered and streamed the color camera; the 720p follow-up is not required to get a picture.

## Upstream status on 2026-11-22

* [libcamera master tested](https://gitlab.freedesktop.org/camera/libcamera/-/tree/adfa719f8ed67d18fd8a0739fc088a1f8b9e7252) has no OV9734 helper. In this pipeline the [IPU3 IPA](https://gitlab.freedesktop.org/camera/libcamera/-/blob/adfa719f8ed67d18fd8a0739fc088a1f8b9e7252/src/ipa/ipu3/ipu3.cpp#L223) requires one. The low-resolution ImgU arithmetic fix is already [in master](https://gitlab.freedesktop.org/camera/libcamera/-/commit/b7a4bfe13e8427da92c4e5613b87feafec682caa); it was developed for Surface Go 3. Do not submit our older libcamera 0.7 patch bundle.
* Afonso Figuinha's [earlier series specifically for Laptop 1](https://patchwork.libcamera.org/cover/28781/) and GuyliandeJong's [v1](https://patchwork.libcamera.org/cover/28766/) are superseded. GuyliandeJong's [v2, three patches](https://patchwork.libcamera.org/cover/28869/) covers the sensor helper, uninitialized test-pattern mode and negotiated viewfinder size. All three were listed as New (not merged), and contain Afonso Figuinha's existing test credit. The properties table is not required to stream on this revision: the test-pattern initialization fixes the startup path, although libcamera may still warn about missing static properties. Adding measured control delays, cell dimensions and test-pattern mappings is a separate submission.
* The Nov 20 [helper registration change](https://gitlab.freedesktop.org/camera/libcamera/-/commit/d694890400a1dfff1251369f6bb0971eab001afc) invalidates the context and argument order of [patch #28870](https://patchwork.libcamera.org/patch/28870/). The [current-API adaptation](compat/28870-current-api.diff) implements its sensor data using the existing OV5640 helper: unity gain code 16; a 10-bit pedestal of 16; exposure margin 4 lines, matching [the kernel sensor driver](https://github.com/gregkh/linux/blob/v7.3.4/drivers/media/i2c/ov9734.c). This is a proposed rebase for the original author, not a competing series.
* The same author's [six pending image-quality patches](https://patchwork.libcamera.org/cover/29021/) add lens shading, black level, statistics handling and first-frame error reporting. We applied all six, plus #28871 and #28872, unmodified. [SHA-256 manifest and original message IDs](public-patches/manifest.json). The [sensor tuning](https://patchwork.libcamera.org/patch/29026/) was measured on Laptop 2; a working capture on Laptop 1 does not establish photometric calibration on this unit.
* Kernel [issue #993](https://github.com/linux-surface/linux-surface/issues/993), the [Laptop 2 report](https://github.com/linux-surface/linux-surface/issues/2401) and [Amirhussein Zia's independent Laptop 1/2 work](https://github.com/amirhusseinzia/surface-laptop-ipu3-camera/tree/bab8cdd4d04e2291d9f3c634bcb42b889d64de5b) provide the related project history. None is a released libcamera binary. libcamera asks for [email review and DCO sign-off](https://gitlab.freedesktop.org/camera/libcamera/-/blob/adfa719f8ed67d18fd8a0739fc088a1f8b9e7252/Documentation/contributing.rst); GitHub access is not required to send testing feedback. [Draft replies](review-reply.md).

## Physical results: upstream checkout, not the private desktop stack

Original Surface Laptop, OV9734, Fedora 45, kernel `7.3.4-2.surface.fc45.x86_64` with the existing hardware-tested sensor/bridge overrides. The private checkout built an IPU3 IPA, `cam` and libcamera 0.8; `cam` linked to its own just-built libcamera. No changes to the installed version, PipeWire or running services were needed. The sensor runtime-suspended after the tests.

| Stack and request | What the hardware delivered |
| --- | --- |
| [Two public series with the helper rebase](evidence/public-series-704.json); viewfinder, default exposure, no HD follow-up | Strict 1280×720 rejected because its adjusted height is 704. Strict 1280×704 delivered 50/50 full NV12 frames (901120 + 450560 bytes). Median settled rate in this scene 15.06 fps. |
| [Same build plus the native HD RFC](evidence/rfc-720-fixed30.json); strict 1280×720 and `FrameDurationLimits=[33333,33333]` | 50/50 full NV12 frames, 921600 Y bytes + 460800 UV bytes each. Median 30.04 fps; 30.07 fps over the run. The rates in these two rows use different exposure requests and are not a speed comparison. |
| [Check of the additional image rows](evidence/native-720-bands.json); fresh 30-frame capture | After eight settling frames, all 22 frames had distinct spatial samples in the bottom 16 Y and 8 UV rows. Bottom Y mean/SD 108.6/54.7; adjacent Y 115.1/55.9. The U and V bands also varied. No image files. |
| [Caps and validation](evidence/native-formats.txt) | Single-stream Viewfinder, VideoRecording and StillCapture each returned 10 distinct aligned modes, including 1280×704 and 1280×720. All 30 role/size pairs validated exactly. For Viewfinder + Raw and Viewfinder + VideoRecording, the existing 704 height limit remained. These are format validations, not multi-stream capture results. |

The HD RFC is limited to an OV9734 in its 1296×734 mode, one NV12 stream. Existing IPU3 multi-stream limits, raw capture, and other sensors' behavior do not change. It adds only the tested 1280×720 combination above the conservative 704 height cap, and avoids offering nonaligned sizes that validation would silently resize. The private Fedora 0.7.2 stack additionally tunes exposure, startup behavior and desktop settings. Do not attribute those changes, the private GNOME result, a default 30 fps in every scene, other IPU3 hardware coverage, or Windows image-quality parity to these upstream patches. A publisher must still build matching distribution libcamera/PipeWire packages before describing consumer support as available to users.

## Reproduce without installation

Use a C++ compiler, Meson, Ninja, pkg-config, OpenSSL, the project's [build dependencies](https://gitlab.freedesktop.org/camera/libcamera/-/blob/adfa719f8ed67d18fd8a0739fc088a1f8b9e7252/README.rst) for IPU3 and the cam app, and a Python 3 interpreter. Run from this directory. The preparer verifies each public mail archive against its recorded digest (using local cached mail if present), and refuses to overwrite a nonempty directory.

```sh
python3 prepare.py src
meson setup build-test src --wrap-mode=nodownload --buildtype=release \
  -Dpipelines=ipu3 -Dipas=ipu3 -Dcam=enabled -Dqcam=disabled \
  -Dgstreamer=disabled -Dlc-compliance=disabled -Ddocumentation=disabled \
  -Dpycamera=disabled -Dv4l2=disabled -Dtracing=disabled
ninja -C build-test
python3 verify-capture.py build-test/src/apps/cam/cam --height 704 --reject-hd
git -C src apply ../rfc/ov9734-native-720.diff
ninja -C build-test
python3 verify-capture.py build-test/src/apps/cam/cam --height 720 --fixed-30
python3 verify-planes.py build-test/src/apps/cam/cam
```

For the optional configuration check on the same laptop:

```sh
export PKG_CONFIG_PATH="$PWD/build-test/meson-uninstalled"
c++ -std=c++20 verify-formats.cpp $(pkg-config --cflags --libs libcamera) \
  -Wl,-rpath,"$PWD/build-test/src/libcamera:$PWD/build-test/src/libcamera/base" \
  -o build-test/verify-formats
build-test/verify-formats
```

For the final tree only, `python3 prepare.py src --with-720` applies both steps to a new directory. We verified the resulting files matched the tested checkout byte for byte. Tests that access a camera require an idle Surface Laptop 1 with the kernel fix installed; the capture verifier expects the OV9734 camera identity and never terminates other clients. `verify-planes.py` consumes NV12 via an anonymous pipe; only aggregate statistics leave memory. There is no system installation or kernel signing in this workflow.

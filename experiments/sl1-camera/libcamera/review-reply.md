# Draft libcamera submissions — not sent

Reply on the [OV9734 v2 cover](https://patchwork.libcamera.org/cover/28869/) (message-id `20261112085159.14289-1-guyliandejong@proton.me`). CC the author of the original SL1 series and keep current reviewers on the thread:

> I tested the OV9734 on a first-generation Surface Laptop with the kernel sensor and IPU bridge fixes, against libcamera adfa719f (2026-11-20). Patches 2/3 and 3/3 applied unchanged. Patch 1/3 no longer applies after d6948904 changed helper registration. The OV5640 helper has exactly the OV9734's gain divisor (16), 16/1024 black pedestal and 4-line exposure margin; registering `"ov9734"` alongside `"ov5640"` worked here. The latter value matches OV9734_EXPOSURE_MAX_MARGIN in the kernel.
>
> With that adaptation and the six pending IPU3 tuning patches from Nov 18, 50/50 processed frames captured successfully at strict 1280×704 NV12 (901120 + 450560 bytes). Strict 1280×720 correctly reported an adjustment. No system libraries or camera plugin changes were needed for the test. This is a combined-stack test rather than a per-patch sign-off.
>
> The 1296×734 sensor has sufficient ImgU margin for one actual 1280×720 processed stream. In a separate scoped follow-up the same build delivered 50/50 full 1280×720 NV12 frames at median 30.04 fps with FrameDurationLimits set to [33333,33333]. In a second capture the bottom 16 Y and 8 U/V rows varied on all 22 measured frames; they are not padded copies. I'll keep the HD follow-up separate from your enablement series.

Reply on the [Nov 18 tuning series](https://patchwork.libcamera.org/cover/29021/) (message-id `20261118164621.15513-1-guyliandejong@proton.me`):

> This six-patch series applies unchanged on adfa719f together with the Nov 12 OV9734 v2 prerequisites (with the sensor helper registration updated for current master). I confirmed processed NV12 capture on a Surface Laptop 1 at 1280×704 for 50 successive frames. This is a streaming smoke test; I did not independently recalibrate lens shading or verify colorimetry on this unit.

Proposed subject for the distinct dependent change: **[RFC PATCH] pipeline: ipu3: Allow native 720p for the OV9734 single-stream mode**

> The 1296×734 sensor mode can supply 1280×720 without a Bayer downscale; the conservative 32-line output height rule restricts it to 704. Permit only that tested combination for an OV9734 and one processed stream; cap mixed streams as before. Advertise the additional size along with existing aligned sizes rather than reporting a size that configure will adjust.
>
> This follows the pending OV9734 v2 series, in particular its viewfinder-size fix. Scope is deliberately limited to tested hardware while the generic BDS/margin rules remain uncertain. A shared geometry-based calculation could replace the quirk once checked against other ImgU users.
>
> Validation on Surface Laptop 1: 50 successive 1280×720 NV12 frames with advancing timestamps and correct plane sizes, median 30.04 fps with a 33.333 ms frame-duration request; 22 distinct post-settling samples from the previously excluded bottom rows of Y, U and V. Confirmed 30 single-stream role/size enumerations validate exactly and two multi-stream configuration combinations retain the 704 height cap.

Attach [the RFC diff](rfc/ov9734-native-720.diff) to a separately authored submission rebased on the accepted/public prerequisite. The test feedback does not introduce any invented Reviewed-by, Tested-by or Signed-off-by trailers. A real submitting developer must provide their own DCO sign-off and retain the prerequisite authors' attribution; a GitHub pull request is not the libcamera submission channel.

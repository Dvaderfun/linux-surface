# Driver source used for the Laptop 1 measurements

`sl1-ov7251-strobe.patch` is the **exact source delta measured**, not an
additional generic linux-media submission. Retain the original author's
[patch and Signed-off-by](https://lore.kernel.org/linux-media/20261113024059.1087031-9-antoine.pichot@gmail.com/)
when discussing its origin; do not reuse that sign-off as certification of
downstream changes. The source is GPL-2.0 like the existing OV7251 driver.
The strobe mechanism, pulse limits and alternate-frame pattern come from
Antoine Pichot's [v3 patch 8/9](https://github.com/antoine79/surface-ir-camera/blob/d21b84370ebbc0019bcf7f35ebda439039721489/kernel/patches/v3-posted/v3-0008-media-i2c-ov7251-Add-strobe-output-enable-control.patch).

The measured source was [Linux stable v7.3.4](https://github.com/gregkh/linux/blob/7595a62d45ee1a2297eafa5f2ef5d0a45142d84d/drivers/media/i2c/ov7251.c)
with linux-surface's ANALOGUE_GAIN change already applied (the packaged module's
text matched the baseline build byte for byte). The attached diff scopes the
control to the measured DMI product+SKU and ACPI HID and subsystem, programs
pulses with the output disabled, rounds the 45% cap down, detects short writes,
and clears cached requests on stop/error. It omits other fixes and model
rotation entries from the nine-patch series. It applies cleanly with
`git apply --check` against the [v7.3-surface driver](https://github.com/linux-surface/kernel/blob/195730abf6fa8c6908585f8a986211007ead1d90/drivers/media/i2c/ov7251.c)
as well. The signed test module was loaded on 7.3.4, not on 7.3.5.
The patch SHA-256 is
`2430e512d63f05136ab5277d6a7a3487aec3c6d97fe6b4712fd518699db23a2a`.

No driver binaries, private keys, Secure Boot certificates, firmware, Windows
binary or MSI are supplied. Use the project's normal kernel build and signing
process for the exact target kernel; do not install binaries built for another
version. Coordinate with the current linux-media author about stream lifecycle
before considering any distro backport, and drop downstream differences when
upstream provides equivalent behavior.

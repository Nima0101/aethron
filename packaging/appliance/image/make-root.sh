set -eu
mkdir /tmp/guest-root
tar -xf - -C /tmp/guest-root
cp /tmp/guest-root/boot/vmlinuz-* /out/kernel
cp /tmp/guest-root/boot/initrd.img-* /out/initrd
truncate -s 1600M /out/rootfs.raw
mkfs.ext4 -q -F -d /tmp/guest-root /out/rootfs.raw
sha256sum /out/kernel /out/initrd /out/rootfs.raw > /out/image.sha256

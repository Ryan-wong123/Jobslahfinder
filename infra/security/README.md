# Chromium seccomp profile

`chromium-seccomp.json` derives from the Docker/Moby default profile at
commit `4b8214fc4971e06172938a1f1554ccff6647ee80`:
https://github.com/moby/profiles/blob/4b8214fc4971e06172938a1f1554ccff6647ee80/seccomp/default.json

One additional rule permits `clone`, `setns`, `unshare`, and `chroot`, so Chromium
can create and confine its own user-namespace sandbox. Kernel namespace ownership
and capability checks still apply. All other default-profile restrictions remain.
The scraper runs as an unprivileged user, drops every container capability, and
retains `no-new-privileges`. It does not use `--no-sandbox`, `SYS_ADMIN`, privileged
mode, or an unconfined seccomp profile.

Tested with the pinned scraper image on Docker Desktop's Linux engine. Run the
same sandbox probe on the AWS kernel before enabling the scraping worker; host
AppArmor user-namespace restrictions may require an administrator-reviewed profile.
Do not bypass a failed probe by disabling the browser sandbox.

`parser-seccomp.json` uses the same pinned upstream baseline and additionally
permits `mount`, `umount2`, and `pivot_root` for Bubblewrap's private mount
namespace. The worker retains no container capabilities; kernel user-namespace
checks constrain these calls. Bubblewrap hides uploaded volumes, the parent
PID/environment, and the network, binding only read-only code/libraries. The
production parser fails closed if this sandbox cannot start. Test both profiles
on the target host; neither grants SYS_ADMIN or disables seccomp.

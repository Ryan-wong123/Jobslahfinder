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

## AppArmor on Ubuntu

Docker's `docker-default` AppArmor policy denies mounts even inside a new user
namespace. The parser worker therefore uses `jobslahfinder-parser.apparmor`,
based on the same pinned Moby AppArmor template. It retains the proc/sys
protections, limits networking to Unix/IP sockets plus the netlink socket needed
to configure private loopback, and permits only the tmpfs/devpts,
bind/remount, propagation, and pivot operations Bubblewrap needs.
Container capabilities stay dropped; kernel namespace ownership still constrains
every mount. The profile is applied only to the private worker.

Install it on the Ubuntu Docker host before starting production workers:

```bash
sudo apt-get install -y apparmor
sudo bash infra/scripts/install-sandbox-apparmor.sh
python infra/scripts/test-parser-sandbox.py
```

The VM bootstrap and Linux CI job load this policy. The probe automatically uses
it when the Docker engine advertises AppArmor and fails if it is missing or
insufficient. Docker Desktop engines without AppArmor still test the same
seccomp, capabilities, namespaces, and filesystem restrictions; they cannot
validate AppArmor enforcement. Production Compose targets the Ubuntu VM and
explicitly requires the named profile.

The sandbox leaves `/proc` empty: extraction needs no procfs, and parent process
information is unavailable there. Docker's masked system paths remain intact;
no `systempaths=unconfined` or inherited worker `/proc` bind is used. The probe
checks the empty proc directory, private PID namespace, sanitized environment,
private loopback-only network, and real DOCX extraction together.

References: [Docker AppArmor policy loading](https://docs.docker.com/engine/security/apparmor/),
[pinned Moby baseline](https://github.com/moby/profiles/blob/4b8214fc4971e06172938a1f1554ccff6647ee80/apparmor/template.go).

"""Exercise release/rollback decisions with fake commands and no infrastructure access."""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[2]
IMAGE="ghcr.io/review/backend@sha256:"


def main():
    for mode in ("success", "legacy-failure", "compatible-failure", "rollback-failure"):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            scripts=root/"infra/scripts"
            scripts.mkdir(parents=True)
            (scripts/"deploy.sh").write_text((ROOT/"infra/scripts/deploy.sh").read_text())
            for script in ("provision-db-roles.sh","verify-deploy.sh"):
                (scripts/script).write_text("#!/bin/sh\nexit 0\n")
            (root/".env").write_text("DOMAIN=review.invalid\nMIGRATION_DATABASE_URL=unused-in-command-stub\n")
            if mode in {"compatible-failure","rollback-failure"}:
                (root/".release.env").write_text("ROLE_CONTRACT=security-v1\n"+"\n".join(f"{name}_IMAGE={IMAGE}{'b'*64}"for name in ("BACKEND","FRONTEND","SCRAPER"))+"\n")
            binaries=root/"bin"
            binaries.mkdir()
            (binaries/"docker").write_text("""#!/bin/sh
echo "$*" >> "$FIXTURE/events"
case "$*" in
 *'--pull never'*) [ "$FIXTURE_MODE" != rollback-failure ]; exit $? ;;
 *'up -d --no-build --wait'*) [ "$FIXTURE_MODE" = success ]; exit $? ;;
esac
exit 0
""")
            for command in ("sudo","curl"):
                (binaries/command).write_text("#!/bin/sh\nexit 0\n")
            for executable in binaries.iterdir():
                executable.chmod(0o755)
            env={**os.environ,"PATH":str(binaries)+os.pathsep+os.environ["PATH"],
                "FIXTURE":str(root),"FIXTURE_MODE":mode,"DEPLOY_SHA":"a"*40,"PREVIOUS_SHA":"c"*40,
                **{name+"_IMAGE":IMAGE+"a"*64 for name in ("BACKEND","FRONTEND","SCRAPER")}}
            process=subprocess.run(["bash",str(scripts/"deploy.sh")],env=env,capture_output=True,text=True)
            events=(root/"events").read_text()
            if mode=="success":
                assert process.returncode==0,process.stderr
                assert "ROLE_CONTRACT=security-v1"in(root/".release.env").read_text()
                assert IMAGE+"a"*64 in(root/".env").read_text()
            else:
                assert process.returncode==1
                if mode=="legacy-failure":
                    assert "--pull never"not in events
                    assert "stop backend worker scraper beat"in events
                else:
                    assert "--no-deps --no-build --pull never"in events
                    if mode=="compatible-failure":
                        assert IMAGE+"b"*64 in(root/".env").read_text()
                    else:
                        assert "stop backend worker scraper beat"in events
            print("PASS deployment decision:",mode)


if __name__=="__main__":main()

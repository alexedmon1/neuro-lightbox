# Hosting galleries on a LAN workstation (nginx or Apache)

A built gallery is **fully static** — the manifest is inlined into `index.html`
(`window.MANIFEST = …`), every asset reference is relative, and there is no
server-side code. So the host needs **only a static web server** — no Python, no
`uv`, no neuro-lightbox and no analysis package. Because all paths are relative,
galleries host cleanly under a sub-path (`/study-a/`, `/study-b/`).

Either **nginx** (§2a) or **Apache 2.4** (§2b) works — both ship a ready config
in `deploy/`. The web server is the only thing that differs; the read-only drive
mount (§1) and rebuild flow (§3) are identical, since both servers run as the
same `www-data` user on Debian/Ubuntu.

**Build vs serve are separate.** Keep *building* galleries on the machine that
has the analysis outputs (the montages read the maps each analysis folder lists).
The workstation only *serves* the finished `gallery*/` directories.

Worked example (placeholders to edit): an Ubuntu workstation serving two studies'
galleries from a results drive mounted at `/mnt/results`, LAN-only. Study A's gallery
has `links:` (e.g. to its preprocessing QC index), so the whole study folder is served
and the gallery sits at `/study-a/analyses/gallery/`; study B is served as its gallery
folder alone at `/study-b/`. A link from a gallery to a page outside the served folder
cannot resolve — serve the folder that holds both.

## 1. Mount the drive (read-only) so the web server can read it

Say the drive is NTFS. Find its UUID, then add an `/etc/fstab` line so it mounts at
boot, owned by the web server's `www-data` user (same user for nginx and Apache):

```bash
sudo blkid            # note the UUID of the results partition
sudo mkdir -p /mnt/results
```

```fstab
# /etc/fstab  (ntfs3 kernel driver; use ntfs-3g if ntfs3 is unavailable)
UUID=XXXX-XXXX  /mnt/results  ntfs3  ro,uid=www-data,gid=www-data,umask=0027,nofail,x-systemd.automount  0  0
```

```bash
sudo systemctl daemon-reload && sudo mount -a
ls /mnt/results/study-a/analyses/gallery/index.html   # sanity check
```

- `ro` — serve-only; the host never writes to the drive.
- `uid/gid=www-data` — the web server can read every file.
- `nofail,x-systemd.automount` — boot doesn't hang if the drive is absent.

> If the drive is **network-shared** (e.g. SMB from the build machine) rather
> than physically moved, mount that share instead — the rest is identical. If
> physically moved, build the gallery *before* moving the drive.

## 2a. Install nginx + the site

```bash
sudo apt update && sudo apt install -y nginx
sudo mkdir -p /srv/galleries
sudo cp deploy/landing.html /srv/galleries/index.html
sudo cp deploy/nginx-galleries.conf /etc/nginx/sites-available/galleries
sudo ln -sf /etc/nginx/sites-available/galleries /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
# edit the alias paths in the conf to match your mount, then:
sudo nginx -t && sudo systemctl reload nginx
```

Browse from any LAN machine to **`http://<workstation-ip>/`** → landing page →
`/study-a/` and `/study-b/`.

## 2b. Install Apache 2.4 + the site (alternative to 2a)

```bash
sudo apt update && sudo apt install -y apache2
sudo mkdir -p /srv/galleries
sudo cp deploy/landing.html /srv/galleries/index.html
sudo cp deploy/apache-galleries.conf /etc/apache2/sites-available/galleries.conf
sudo a2ensite galleries
sudo a2dissite 000-default          # drop the stock default site
# edit the Alias paths in the conf to match your mount, then:
sudo apache2ctl configtest && sudo systemctl reload apache2
```

`mod_alias` and `mod_dir` are enabled by default, so the sub-path serving and the
redirects work with no extra modules. Browse to **`http://<workstation-ip>/`** →
landing page → `/study-a/` and `/study-b/`.

## 3. Updating after a rebuild

Rebuild on the machine with the analysis outputs (`neuro-lightbox build --config <study.yaml>`).
The files on the shared drive update and the web server serves them immediately —
the build stamps a fresh `?v=` on `index.html`'s assets, so browsers pick up
changes on refresh. No reload needed. (If the drive was physically moved, re-copy
or re-mount the updated drive.)

## Options / troubleshooting

- **LAN password:** uncomment the auth block in the conf, then
  `sudo htpasswd -c /etc/nginx/.htpasswd labuser` (nginx) or
  `sudo htpasswd -c /etc/apache2/.htpasswd labuser` (Apache).
- **Adding a gallery:** nginx — copy a `location /<name>/ { alias …; }` block;
  Apache — copy an `Alias /<name> …` + matching `<Directory>` block. Then add a card
  to `landing.html`.
- **403 Forbidden:** the web server (`www-data`) can't read the path — re-check
  the mount `uid/gid/umask`, and that every parent dir is executable (`x`) for it.
  On Apache, also confirm the gallery dir has a `<Directory>` block with
  `Require all granted`.
- **AppArmor:** if serving from `/mnt` is blocked, allow the web server read
  access to the mount path (`/etc/apparmor.d/` profile — `usr.sbin.nginx` or
  `usr.sbin.apache2`) or mount under `/srv`.
- **Firewall:** `sudo ufw allow 80/tcp` if `ufw` is enabled.
- **Internet-facing instead of LAN:** add HTTPS — easiest is Caddy
  (automatic certs), or nginx/Apache + certbot — and require auth.

<a href="http://tarantool.org">
  <img src="https://avatars2.githubusercontent.com/u/2344919?v=2&s=250" align="right">
</a>

# RWS

The Repository Web Service is designed to interact with the repository via HTTP.
Currently, only the ability to upload packages to the repository via HTTP is
supported. S3 is used as storage.

## Table of contents
* [Getting started](#getting-started)
  * [Prerequisites](#prerequisites)
  * [Download](#download)
  * [Install dependencies](#install-dependencies)
  * [Run](#run)
  * [Usage](#usage)
* [Configuration](#configuration)
* [Caution](#caution)

## Getting started

### Prerequisites

 * [Python3](https://www.python.org/downloads/)
 * [pip](https://pypi.org/project/pip/)
 * [Git](https://git-scm.com/book/en/v2/Getting-Started-Installing-Git)

All other dependencies will be installed using `pip`.

### Download

Download service:
``` bash
git clone https://github.com/tarantool/rws.git
```

### Install dependencies

```bash
pip install -r requirements.txt
```

### Run

Set the necessary configuration settings before run the service
(see [Configuration](#configuration) section belows for more details).

Run development server:
``` bash
export FLASK_APP=app.py
flask run
```

Run production server:
``` bash
gunicorn --workers 1 --timeout 0 --threads 10 app:app
```
The `timeout` parameter should be set to `0`, because the worker can be checked
by the server only after the application (`app`) has started, but the
metainformation synchronization of all repositories starts before the
application and can take a long time in some cases.

### Usage

* Put package to repository.

  The HTTP `PUT` method is used to upload package to the repository.
  URL describes a path to the repository in the following format:
  `repo_kind/tarantool_series/dist/dist_ver`:
    * `repo_kind` - kind of repository (live, release, ...).
    * `tarantool_series` - tarantool series (1.10, 2.5, ...).
      As special value an `enabled` can be used. In this case, the package will
      be loaded into all tarantool series from the `enabled` section of the
      configuration file.
    * `dist` - distribution (fedora, ubuntu ...).
    * `dist_ver` - destribution version (30, 31 ...).

  To upload a package to the deb repository, necessary additionaly specify the
  "product" form. The "product" form is used to place package files in
  deb repositories
  (`.../release/series-2/ubuntu/pool/focal/main/p/product_name/...`).

  Example:
``` bash
curl -u user_name:password \
-F 'cartridge-cli-1.8.0.0-1.el7.x86_64.rpm=@/path/to/package/cartridge-cli-1.8.0.0-1.el7.x86_64.rpm' \
-F 'cartridge-cli-1.8.0.0-1.el7.src.rpm=@/path/to/package/cartridge-cli-1.8.0.0-1.el7.src.rpm' \
--request PUT 127.0.0.1:5000/live/1.10/el/7

{"message":"OK"}

curl \
-u login:password \
-F 'product=tarantool-smtp' \
-F 'tarantool-smtp_0.0.4.0-1_amd64.deb=@/home/leonid/Downloads/tarantool-smtp_0.0.4.0-1_amd64.deb' \
-F 'tarantool-smtp_0.0.4.0-1.debian.tar.xz=@/home/leonid/Downloads/tarantool-smtp_0.0.4.0-1.debian.tar.xz' \
-F 'tarantool-smtp_0.0.4.0-1.dsc=@/home/leonid/Downloads/tarantool-smtp_0.0.4.0-1.dsc' \
-F 'tarantool-smtp_0.0.4.0.orig.tar.xz=@/home/leonid/Downloads/tarantool-smtp_0.0.4.0.orig.tar.xz' \
--request PUT 127.0.0.1:5000/release/2.8/ubuntu/focal

{"message":"OK"}
```

* Update repository metainformation without uploading a package.

  The HTTP `POST` method is used to update repository metainformation
  without uploading a package. URL describes a path to the repository
  in the same format as the package upload.

  Example:
```bash
curl \
-u user_name:password \
--request POST 127.0.0.1:5000/release/2.8/ubuntu/focal
```

## Configuration

The configuration is set by the environment variables and configuration file.
In the case of using an environment variable, if a bool value is expected,
all values except "0" and "False" will be interpreted as "True". If the
variable is == "" or is not set, the default will be used.

Environment variables:
* `RWS_CFG` - path to a configuration file.
* `RWS_CREDENTIALS` - authentication credentials in JSON format
  ('{"name": "password_hash"}').
* `RWS_FORCE_SYNC` - skip malformed packages when synchronizing metainformation.
  Default: `False`.
* `GPG_SIGN_KEY_ARMORED` - gpg key in ASCII armored format to sign tarantool
  repositories.
* `GPG_MODULES_SIGN_KEY_ARMORED` - gpg key in ASCII armored format to sign
  "modules" repository.
  Export the key in ASCII armored format:
  ```bash
  gpg --armor --export-secret-keys MYKEYID > mykeys.asc)
  ```
* `S3_URL` - URL to access S3 (https://hb.bizmrg.com).
* `S3_REGION` - region (ru-msk, us-east-2, ...).
* `S3_BUCKET` - bucket name.
* `S3_BASE_PATH` - prefix path inside the bucket.
* `S3_ACCESS_KEY` - Access Key ID for the account.
* `S3_SECRET_KEY` - Secret Access Key for the account.
* `S3_PUBLIC_READ`- set read-only permission on files uploaded
  to S3 for anonymous users

Configuration file parameters(JSON, for example see `config.default`):

* `common`
  * `sync_on_start`(bool) - describes whether to synchronize the metainformation
    of all repositories at the start.
* `model`
  * `supported_repos` - describes the supported repositories.
    * `repo_kind` - kind of repository (live, release, ...).
    * `tarantool_series` - list of the supported tarantool series.
    * `distrs` - describes the supported versions of distributions.

Tip (hashing password for credentials):
```bash
python3 -c "from werkzeug.security import generate_password_hash; print(generate_password_hash('password'))"
```

# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](http://keepachangelog.com/en/1.0.0/)
and this project adheres to [Semantic Versioning](http://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- Changed deployment mode back to `buildpack`.

## [1.0.11] - 2024-03-04

### Changed

- Fixed an issue with the `Werkzeug` dependency.

## [1.0.10] - 2024-03-01

### Added

- Added support of Fedora 39.
- Added support of AlmaLinux 8, 9.
- Added support of Astra Linux 1.7.

## [1.0.9] - 2023-08-31

### Added

- Added support of Debian Bookworm and Fedora 37, 38.

## [1.0.8] - 2023-08-29

### Added

- Added support of static repositories.
- Added `Dockerfile` to build Docker images.
- Added `docker-compose.yml` for setting up a test stand.

## [1.0.7] - 2023-04-06

### Changed

- Fixed broken paths to images in `templates/index.html`.

## [1.0.6] - 2022-12-07

### Changed

- Now the `.ddeb` files are simply skipped and all other files in the package
  continue to be processed. Previously, this caused fail package uploading.

## [1.0.5] - 2022-12-07

### Changed

- Changed the version of dokku deploy action to patched one which supports
  deploying to multiple environments.
- Updated checkout action to a newer version.
- Updated required version of `mkrepo` to 1.0.2.
  The new release of `mkrepo` contains several improvements and bug fixes. 
  The most significant of them are auto-installation of required package 
  dependencies, fixing Python 3.6 compatibility, and bumping `boto3` version 
  to 1.17.5.

## [1.0.4] - 2022-11-24

### Changed

- Updated required version of `mkrepo` to 1.0.0.
  The new release of `mkrepo` contains several improvements and bug
  fixes for handling rpm repository metainformation. The most
  significant of these is the addition of the ability to remove
  information about a removed package.

## [1.0.3] - 2022-09-06

### Added

- Added support of RedOS 7.3.

### Changed

- Updated required version of `mkrepo` to 0.1.10. The new version of `mkrepo`
  contains major bug fixes related to the processing of rpm repository metadata.

## [1.0.2] - 2022-07-22

### Added

- Added the `zstd` deb package as a dependency that is needed for the `mkrepo`
  library. The dependency is stored in the special files `apt-packages` and
  `Aptfile` that can be read by Dokku and Heroku services correspondingly to
  install required packages while RWS deployment.

## [1.0.1] - 2022-07-12

### Changed

- Updated required version of "mkrepo" to 0.1.7. The new version of mkrepo
  fixes the parsing of signed dsc files and the processing of rpm repository
  metainformation.

## [1.0.0] - 2022-06-19

### Added

- Displaying the contents of deb/rpm repositories located on S3 via HTTP.
- Uploading a package (creating/updating the metainformation of the related
  repository) to the deb/rpm repository located on S3, via HTTP with
  authentication.
- Multi-threaded synchronization of all repositories under RWS control, at
  the start of the service.
- Force synchronization mode, when enabled RWS ignores malformed packages
  during repository synchronization (information about malformed packages will
  be saved in the `malformed_list.txt` file).
- The ability to set different GPG keys to sign `tarantool' and module
  repositories.
- The `anchors' mechanism that allows to upload a package to multiple
  repositories using a single URL.
- All necessary files to start the service on the heroku/dokku platforms.
- Utility for backup repositories to/from S3.
- GHA to automatically deploy the service to the dokku platform.

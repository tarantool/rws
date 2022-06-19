# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](http://keepachangelog.com/en/1.0.0/)
and this project adheres to [Semantic Versioning](http://semver.org/spec/v2.0.0.html).

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
